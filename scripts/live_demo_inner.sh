#!/bin/bash
# Runs INSIDE the container: a continuous testbed for the dashboard's Live view.
# Random waypoint vehicles, traffic in every slice, and an eMBB flood that switches
# on and off every 30 s. Runs for ${MINUTES:-30} minutes or until stopped.
# Usage: live_demo_inner.sh [setup]   (orchestrated, static or best_effort)
SETUP=${1:-orchestrated}
D=/app/project/logs/live
PROBE="python3 /app/project/experiments/udp_probe.py"
MINUTES=${MINUTES:-30}
DUR=$(( MINUTES * 60 ))
rm -rf "$D"; mkdir -p "$D/trace" "$D/live"; cd /tmp
mn -c > /dev/null 2>&1; pkill -f udp_probe; pkill iperf3
case $SETUP in
    best_effort)  export V2X_SLICING=0 V2X_PRIORITY=0 V2X_DYNAMIC=0 ;;
    static)       export V2X_SLICING=1 V2X_PRIORITY=1 V2X_DYNAMIC=0 ;;
    *)            export V2X_SLICING=1 V2X_PRIORITY=1 V2X_DYNAMIC=1 ;;
esac
export V2X_MOBILITY=random V2X_SEED=${SEED:-7} V2X_PLOT=0 V2X_TRACE=$D/trace
ryu-manager --wsapi-port 8081 /app/project/controller/v2x_orchestrator.py > "$D/ryu.log" 2>&1 &
RYU=$!
sleep 4
live() { echo "$1 $PROBE client --dst $3 --port $4 --size $5 --pps $6 --dur $DUR --out $D/$2.csv --live $D/live/$2.json --name $2 > /dev/null 2>&1 &"; }
{
    echo "sh sleep 2"
    for s in "mec_rsu1 5000" "mec_rsu2 5000" "veh3 9000" "telemetry 1883"; do
        set -- $s; echo "$1 $PROBE server --port $2 > /dev/null 2>&1 &"
    done
    echo "infotain iperf3 -s -p 8080 -D"
    echo "sh sleep 1"
    live veh1 urllc_veh1 10.0.0.11 5000 200 100
    live veh4 urllc_veh4 10.0.0.12 5000 200 100
    live veh2 platoon 10.0.0.3 9000 1000 100
    live veh6 mmtc 10.0.0.30 1883 200 10
    for i in $(seq 1 $(( DUR / 60 ))); do
        echo "sh sleep 30"
        echo "veh5 iperf3 -c 10.0.0.20 -p 8080 -R -P 4 -t 30 > /dev/null"
    done
    echo "exit"
} | timeout $(( DUR + 120 )) python3 /app/project/v2x_topology_v2.py > "$D/topology.log" 2>&1
kill $RYU 2>/dev/null; pkill -f udp_probe; pkill iperf3
mn -c > /dev/null 2>&1
