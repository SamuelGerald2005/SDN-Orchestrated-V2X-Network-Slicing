#!/bin/bash
# Runs INSIDE the container: records dashboard replays. Each run is 100 s: traffic in
# every slice from the start, and an eMBB flood from 30 s to 70 s.
# Usage: demo_inner.sh name setup mobility [seed]
NAME=$1; SETUP=$2; MOB=$3; SEED=${4:-7}
D=/app/project/logs/demo/$NAME
REC=/app/project/dashboard/recordings
PROBE="python3 /app/project/experiments/udp_probe.py"
rm -rf "$D"; mkdir -p "$D/trace" "$D/live" "$REC"; cd /tmp
mn -c > /dev/null 2>&1; pkill -f udp_probe; pkill iperf3
case $SETUP in
    best_effort)  export V2X_SLICING=0 V2X_PRIORITY=0 V2X_DYNAMIC=0 ;;
    static)       export V2X_SLICING=1 V2X_PRIORITY=1 V2X_DYNAMIC=0 ;;
    orchestrated) export V2X_SLICING=1 V2X_PRIORITY=1 V2X_DYNAMIC=1 ;;
esac
export V2X_MOBILITY=$MOB V2X_SEED=$SEED V2X_PLOT=0 V2X_TRACE=$D/trace
ryu-manager --wsapi-port 8081 /app/project/controller/v2x_orchestrator.py > "$D/ryu.log" 2>&1 &
RYU=$!
sleep 4
live() { echo "$1 $PROBE client --dst $3 --port $4 --size $5 --pps $6 --dur 98 --out $D/$2.csv --live $D/live/$2.json --name $2 > /dev/null 2>&1 &"; }
{
    echo "sh sleep 2"
    for s in "mec_rsu1 5000" "mec_rsu2 5000" "veh3 9000" "telemetry 1883"; do
        set -- $s; echo "$1 $PROBE server --port $2 > /dev/null 2>&1 &"
    done
    echo "infotain iperf3 -s -p 8080 -D"
    echo "sh sleep 1"
    echo "sh cd /app/project/dashboard && python3 recorder.py --trace $D/trace --live $D/live --out $REC/$NAME.json --dur 100 --setup $SETUP --scenario $MOB > $D/recorder.log 2>&1 &"
    live veh1 urllc_veh1 10.0.0.11 5000 200 100
    live veh4 urllc_veh4 10.0.0.12 5000 200 100
    live veh2 platoon 10.0.0.3 9000 1000 100
    live veh6 mmtc 10.0.0.30 1883 200 10
    echo "sh sleep 30"
    echo "veh5 iperf3 -c 10.0.0.20 -p 8080 -R -P 4 -t 40 --json --logfile $D/embb.json"
    echo "sh sleep 32"
    echo "exit"
} | timeout 220 python3 /app/project/v2x_topology_v2.py > "$D/topology.log" 2>&1
echo "topology exit code: $?" >> "$D/topology.log"
kill $RYU 2>/dev/null; pkill -f udp_probe; pkill -f recorder.py; pkill iperf3
mn -c > /dev/null 2>&1
