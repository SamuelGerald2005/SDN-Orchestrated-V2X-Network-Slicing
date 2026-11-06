#!/bin/bash
# Builds the two Docker images the testbed needs. Needs Docker and an internet connection.
#   sudo bash scripts/build_images.sh
#   mn-wifi:v1  official Mininet-WiFi image, with two small fixes to its Dockerfile (see below)
#   mn-wifi:v2  v1 + RYU 4.34 (pinned deps) + iperf3, from docker/Dockerfile
# These are the steps from docs/Environment_Setup_Guide_Part3.pdf (Steps 15 and 16).
# Not needed for the dashboard replay, only for the live testbed and the experiments.
set -e
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${1:-$PROJECT/.build/mininet-wifi}"

if [ ! -d "$WORK/.git" ]; then
  mkdir -p "$(dirname "$WORK")"
  git clone --depth 1 https://github.com/intrig-unicamp/mininet-wifi "$WORK"
fi

# 1. FlightRadarAPI 1.4.1+ needs Python 3.10 (the image has 3.9, so pip installs 1.4.0, whose module is
#    named FlightRadar24); 2. upstream forces the Tk plotting backend at import, which crashes headless.
python3 - "$WORK/Dockerfile" <<'EOF'
import sys
p = sys.argv[1]
text = open(p).read()
fix = ('RUN sed -i "s/from FlightRadarAPI import FlightRadar24API/from FlightRadar24 import FlightRadar24API/" mn_wifi/net.py\n'
       'RUN sed -i "s/matplotlib.use(\'TkAgg\')/matplotlib.use(\'TkAgg\', force=False)/" mn_wifi/telemetry.py\n')
if 'from FlightRadar24 import' in text:
    print('Dockerfile already patched')
else:
    marker = 'RUN util/install.sh -Wlnfv6'
    if marker not in text:
        sys.exit('Could not find "%s" in %s: upstream changed, patch it by hand (see the setup guide)' % (marker, p))
    open(p, 'w').write(text.replace(marker, fix + marker, 1))
    print('Dockerfile patched')
EOF

docker build -t mn-wifi:v1 "$WORK"
docker build -t mn-wifi:v2 "$PROJECT/docker"
echo "Images ready: mn-wifi:v1, mn-wifi:v2"
