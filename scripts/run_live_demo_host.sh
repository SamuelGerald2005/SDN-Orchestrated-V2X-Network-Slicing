#!/bin/bash
# Runs on the HOST with sudo: sudo bash run_live_demo_host.sh [setup] [minutes]
# Starts a continuous testbed for the dashboard's Live view. In another terminal:
#   python3 ~/v2x-project/dashboard/server.py   then open http://127.0.0.1:8090
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
NAME=v2x-live
docker rm -f "$NAME" > /dev/null 2>&1
docker run --name "$NAME" --rm --privileged --net host -e MINUTES="${2:-30}" \
  -v /sys/:/sys -v /lib/modules:/lib/modules -v /sys/kernel/debug:/sys/kernel/debug \
  -v /var/run/netns:/var/run/netns -v "$PROJECT":/app/project \
  --entrypoint /bin/bash mn-wifi:v2 \
  -c "service openvswitch-switch start > /dev/null && bash /app/project/scripts/live_demo_inner.sh ${1:-orchestrated}"
[ -n "$SUDO_USER" ] && chown -R "$SUDO_USER": "$PROJECT/logs"
