#!/bin/bash
# Runs on the HOST with sudo: sudo bash run_all_host.sh [repeats]
# Runs the whole remaining pipeline (about 3 hours for 5 repeats) and exits.
# Progress: logs/final/stage and logs/final/batch.log
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
NAME=v2x-all
docker rm -f "$NAME" > /dev/null 2>&1
docker run --name "$NAME" --rm --privileged --net host -e REPS="${1:-5}" \
  -v /sys/:/sys -v /lib/modules:/lib/modules -v /sys/kernel/debug:/sys/kernel/debug \
  -v /var/run/netns:/var/run/netns -v "$PROJECT":/app/project \
  --entrypoint /bin/bash mn-wifi:v2 \
  -c "service openvswitch-switch start > /dev/null && bash /app/project/scripts/run_all_inner.sh"
RC=$?
[ -n "$SUDO_USER" ] && chown -R "$SUDO_USER": "$PROJECT"
echo "ALL FINISHED rc=$RC, see $PROJECT/logs/final/batch.log"
