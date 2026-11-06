#!/bin/bash
# Runs on the HOST with sudo. Same container settings as ~/start_mnwifi.sh, but
# non-interactive: runs the Step 12 check once and removes the container.
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
NAME=v2x-step12

docker rm -f "$NAME" > /dev/null 2>&1
docker run --name "$NAME" --rm --privileged --env="DISPLAY=${DISPLAY:-:1}" --env="QT_X11_NO_MITSHM=1" \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw --net host -v /sys/:/sys \
  -v /lib/modules:/lib/modules -v /sys/kernel/debug:/sys/kernel/debug \
  -v /var/run/netns:/var/run/netns -v "$PROJECT":/app/project \
  --entrypoint /bin/bash mn-wifi:v2 \
  -c "service openvswitch-switch start && bash /app/project/scripts/verify_step12_inner.sh"
RC=$?

# Logs are written by root in the container; hand them back to the invoking user
[ -n "$SUDO_USER" ] && chown -R "$SUDO_USER": "$PROJECT/logs"
echo "STEP12 FINISHED rc=$RC, logs in $PROJECT/logs/step12"
