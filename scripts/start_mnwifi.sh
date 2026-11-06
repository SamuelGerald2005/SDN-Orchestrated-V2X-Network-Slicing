#!/bin/bash
# Opens an interactive shell in the testbed container, with this project mounted at /app/project.
# For the manual two-terminal workflow (see README). Needs the mn-wifi:v2 image (scripts/build_images.sh).
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
xhost +local:docker > /dev/null 2>&1   # lets the container open the live Mininet-WiFi plot (optional)
sudo docker run -it --rm --privileged --env="DISPLAY" --env="QT_X11_NO_MITSHM=1" \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw --net host -v /sys/:/sys \
  -v /lib/modules:/lib/modules -v /sys/kernel/debug:/sys/kernel/debug \
  -v /var/run/netns:/var/run/netns -v "$PROJECT":/app/project \
  --entrypoint /bin/bash mn-wifi:v2 \
  -c "service openvswitch-switch start && bash"
