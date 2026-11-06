#!/bin/bash
# Runs INSIDE the container. Step 2: repeats each scenario under each setup, with
# setups interleaved in every repeat so slow drift doesn't favour one of them.
#
# Setups (controller switches):
#   best_effort   no meters, no priority marking, no loop      (V2X_SLICING=0)
#   meters_only   meters                                       (PRIORITY=0 DYNAMIC=0)
#   meters_loop   meters + threshold loop                      (PRIORITY=0 DYNAMIC=1)
#   static        meters + priority queues                     (PRIORITY=1 DYNAMIC=0)
#   orchestrated  meters + priority queues + threshold loop    (PRIORITY=1 DYNAMIC=1)
# Scenarios:
#   congestion  parked vehicles, eMBB flood, light critical traffic
#   heavy       parked vehicles, eMBB flood, critical slices near their budgets
#   handover    scripted intersecting paths, traffic while the vehicles move
#   random      random waypoint mobility for the whole trial, light critical traffic
#
# Usage: run_step2_inner.sh [repeats] ["scenario list"]   (STEP2_ROOT sets the log folder)
REPS=${1:-1}
SCENARIOS=${2:-congestion heavy handover random}
ROOT=${STEP2_ROOT:-/app/project/logs/step2}
PROBE="python3 /app/project/experiments/udp_probe.py"
cd /tmp

setups_for() {
    case $1 in
        congestion|heavy) echo "best_effort meters_only meters_loop static orchestrated" ;;
        *)                echo "best_effort static orchestrated" ;;
    esac
}

servers() {
    for s in "mec_rsu1 5000" "mec_rsu2 5000" "veh3 9000" "veh4 9000" "telemetry 1883"; do
        set -- $s
        echo "$1 $PROBE server --port $2 > /dev/null 2>&1 &"
    done
    echo "infotain iperf3 -s -p 8080 -D"
    echo "sh sleep 1"
}

probe() {  # node name dst port size pps dur
    echo "$1 $PROBE client --dst $3 --port $4 --size $5 --pps $6 --dur $7 --out $DIR/$2.csv > /dev/null 2>&1 &"
}

embb() {   # duration; downlink TCP to veh5
    echo "veh5 iperf3 -c 10.0.0.20 -p 8080 -R -P 4 -t $1 --json --logfile $DIR/embb.json"
}

finish() {
    echo "sh curl -s localhost:8081/v2x/events > $DIR/events.json"
    echo "sh curl -s localhost:8081/v2x/slices > $DIR/slices.json"
    for sw in s1 rsu1 rsu2; do
        echo "sh ovs-ofctl -O OpenFlow13 meter-stats $sw > $DIR/meters_$sw.txt 2>&1"
    done
    echo "sh for d in s1-eth1 s1-eth2 rsu1-eth3 rsu2-eth3; do echo == \$d; tc -s qdisc show dev \$d; done > $DIR/qdisc.txt 2>&1"
    echo "exit"
}

parked_flows() {   # $1 = light | heavy
    if [ "$1" = heavy ]; then
        # Critical slices just under their per-switch budgets (each meter counts both
        # directions, so the replies are included): about 8.2 Mb/s crosses s1 -> rsu1,
        # which with eMBB at its 12 Mb/s budget slightly overflows the 20 Mb/s backhaul.
        # URLLC edge moves to rsu2 so it doesn't share rsu1's URLLC meter with URLLC far.
        far="1000 540"; plat="1000 440"; edge="veh6 10.0.0.12"
    else
        far="200 100"; plat="1000 100"; edge="veh4 10.0.0.11"
    fi
    set -- $edge
    probe $1 urllc_edge $2 5000 200 100 60
    probe veh1 urllc_far 10.0.0.11 5000 $far 60
    probe veh2 platoon 10.0.0.3 9000 $plat 60
    probe veh4 mmtc 10.0.0.30 1883 200 10 60
    # 15 s idle, 30 s eMBB load, 15 s recovery, then time for PROTECT_OFF
    echo "sh sleep 15"
    embb 30
    echo "sh sleep 22"
}

scenario() {
    case $1 in
    congestion) echo "sh sleep 25"; servers; parked_flows light ;;
    heavy)      echo "sh sleep 25"; servers; parked_flows heavy ;;
    random)     echo "sh sleep 10"; servers; parked_flows light ;;
    handover)           # traffic from the moment the CLI starts, while vehicles move
        servers
        probe veh1 urllc_far 10.0.0.11 5000 200 100 30
        probe veh3 urllc_edge 10.0.0.11 5000 200 100 30
        probe veh2 platoon 10.0.0.4 9000 1000 100 30
        embb 30
        echo "sh sleep 3"
        ;;
    esac
    finish
}

for rep in $(seq 1 "$REPS"); do
  for scen in $SCENARIOS; do
    for setup in $(setups_for "$scen"); do
        DIR=$ROOT/${scen}/${setup}/r$rep
        rm -rf "$DIR"; mkdir -p "$DIR"
        echo "$(date +%T) rep $rep $scen $setup"
        mn -c > /dev/null 2>&1
        pkill -f udp_probe; pkill iperf3
        case $setup in
            best_effort)  export V2X_SLICING=0 V2X_PRIORITY=0 V2X_DYNAMIC=0 ;;
            meters_only)  export V2X_SLICING=1 V2X_PRIORITY=0 V2X_DYNAMIC=0 ;;
            meters_loop)  export V2X_SLICING=1 V2X_PRIORITY=0 V2X_DYNAMIC=1 ;;
            static)       export V2X_SLICING=1 V2X_PRIORITY=1 V2X_DYNAMIC=0 ;;
            orchestrated) export V2X_SLICING=1 V2X_PRIORITY=1 V2X_DYNAMIC=1 ;;
        esac
        if [ "$scen" = random ]; then
            export V2X_MOBILITY=random V2X_SEED=$rep
        else
            export V2X_MOBILITY=scripted
        fi
        ryu-manager --wsapi-port 8081 /app/project/controller/v2x_orchestrator.py \
            > "$DIR/ryu.log" 2>&1 &
        RYU=$!
        sleep 4
        scenario "$scen" | V2X_PLOT=0 timeout 220 python3 /app/project/v2x_topology_v2.py \
            > "$DIR/topology.log" 2>&1
        echo "topology exit code: $?" >> "$DIR/topology.log"
        kill "$RYU" 2>/dev/null
        pkill -f udp_probe; pkill iperf3
    done
  done
done
mn -c > /dev/null 2>&1
