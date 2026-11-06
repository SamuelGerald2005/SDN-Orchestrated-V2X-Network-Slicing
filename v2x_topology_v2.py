#!/usr/bin/env python3
"""
V2X SDN Topology v2 (post-review)
- 2 RSUs with co-located MEC servers (URLLC slice, low latency)
- 6 vehicles, on intersecting road paths (default) or random waypoint mobility
- Central infotainment (eMBB) and telemetry (mMTC) servers behind an OVS backhaul
- Link delays/bandwidth model edge vs. core so latency and congestion are measurable
- Strict-priority queues on the 20 Mbit/s backhaul, selected by the DSCP mark the
  controller writes into each slice's packets
- RYU as remote OpenFlow 1.3 controller

Order: mn -c  ->  ryu-manager <app>  ->  python3 v2x_topology_v2.py

Environment options:
  V2X_MOBILITY=random   random waypoint mobility instead of the scripted paths
  V2X_SEED=<n>          random waypoint seed (default 1)
  V2X_PLOT=0            no live plot (used during measurements)
  V2X_TRACE=<dir>       write node positions for the dashboard every 0.5 s
"""
import json
import os
import threading
import time

from mininet.log import setLogLevel, info
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.link import TCLink
from mn_wifi.net import Mininet_wifi
from mn_wifi.cli import CLI
from mn_wifi.link import wmediumd, IntfWireless
from mn_wifi.wmediumdConnector import interference

# Link model (one-way delays; RTT is roughly double)
EDGE_DELAY = '0.5ms'      # RSU <-> co-located MEC server
BACKHAUL_DELAY = '5ms'    # RSU <-> aggregation switch
CORE_DELAY = '15ms'       # aggregation switch <-> central/cloud servers
BACKHAUL_BW = 20          # Mbit/s, so eMBB load can congest it
CORE_BW = 100             # Mbit/s

# RSU (hostapd) settings from Saraiva et al., IEEE T-ITS 2021 (framework_its_sdn,
# testes2020.py). Without them the old RSU keeps a departed vehicle in its station
# list for minutes and delivers frames for it locally, breaking V2V after handover.
RSU_CONFIG = 'ap_max_inactivity=6,skip_inactivity_poll=1,max_listen_interval=6'
# Coverage radius in metres. RSUs are 40 m apart, so 30 m gives 20 m of overlap: a
# moving vehicle always has an RSU in range and hands over without a coverage hole.
RSU_RANGE = 30
# Periodic vehicle beacons (Saraiva et al. also run these). They stop a parked
# vehicle being dropped by the short inactivity limit, and let the controller see
# each vehicle during mobility so handovers are detected.
BEACON_DST = '10.0.0.30'
BEACON_INTERVAL = 1       # s; must stay well below ap_max_inactivity

# Random waypoint area: every point is within RSU_RANGE of an RSU
RWP_AREA = {'min_x': 5, 'max_x': 65, 'min_y': 15, 'max_y': 45}
RWP_SPEED = {'min_v': 2, 'max_v': 4}     # m/s

# Strict-priority bands on the backhaul, selected by DSCP (dsfield = DSCP << 2).
# Band 1: URLLC (EF 46) and platoon (CS5 40). Band 2: mMTC (AF21 18).
# Band 3: eMBB (AF11 10), best effort and anything unmarked.
DSCP_BANDS = [(46, 1), (40, 1), (18, 2), (10, 3)]

MOBILITY = os.environ.get('V2X_MOBILITY', 'scripted')


def _thread_safe_cmd(self, *args, **kwargs):
    """Mininet-WiFi's mobility thread runs iw/hwsim commands through the node's
    shell. If the CLI is running a foreground command on that node at the same time
    (an iperf3 client, say), mininet raises AssertionError, the mobility thread dies
    and the vehicles freeze. Off the main thread, run the command as a separate
    process in the node's namespace instead."""
    if threading.current_thread() is threading.main_thread():
        return self.node.cmd(*args, **kwargs)
    out, err, _ = self.node.pexec(['sh', '-c', ' '.join(str(a) for a in args)])
    return out + err


IntfWireless.cmd = _thread_safe_cmd


