"""
V2X Slice Orchestrator (RYU, OpenFlow 1.3)
==========================================

A single RYU application that acts as the slice orchestrator for the
Mininet-WiFi V2X testbed. Its functions (evaluator input 1):

  1. Slice definition      - SLICES table below, editable at runtime via REST
  2. Admission/classification - proactive OpenFlow rules (table 0) map each
                              application's traffic to its slice, both directions
  3. Resource allocation   - one OpenFlow 1.3 meter per slice per switch caps
                              each slice's bandwidth (isolation), following the
                              RYU + OF1.3 metering approach of Campolo et al.
  4. Monitoring            - meter statistics polled every POLL_INTERVAL seconds
  5. Dynamic adaptation    - threshold loop: from the measured critical load
                              (URLLC + platooning) on each switch, the eMBB
                              budget is cut to what the backhaul has left, and
                              restored when the critical slices go quiet
  5b. Priority scheduling  - slice rules mark DSCP, and strict-priority queues on
                              the backhaul links serve critical slices first
  6. Mobility management   - forwarding (table 1) detects handovers between
                              RSUs and flushes stale flows network-wide, so
                              traffic follows the vehicle (Research Gap 3).
                              RSUs use client isolation, so same-RSU V2V also
                              passes through OVS and its slice meter
  7. Northbound REST API   - inspect and resize slices while the network runs

Pipeline
  table 0 : slice classification  -> meter <slice> -> mark DSCP -> goto table 1
            everything else        -> meter best-effort -> goto table 1
  table 1 : mobility-aware MAC learning / forwarding

Meters police inside the switch and do not touch Linux tc, so the link delays
and bandwidth set by TCLink in the topology stay intact.

Run (inside the container, after `mn -c`):
    ryu-manager --wsapi-port 8081 /app/project/controller/v2x_orchestrator.py
Baseline without slicing (same forwarding, no meters), for before/after tests:
    V2X_SLICING=0 ryu-manager --wsapi-port 8081 /app/project/controller/v2x_orchestrator.py
Static slicing (meters on, threshold loop off):
    V2X_DYNAMIC=0 ryu-manager --wsapi-port 8081 /app/project/controller/v2x_orchestrator.py
Other switches: V2X_PRIORITY=0 (no DSCP marking), V2X_POLICY=fixed (earlier halving policy)

REST (from a container shell):
    curl -s localhost:8081/v2x/slices | python3 -m json.tool
    curl -s -X PUT -d '{"kbps": 8000}' localhost:8081/v2x/slices/embb
    curl -s localhost:8081/v2x/events | python3 -m json.tool
"""
import json
import os
import time
from collections import deque

from ryu.app.wsgi import ControllerBase, Response, WSGIApplication, route
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (CONFIG_DISPATCHER, MAIN_DISPATCHER,
                                    set_ev_cls)
from ryu.lib import hub
from ryu.lib.packet import ethernet, ether_types, packet
from ryu.ofproto import ofproto_v1_3

# --------------------------------------------------------------------------
# Slice definitions. Budgets are per switch, in kbit/s, sized for the 20 Mbit/s
# RSU backhaul in v2x_topology_v2.py. Port numbers match the earlier controller.
# --------------------------------------------------------------------------
# dscp: DiffServ code point written into each packet, which the priority queues on
# the backhaul links (v2x_topology_v2.py) use to pick a band. EF and CS5 go to the
# highest band, AF21 to the middle one, AF11 and unmarked traffic to the lowest.
SLICES = {
    'urllc':   {'meter': 1, 'proto': 17, 'port': 5000, 'kbps': 5000, 'dscp': 46,
                'critical': True,  'desc': 'Safety messages -> RSU edge (MEC) server'},
    'platoon': {'meter': 2, 'proto': 17, 'port': 9000, 'kbps': 4000, 'dscp': 40,
                'critical': True,  'desc': 'Cooperative driving / platooning (V2V)'},
    'embb':    {'meter': 3, 'proto': 6,  'port': 8080, 'kbps': 12000, 'dscp': 10,
                'critical': False, 'desc': 'Infotainment -> central server'},
    'mmtc':    {'meter': 4, 'proto': 17, 'port': 1883, 'kbps': 1000, 'dscp': 18,
                'critical': False, 'desc': 'Vehicle telemetry -> central server'},
}
BEST_EFFORT = {'meter': 5, 'kbps': 2000}    # all unclassified traffic

