#!/bin/bash
# Runs INSIDE the container: the whole remaining pipeline in one go.
#   1 environment facts   2 functional checks   3 Step 12 check   4 gate
#   5 dashboard recordings   6 full experiments (5 repeats)
OUT=/app/project/logs/final
mkdir -p "$OUT"
exec > >(tee -a "$OUT/batch.log") 2>&1
S=/app/project/scripts
stage() { echo "$(date '+%F %T') STAGE $1"; echo "$1" > "$OUT/stage"; }

stage env
rm -f /app/project/mn170_rsu1-wlan1.apconf /app/project/mn170_rsu2-wlan1.apconf
{ uname -r; tc -V; ovs-vsctl --version | head -1; iperf3 --version | head -1; python3 --version
  pip show ryu 2>/dev/null | grep -i ^version; which sumo || echo "sumo: not installed"; } > "$OUT/env.txt" 2>&1

stage functional; bash $S/functional_inner.sh
stage step12;     V2X_PLOT=0 bash $S/verify_step12_inner.sh
stage gate
if ! python3 $S/gate.py > "$OUT/gate.txt" 2>&1; then
    cat "$OUT/gate.txt"; stage GATE_FAILED; exit 1
fi
cat "$OUT/gate.txt"
stage demo
bash $S/demo_inner.sh scripted_orchestrated orchestrated scripted
bash $S/demo_inner.sh scripted_best_effort best_effort scripted
bash $S/demo_inner.sh random_orchestrated orchestrated random 7
bash $S/demo_inner.sh random_best_effort best_effort random 7
stage experiments; bash $S/run_step2_inner.sh ${REPS:-5}
stage done
# Appended while the first batch ran: the random-mobility recordings made before the
# random waypoint fix show parked vehicles, so record them again.
stage rerecord
bash $S/demo_inner.sh random_orchestrated orchestrated random 7
bash $S/demo_inner.sh random_best_effort best_effort random 7
stage done