def priority_queues(intfs, bw_mbit, delay):
    """Replace TCLink's HTB + netem tree with HTB (same rate) -> 3-band strict
    priority -> netem (same delay) per band. Rate and delay are unchanged, and
    with no DSCP marks every packet uses band 3, which behaves like the original
    single queue."""
    for intf in intfs:
        dev = intf.name
        cmds = ['tc qdisc del dev %s root' % dev,
                'tc qdisc add dev %s root handle 5: htb default 1' % dev,
                'tc class add dev %s parent 5: classid 5:1 htb rate %smbit burst 15k quantum 1514'
                % (dev, bw_mbit),
                'tc qdisc add dev %s parent 5:1 handle 10: prio bands 3 '
                'priomap 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2 2' % dev]
        for band in (1, 2, 3):
            cmds.append('tc qdisc add dev %s parent 10:%d handle %d: netem delay %s limit 1000'
                        % (dev, band, 20 + band, delay))
        for dscp, band in DSCP_BANDS:
            cmds.append('tc filter add dev %s parent 10: protocol ip prio %d u32 '
                        'match ip dsfield 0x%02x 0xfc flowid 10:%d'
                        % (dev, band, dscp << 2, band))
        errors = [out for out in (intf.node.cmd(c) for c in cmds) if out.strip()]
        info('*** Priority queues on %s%s\n' % (dev, ': ' + ' | '.join(errors) if errors else ''))


def position_of(node):
    pos = getattr(node, 'position', None) or node.params.get('position')
    if isinstance(pos, str):
        pos = pos.split(',')
    return [round(float(v), 2) for v in pos[:2]] if pos else None