# Threshold loop
POLL_INTERVAL = 2           # s between statistics polls
# 'capacity' (default): while critical traffic is present, eMBB gets whatever the
#   backhaul has left: capacity - critical load - headroom, between EMBB_MIN_KBPS
#   and its budget. It is only cut when the link would otherwise overflow.
# 'fixed': the earlier policy, eMBB halved whenever critical load >= CRITICAL_ON_KBPS.
POLICY = os.environ.get('V2X_POLICY', 'capacity')
LINK_CAPACITY_KBPS = 20000  # RSU backhaul in v2x_topology_v2.py
HEADROOM_KBPS = 1500        # margin for mMTC, best effort and bursts
EMBB_MIN_KBPS = 2000        # eMBB is never squeezed below this
STEP_KBPS = 500             # changes smaller than this are ignored, to avoid churn
CRITICAL_ON_KBPS = 500      # 'fixed' policy: critical load that triggers protection
CRITICAL_OFF_KBPS = 200     # 'fixed' policy: load below which protection is released
EMBB_PROTECT_FACTOR = 0.5   # 'fixed' policy: eMBB budget multiplier while protecting

# Forwarding (table 1)
IDLE_TIMEOUT = 10
HARD_TIMEOUT = 30

PRIO_SLICE = 100
PROTO_NAME = {6: 'tcp', 17: 'udp'}
SLICING_ENABLED = os.environ.get('V2X_SLICING', '1') != '0'
# 0 = static slicing: meters stay at their budgets and the threshold loop never acts
DYNAMIC_ENABLED = os.environ.get('V2X_DYNAMIC', '1') != '0'
# 0 = no DSCP marking, so every packet shares one queue band (meters only)
PRIORITY_ENABLED = SLICING_ENABLED and os.environ.get('V2X_PRIORITY', '1') != '0'
API = 'v2x_orchestrator_app'


