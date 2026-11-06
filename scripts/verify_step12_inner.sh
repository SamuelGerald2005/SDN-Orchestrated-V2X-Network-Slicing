#!/bin/bash
# Runs INSIDE the container. Step 12 check: start RYU + topology, run the CLI
# checks from a script, and keep all output in logs/step12/.
OUT=/app/project/logs/step12
mkdir -p "$OUT"
rm -f "$OUT"/*.log
cd /tmp   # keeps Mininet-WiFi's *.apconf files out of the project folder

mn -c > "$OUT/mn_clean.log" 2>&1

# --verbose records each connection/handshake event, needed to diagnose switches
ryu-manager --verbose --wsapi-port 8081 /app/project/controller/v2x_orchestrator.py \
    > "$OUT/ryu.log" 2>&1 &
RYU_PID=$!
sleep 5

{
    stations() {  # which vehicles each RSU's kernel still lists as associated
        echo "sh echo \"=== STATIONS $1 ===\"; for r in rsu1 rsu2; do echo \$r; iw dev \$r-wlan1 station dump | grep -E 'Station|inactive time'; done"
    }
    sleep 30    # mobility runs t=1..21 s
    echo 'sh echo "=== CONNECTION CHECK ==="; ovs-vsctl show; ss -tan | grep -E ":(6633|6653) "; curl -s localhost:8081/v2x/slices'
    stations after-mobility
    echo 'sh echo "=== PINGALL warm-up ==="'
    echo 'pingall'
    echo 'sh echo "=== PINGALL 1 ==="'
    echo 'pingall'
    echo 'sh echo "=== PINGALL 2 ==="'
    echo 'pingall'
    stations after-pingall-2
    # Does platoon traffic (UDP 9000) reach its meter? veh5 and veh3 end on rsu1,
    # veh1 ends on rsu2, so these are same-RSU and cross-RSU V2V respectively.
    echo 'veh3 iperf3 -s -p 9000 -D'
    echo 'sh sleep 1'
    table0() { echo "sh echo \"=== PLATOON COUNTERS $1 ===\"; for b in rsu1 rsu2 s1; do echo \$b; ovs-ofctl -O OpenFlow13 dump-flows \$b table=0 | grep -E 'tp_(dst|src)=9000' | sed 's/.*n_packets=/n_packets=/'; done"; }
    table0 before
    echo 'sh echo "=== PLATOON same-RSU veh5 to veh3 ==="'
    echo 'veh5 iperf3 -c 10.0.0.3 -u -p 9000 -b 1M -t 3'
    table0 after-same-rsu
    echo 'sh echo "=== PLATOON cross-RSU veh1 to veh3 ==="'
    echo 'veh1 iperf3 -c 10.0.0.3 -u -p 9000 -b 1M -t 3'
    table0 after-cross-rsu
    # Above the platoon budget (4000 kb/s), so about half should be dropped
    echo 'sh echo "=== METER LIMIT same-RSU veh5 to veh3 at 8M ==="'
    echo 'veh5 iperf3 -c 10.0.0.3 -u -p 9000 -b 8M -t 5'
    echo 'sh echo "=== METER LIMIT cross-RSU veh1 to veh3 at 8M ==="'
    echo 'veh1 iperf3 -c 10.0.0.3 -u -p 9000 -b 8M -t 5'
    echo 'sh sleep 8'   # lets critical load fall so PROTECT_OFF can fire
    echo 'sh echo "=== RSU1 APCONF ==="; cat /tmp/mn*_rsu1-wlan1.apconf'
    for sw in s1 rsu1 rsu2; do
        echo "sh echo \"=== METERS $sw ===\"; ovs-ofctl -O OpenFlow13 dump-meters $sw"
        echo "sh echo \"=== TABLE0 $sw ===\"; ovs-ofctl -O OpenFlow13 dump-flows $sw table=0"
        echo "sh echo \"=== TABLE1 $sw ===\"; ovs-ofctl -O OpenFlow13 dump-flows $sw table=1"
    done
    echo 'sh echo "=== REST slices ==="; curl -s localhost:8081/v2x/slices'
    echo 'sh echo "=== REST events ==="; curl -s localhost:8081/v2x/events'
    echo 'exit'
} | timeout 900 python3 /app/project/v2x_topology_v2.py > "$OUT/topology.log" 2>&1
echo "topology exit code: $?" >> "$OUT/topology.log"

kill "$RYU_PID" 2>/dev/null
cp /var/log/openvswitch/ovs-vswitchd.log "$OUT/ovs-vswitchd.log" 2>/dev/null
mn -c >> "$OUT/mn_clean.log" 2>&1
