#!/bin/bash
# Runs INSIDE the container: functional checks that the experiments don't cover.
#  - priority queue tree on the backhaul, and DSCP marks landing in the right band
#  - meter limits for URLLC, mMTC, best effort and eMBB under overload
#  - REST PUT resize, including bad requests
D=/app/project/logs/final/functional
rm -rf "$D"; mkdir -p "$D"; cd /tmp
mn -c > /dev/null 2>&1
export V2X_SLICING=1 V2X_PRIORITY=1 V2X_DYNAMIC=1 V2X_MOBILITY=scripted V2X_PLOT=0
ryu-manager --wsapi-port 8081 /app/project/controller/v2x_orchestrator.py > "$D/ryu.log" 2>&1 &
RYU=$!
sleep 4
CLASSES='for d in rsu1-eth3 rsu2-eth3 s1-eth1 s1-eth2; do echo == $d; tc -s class show dev $d | grep -A1 "class prio"; done'
{
    echo "sh sleep 25"
    echo "sh for d in rsu1-eth3 s1-eth1; do echo == \$d; tc qdisc show dev \$d; tc filter show dev \$d parent 10:; done > $D/qdisc_tree.txt 2>&1"
    echo "mec_rsu1 iperf3 -s -p 5000 -D"
    echo "telemetry iperf3 -s -p 1883 -D"
    echo "telemetry iperf3 -s -p 7000 -D"
    echo "infotain iperf3 -s -p 8080 -D"
    echo "sh sleep 1"
    # DSCP bands: URLLC from veh1 (rsu2) to mec_rsu1 crosses rsu2-eth3 and s1-eth1 -> band 1;
    # mMTC from veh4 (rsu1) to telemetry crosses rsu1-eth3 -> band 2
    echo "sh ($CLASSES) > $D/bands_before.txt 2>&1"
    echo "veh1 iperf3 -c 10.0.0.11 -u -p 5000 -b 1M -t 3 --json --logfile $D/band_urllc.json"
    echo "veh4 iperf3 -c 10.0.0.30 -u -p 1883 -b 500K -t 3 --json --logfile $D/band_mmtc.json"
    echo "sh ($CLASSES) > $D/bands_after.txt 2>&1"
    # Meter limits: each flood is about twice its slice budget
    echo "veh4 iperf3 -c 10.0.0.11 -u -p 5000 -b 10M -t 5 --json --logfile $D/limit_urllc_10M.json"
    echo "veh4 iperf3 -c 10.0.0.30 -u -p 1883 -b 2M -t 5 --json --logfile $D/limit_mmtc_2M.json"
    echo "veh4 iperf3 -c 10.0.0.30 -u -p 7000 -b 4M -t 5 --json --logfile $D/limit_be_4M.json"
    echo "veh5 iperf3 -c 10.0.0.20 -p 8080 -R -P 4 -t 8 --json --logfile $D/limit_embb_tcp.json"
    # REST resize: URLLC to 3000 kb/s, flood, then restore 5000
    echo "sh curl -s -o $D/put_3000.txt -w '%{http_code}\n' -X PUT -d '{\"kbps\": 3000}' localhost:8081/v2x/slices/urllc > $D/put_codes.txt"
    echo "sh sleep 1; ovs-ofctl -O OpenFlow13 dump-meters rsu1 > $D/meters_after_put.txt"
    echo "veh4 iperf3 -c 10.0.0.11 -u -p 5000 -b 10M -t 5 --json --logfile $D/limit_urllc_put3000.json"
    echo "sh curl -s -o /dev/null -w '%{http_code}\n' -X PUT -d '{\"kbps\": 5000}' localhost:8081/v2x/slices/urllc >> $D/put_codes.txt"
    echo "sh curl -s -o /dev/null -w '%{http_code}\n' -X PUT -d '{\"kbps\": 100}' localhost:8081/v2x/slices/nosuch >> $D/put_codes.txt"
    echo "sh curl -s -o /dev/null -w '%{http_code}\n' -X PUT -d 'oops' localhost:8081/v2x/slices/urllc >> $D/put_codes.txt"
    echo "sh sleep 1; ovs-ofctl -O OpenFlow13 dump-meters rsu1 > $D/meters_after_restore.txt"
    echo "sh curl -s localhost:8081/v2x/events > $D/events.json; curl -s localhost:8081/v2x/slices > $D/slices.json"
    echo "exit"
} | timeout 300 python3 /app/project/v2x_topology_v2.py > "$D/topology.log" 2>&1
echo "topology exit code: $?" >> "$D/topology.log"
kill $RYU 2>/dev/null; pkill iperf3
mn -c > /dev/null 2>&1
