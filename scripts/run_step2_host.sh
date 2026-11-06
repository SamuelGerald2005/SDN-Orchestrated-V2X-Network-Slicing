#!/bin/bash
# Runs on the HOST with sudo. Usage: sudo bash run_step2_host.sh [repeats] ["scenario list"]
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
NAME=v2x-step2
docker rm -f "$NAME" > /dev/null 2>&1
docker run --name "$NAME" --rm --privileged \
  --net host -v /sys/:/sys \
  -v /lib/modules:/lib/modules -v /sys/kernel/debug:/sys/kernel/debug \
  -v /var/run/netns:/var/run/netns -v "$PROJECT":/app/project \
  --entrypoint /bin/bash mn-wifi:v2 \
  -c "service openvswitch-switch start && bash /app/project/scripts/run_step2_inner.sh ${1:-1} \"${2:-congestion heavy handover}\""
RC=$?
[ -n "$SUDO_USER" ] && chown -R "$SUDO_USER": "$PROJECT/logs"
echo "STEP2 FINISHED rc=$RC, logs in $PROJECT/logs/step2"