class V2XOrchestrator(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datapaths = {}       # dpid -> datapath
        self.mac_to_port = {}     # dpid -> {mac: port}
        self.wlan_ports = {}      # dpid -> {port numbers that are RSU Wi-Fi interfaces}
        self.applied = {}         # dpid -> {meter_id: kbps currently installed}
        self.protecting = {}      # dpid -> bool (eMBB cut active)
        self.embb_target = {}     # dpid -> eMBB kb/s set by the capacity policy
        self.last_bytes = {}      # (dpid, meter_id) -> (bytes, timestamp)
        self.measured = {}        # dpid -> {slice: kbps}
        self.budget = {name: s['kbps'] for name, s in SLICES.items()}
        self.event_log = deque(maxlen=200)   # not self.events: RyuApp uses that for its event queue
        kwargs['wsgi'].register(V2XRestController, {API: self})
        self.monitor_thread = hub.spawn(self._monitor)
        self._log('START', 'slicing %s, priority queues %s, threshold loop %s (%s policy)'
                  % ('ENABLED' if SLICING_ENABLED else 'DISABLED (baseline)',
                     'ENABLED' if PRIORITY_ENABLED else 'DISABLED',
                     'ENABLED' if DYNAMIC_ENABLED else 'DISABLED', POLICY))

    # ------------------------------------------------------------ utilities
    def _log(self, kind, text):
        self.event_log.append({'t': round(time.time(), 1), 'event': kind, 'detail': text})
        self.logger.info('%s %s', kind, text)

    @staticmethod
    def _inst(parser, ofp, actions=None, meter=None, goto=None):
        inst = []
        if meter is not None:
            inst.append(parser.OFPInstructionMeter(meter))
        if actions:
            inst.append(parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions))
        if goto is not None:
            inst.append(parser.OFPInstructionGotoTable(goto))
        return inst

    def _flow(self, dp, table, priority, match, inst, idle=0, hard=0):
        parser = dp.ofproto_parser
        dp.send_msg(parser.OFPFlowMod(datapath=dp, table_id=table, priority=priority,
                                      match=match, instructions=inst,
                                      idle_timeout=idle, hard_timeout=hard))

    def _meter(self, dp, meter_id, kbps, command):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        band = parser.OFPMeterBandDrop(rate=int(kbps), burst_size=max(int(kbps) // 10, 100))
        dp.send_msg(parser.OFPMeterMod(datapath=dp, command=command,
                                       flags=ofp.OFPMF_KBPS | ofp.OFPMF_BURST | ofp.OFPMF_STATS,
                                       meter_id=meter_id, bands=[band]))
        self.applied.setdefault(dp.id, {})[meter_id] = int(kbps)

    def _target_kbps(self, dpid, name):
        kbps = self.budget[name]
        if name == 'embb' and self.protecting.get(dpid):
            if POLICY == 'fixed':
                kbps = int(kbps * EMBB_PROTECT_FACTOR)
            else:
                kbps = min(kbps, self.embb_target.get(dpid, kbps))
        return kbps

    def _capacity_target(self, critical_kbps):
        spare = LINK_CAPACITY_KBPS - critical_kbps - HEADROOM_KBPS
        spare = int(spare // STEP_KBPS * STEP_KBPS)
        return max(EMBB_MIN_KBPS, min(self.budget['embb'], spare))

    # ------------------------------------------------- switch connection
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        self.datapaths[dp.id] = dp
        self.mac_to_port[dp.id] = {}
        self.protecting[dp.id] = False

        # Start from a clean switch: no leftover flows or meters
        dp.send_msg(parser.OFPFlowMod(datapath=dp, table_id=ofp.OFPTT_ALL,
                                      command=ofp.OFPFC_DELETE,
                                      out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
                                      match=parser.OFPMatch()))
        dp.send_msg(parser.OFPMeterMod(datapath=dp, command=ofp.OFPMC_DELETE,
                                       meter_id=ofp.OFPM_ALL))

        if SLICING_ENABLED:
            for name, s in SLICES.items():
                self._meter(dp, s['meter'], self._target_kbps(dp.id, name), ofp.OFPMC_ADD)
                proto = PROTO_NAME[s['proto']]
                # Both directions: requests (dst port) and replies (src port)
                mark = ([parser.OFPActionSetField(ip_dscp=s['dscp'])]
                        if PRIORITY_ENABLED else None)
                for field in ('%s_dst' % proto, '%s_src' % proto):
                    match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                            ip_proto=s['proto'], **{field: s['port']})
                    self._flow(dp, 0, PRIO_SLICE, match,
                               self._inst(parser, ofp, actions=mark, meter=s['meter'], goto=1))
            self._meter(dp, BEST_EFFORT['meter'], BEST_EFFORT['kbps'], ofp.OFPMC_ADD)
            self._flow(dp, 0, 0, parser.OFPMatch(),
                       self._inst(parser, ofp, meter=BEST_EFFORT['meter'], goto=1))
        else:
            self._flow(dp, 0, 0, parser.OFPMatch(), self._inst(parser, ofp, goto=1))

        # Table 1 miss -> controller (learning)
        to_ctrl = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self._flow(dp, 1, 0, parser.OFPMatch(), self._inst(parser, ofp, actions=to_ctrl))
        self._log('SWITCH', 'dpid %s connected' % dp.id)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, [CONFIG_DISPATCHER, MAIN_DISPATCHER])
    def port_desc_handler(self, ev):
        dp = ev.msg.datapath
        wlan = self.wlan_ports.setdefault(dp.id, set())
        for port in ev.msg.body:
            name = port.name.decode() if isinstance(port.name, bytes) else port.name
            if 'wlan' in name:
                wlan.add(port.port_no)

    @set_ev_cls(ofp_event.EventOFPErrorMsg, [CONFIG_DISPATCHER, MAIN_DISPATCHER])
    def error_handler(self, ev):
        m = ev.msg
        self.logger.error('OFP ERROR dpid=%s type=%s code=%s', m.datapath.id, m.type, m.code)

    # ------------------------------------------- mobility-aware forwarding
    def flush_mac(self, mac):
        """Remove every forwarding flow to/from `mac` and forget its location."""
        for dpid, dp in self.datapaths.items():
            ofp, parser = dp.ofproto, dp.ofproto_parser
            for match in (parser.OFPMatch(eth_dst=mac), parser.OFPMatch(eth_src=mac)):
                dp.send_msg(parser.OFPFlowMod(datapath=dp, table_id=1,
                                              command=ofp.OFPFC_DELETE,
                                              out_port=ofp.OFPP_ANY,
                                              out_group=ofp.OFPG_ANY, match=match))
            self.mac_to_port.get(dpid, {}).pop(mac, None)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match['in_port']

        eth = packet.Packet(msg.data).get_protocols(ethernet.ethernet)[0]
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        src, dst, dpid = eth.src, eth.dst, dp.id
        table = self.mac_to_port.setdefault(dpid, {})

        # Handover: a known source MAC appears on a different port
        old = table.get(src)
        if old is not None and old != in_port:
            self._log('HANDOVER', '%s dpid %s port %s -> %s, flows flushed'
                      % (src, dpid, old, in_port))
            self.flush_mac(src)
            table = self.mac_to_port.setdefault(dpid, {})
        table[src] = in_port

        out_port = table.get(dst, ofp.OFPP_FLOOD)
        # RSUs run with client isolation, so same-RSU V2V arrives here and must go
        # back out the Wi-Fi port it came from. FLOOD and plain output both skip the
        # ingress port, hence OFPP_IN_PORT. On a wired port, a destination behind
        # the ingress port means it has moved away.
        from_wlan = in_port in self.wlan_ports.get(dpid, ())
        if out_port == in_port and not from_wlan:
            self._log('STALE', '%s no longer behind dpid %s port %s, rediscovering'
                      % (dst, dpid, in_port))
            self.flush_mac(dst)
            out_port = ofp.OFPP_FLOOD

        if out_port == ofp.OFPP_FLOOD:
            actions = [parser.OFPActionOutput(ofp.OFPP_FLOOD)]
            if from_wlan:
                actions.append(parser.OFPActionOutput(ofp.OFPP_IN_PORT))
        else:
            port = ofp.OFPP_IN_PORT if out_port == in_port else out_port
            actions = [parser.OFPActionOutput(port)]
            match = parser.OFPMatch(in_port=in_port, eth_src=src, eth_dst=dst)
            self._flow(dp, 1, 1, match, self._inst(parser, ofp, actions=actions),
                       idle=IDLE_TIMEOUT, hard=HARD_TIMEOUT)

        dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=ofp.OFP_NO_BUFFER,
                                        in_port=in_port, actions=actions, data=msg.data))

    # --------------------------------------- monitoring + threshold loop
    def _monitor(self):
        while True:
            if SLICING_ENABLED:
                for dp in list(self.datapaths.values()):
                    dp.send_msg(dp.ofproto_parser.OFPMeterStatsRequest(
                        dp, 0, dp.ofproto.OFPM_ALL))
            hub.sleep(POLL_INTERVAL)

    @set_ev_cls(ofp_event.EventOFPMeterStatsReply, MAIN_DISPATCHER)
    def meter_stats_handler(self, ev):
        dp = ev.msg.datapath
        now = time.time()
        by_meter = {s['meter']: name for name, s in SLICES.items()}
        by_meter[BEST_EFFORT['meter']] = 'best_effort'
        rates = self.measured.setdefault(dp.id, {})

        for stat in ev.msg.body:
            name = by_meter.get(stat.meter_id)
            if name is None:
                continue
            key = (dp.id, stat.meter_id)
            prev = self.last_bytes.get(key)
            self.last_bytes[key] = (stat.byte_in_count, now)
            if prev and now > prev[1]:
                rates[name] = round((stat.byte_in_count - prev[0]) * 8 / 1000.0
                                    / (now - prev[1]), 1)

        critical = sum(rates.get(n, 0) for n, s in SLICES.items() if s['critical'])
        if DYNAMIC_ENABLED:
            if POLICY == 'fixed':
                self._fixed_policy(dp.id, critical)
            else:
                self._capacity_policy(dp.id, critical)
        self._sync_meters(dp)

    def _fixed_policy(self, dpid, critical):
        protecting = self.protecting.get(dpid, False)
        if not protecting and critical >= CRITICAL_ON_KBPS:
            self.protecting[dpid] = True
            self._log('PROTECT_ON', 'dpid %s critical load %.0f kb/s, eMBB -> %d kb/s'
                      % (dpid, critical, self._target_kbps(dpid, 'embb')))
        elif protecting and critical <= CRITICAL_OFF_KBPS:
            self.protecting[dpid] = False
            self._log('PROTECT_OFF', 'dpid %s critical load %.0f kb/s, eMBB -> %d kb/s'
                      % (dpid, critical, self._target_kbps(dpid, 'embb')))

    def _capacity_policy(self, dpid, critical):
        target = self._capacity_target(critical)
        protecting = self.protecting.get(dpid, False)
        current = self.embb_target.get(dpid, self.budget['embb'])
        if target < self.budget['embb']:
            if not protecting:
                self.protecting[dpid] = True
                self.embb_target[dpid] = target
                self._log('PROTECT_ON', 'dpid %s critical load %.0f kb/s, eMBB -> %d kb/s'
                          % (dpid, critical, target))
            elif abs(target - current) >= STEP_KBPS:
                self.embb_target[dpid] = target
                self._log('ADJUST', 'dpid %s critical load %.0f kb/s, eMBB -> %d kb/s'
                          % (dpid, critical, target))
        elif protecting:
            self.protecting[dpid] = False
            self.embb_target.pop(dpid, None)
            self._log('PROTECT_OFF', 'dpid %s critical load %.0f kb/s, eMBB -> %d kb/s'
                      % (dpid, critical, self.budget['embb']))

    def _sync_meters(self, dp):
        """Push any slice budget that differs from what the switch has."""
        if not SLICING_ENABLED:
            return
        for name, s in SLICES.items():
            want = self._target_kbps(dp.id, name)
            if self.applied.get(dp.id, {}).get(s['meter']) != want:
                self._meter(dp, s['meter'], want, dp.ofproto.OFPMC_MODIFY)

    # ------------------------------------------------ northbound helpers
    def status(self):
        return {
            'slicing_enabled': SLICING_ENABLED,
            'dynamic_enabled': DYNAMIC_ENABLED,
            'priority_enabled': PRIORITY_ENABLED,
            'policy': POLICY,
            'link_capacity_kbps': LINK_CAPACITY_KBPS,
            'slices': {name: dict(s, budget_kbps=self.budget[name]) for name, s in SLICES.items()},
            'best_effort': BEST_EFFORT,
            'switches': {str(dpid): {'protecting_critical': self.protecting.get(dpid, False),
                                     'installed_kbps': self.applied.get(dpid, {}),
                                     'measured_kbps': self.measured.get(dpid, {})}
                         for dpid in self.datapaths},
        }

    def set_budget(self, name, kbps):
        if name not in SLICES or kbps <= 0:
            return False
        self.budget[name] = int(kbps)
        self._log('RESIZE', '%s budget -> %d kb/s' % (name, kbps))
        for dp in list(self.datapaths.values()):
            self._sync_meters(dp)
        return True


class V2XRestController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super().__init__(req, link, data, **config)
        self.app = data[API]

    @route('v2x', '/v2x/slices', methods=['GET'])
    def get_slices(self, req, **kwargs):
        return Response(content_type='application/json',
                        text=json.dumps(self.app.status(), indent=2))

    @route('v2x', '/v2x/slices/{name}', methods=['PUT'])
    def put_slice(self, req, name, **kwargs):
        try:
            kbps = int(json.loads(req.body)['kbps'])
        except (ValueError, KeyError, TypeError):
            return Response(status=400, text='body must be {"kbps": <int>}\n')
        if not self.app.set_budget(name, kbps):
            return Response(status=404, text='unknown slice or bad rate\n')
        return Response(content_type='application/json',
                        text=json.dumps(self.app.status()['slices'][name], indent=2))

    @route('v2x', '/v2x/events', methods=['GET'])
    def get_events(self, req, **kwargs):
        return Response(content_type='application/json',
                        text=json.dumps(list(self.app.event_log), indent=2))