def start_trace(trace_dir, aps, stations, hosts, links):
    """Write meta.json once and positions.json every 0.5 s for the dashboard."""
    os.makedirs(trace_dir, exist_ok=True)
    meta = {'mobility': MOBILITY, 'rsu_range': RSU_RANGE, 'backhaul_mbit': BACKHAUL_BW,
            'rsus': {ap.name: {'pos': position_of(ap), 'dpid': int(ap.dpid, 16)} for ap in aps},
            'switches': {'s1': {'dpid': 1}},
            'hosts': {h.name: {'ip': h.IP()} for h in hosts},
            'vehicles': {s.name: {'ip': s.IP()} for s in stations},
            'links': links}
    with open(os.path.join(trace_dir, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)

    def loop():
        path = os.path.join(trace_dir, 'positions.json')
        while True:
            vehicles = {}
            for sta in stations:
                intf = sta.wintfs[0]
                ap = getattr(intf, 'associatedTo', None)
                vehicles[sta.name] = {'pos': position_of(sta),
                                      'rsu': getattr(getattr(ap, 'node', None), 'name', None),
                                      'rssi': getattr(intf, 'rssi', None)}
            tmp = path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump({'t': round(time.time(), 2), 'vehicles': vehicles}, f)
            os.replace(tmp, path)
            time.sleep(0.5)

    threading.Thread(target=loop, daemon=True).start()


def topology():
    # client_isolation (ap_isolate=1) stops an RSU delivering vehicle-to-vehicle
    # frames itself, so all V2V traffic reaches OVS and passes through the slice
    # meters. The controller sends same-RSU traffic back out the Wi-Fi port.
    net = Mininet_wifi(link=wmediumd, wmediumd_mode=interference,
                       client_isolation=True)

    info('*** Adding controller (RYU)\n')
    c0 = net.addController('c0', controller=RemoteController,
                           ip='127.0.0.1', port=6653)

    info('*** Adding access points (RSUs)\n')
    rsu1 = net.addAccessPoint('rsu1', ssid='rsu1-ssid', mode='g',
                              channel='1', position='15,30,0',
                              protocols='OpenFlow13', config=RSU_CONFIG,
                              range=RSU_RANGE)
    rsu2 = net.addAccessPoint('rsu2', ssid='rsu2-ssid', mode='g',
                              channel='6', position='55,30,0',
                              protocols='OpenFlow13', config=RSU_CONFIG,
                              range=RSU_RANGE)

    info('*** Adding OVS backhaul switch\n')
    s1 = net.addSwitch('s1', cls=OVSKernelSwitch, protocols='OpenFlow13')

    info('*** Adding vehicle stations (6)\n')
    # Mininet-WiFi treats a station with a fixed position as stationary, so under
    # random waypoint the vehicles get the movement area instead of a start point.
    starts = ['10,30,0', '10,40,0', '60,30,0', '50,40,0', '15,10,0', '55,50,0']
    place = [dict(RWP_AREA, **RWP_SPEED) if MOBILITY == 'random' else {'position': p}
             for p in starts]
    vehicles = [net.addStation('veh%d' % i, mac='00:00:00:00:00:%02d' % i,
                               ip='10.0.0.%d/8' % i, **place[i - 1])
                for i in range(1, 7)]
    veh1, veh2, veh3, veh4, veh5, veh6 = vehicles

    info('*** Adding edge (MEC) servers at RSUs - URLLC slice\n')
    mec_rsu1 = net.addHost('mec_rsu1', ip='10.0.0.11/8')
    mec_rsu2 = net.addHost('mec_rsu2', ip='10.0.0.12/8')

    info('*** Adding central servers - eMBB and mMTC slices\n')
    info_srv = net.addHost('infotain', ip='10.0.0.20/8')
    telemetry_srv = net.addHost('telemetry', ip='10.0.0.30/8')

    info('*** Setting propagation model\n')
    net.setPropagationModel(model='logDistance', exp=5)

    info('*** Configuring nodes\n')
    net.configureNodes()

    info('*** Creating links\n')
    # Edge: MEC co-located with each RSU (no backhaul traversal)
    net.addLink(rsu1, mec_rsu1, cls=TCLink, delay=EDGE_DELAY)
    net.addLink(rsu2, mec_rsu2, cls=TCLink, delay=EDGE_DELAY)
    # Backhaul: RSUs to aggregation switch (bandwidth-limited)
    net.addLink(rsu1, s1, cls=TCLink, delay=BACKHAUL_DELAY, bw=BACKHAUL_BW)
    net.addLink(rsu2, s1, cls=TCLink, delay=BACKHAUL_DELAY, bw=BACKHAUL_BW)
    # Core: central servers
    net.addLink(s1, info_srv, cls=TCLink, delay=CORE_DELAY, bw=CORE_BW)
    net.addLink(s1, telemetry_srv, cls=TCLink, delay=CORE_DELAY, bw=CORE_BW)

    info('*** Plotting topology\n')
    # V2X_PLOT=0 skips the live plot, which uses CPU during measurements
    if os.environ.get('V2X_PLOT', '1') != '0':
        net.plotGraph(max_x=100, max_y=100)

    if MOBILITY == 'random':
        info('*** Random waypoint mobility\n')
        net.setMobilityModel(time=0, model='RandomWayPoint', seed=int(os.environ.get('V2X_SEED', '1')),
                             max_x=RWP_AREA['max_x'], max_y=RWP_AREA['max_y'])
    else:
        info('*** Scripting vehicle mobility (intersecting paths)\n')
        net.startMobility(time=0)
        # West -> East
        net.mobility(veh1, 'start', time=1, position='10,30,0')
        net.mobility(veh2, 'start', time=2, position='10,40,0')
        # East -> West
        net.mobility(veh3, 'start', time=1, position='60,30,0')
        net.mobility(veh4, 'start', time=2, position='50,40,0')
        # Cross traffic (vertical)
        net.mobility(veh5, 'start', time=3, position='15,10,0')
        net.mobility(veh6, 'start', time=3, position='55,50,0')
        # End positions
        net.mobility(veh1, 'stop', time=20, position='60,30,0')
        net.mobility(veh2, 'stop', time=20, position='50,40,0')
        net.mobility(veh3, 'stop', time=20, position='10,30,0')
        net.mobility(veh4, 'stop', time=20, position='10,40,0')
        net.mobility(veh5, 'stop', time=20, position='15,50,0')
        net.mobility(veh6, 'stop', time=20, position='55,10,0')
        net.stopMobility(time=21)

    info('*** Starting network\n')
    net.build()
    c0.start()
    rsu1.start([c0])
    rsu2.start([c0])
    s1.start([c0])

    # Mininet-WiFi creates links during build(), so find the backhaul ones now
    backhaul = [{'rsu1', 's1'}, {'rsu2', 's1'}]
    ends = lambda link: {getattr(getattr(link, i, None), 'node', None) and
                         getattr(link, i).node.name for i in ('intf1', 'intf2')}
    intfs = [i for link in net.links if ends(link) in backhaul
             for i in (link.intf1, link.intf2)]
    priority_queues(intfs, BACKHAUL_BW, BACKHAUL_DELAY)

    trace = os.environ.get('V2X_TRACE')
    if trace:
        links = [['rsu1', 'mec_rsu1'], ['rsu2', 'mec_rsu2'], ['rsu1', 's1'], ['rsu2', 's1'],
                 ['s1', 'infotain'], ['s1', 'telemetry']]
        start_trace(trace, [rsu1, rsu2], vehicles,
                    [mec_rsu1, mec_rsu2, info_srv, telemetry_srv], links)

    info('*** Starting vehicle beacons\n')
    for veh in vehicles:
        veh.cmd('ping -i %d %s > /dev/null 2>&1 &' % (BEACON_INTERVAL, BEACON_DST))

    info('*** Running CLI\n')
    CLI(net)

    info('*** Stopping network\n')
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    topology()
