# mn-wifi:v2 = official Mininet-WiFi image (v1) + RYU controller + project tools
FROM mn-wifi:v1

# RYU 4.34 is unmaintained; pin old build/runtime deps it still relies on:
#  - setuptools<68: RYU's setup.py calls easy_install.get_script_args (removed in 68)
#  - --no-build-isolation: make pip build RYU with the pinned setuptools, not the latest
#  - eventlet 0.30.2: newer releases removed eventlet.wsgi.ALREADY_HANDLED
RUN python3 -m pip install "setuptools<68" wheel \
 && python3 -m pip install --no-build-isolation ryu \
 && python3 -m pip install "eventlet==0.30.2"

# Restore Mininet-WiFi's `mn` (plain Mininet's overwrote it), so `mn --wifi` works
RUN install -m 755 /app/mininet-wifi/bin/mn /usr/local/bin/mn

# iperf3 for the upcoming traffic-generation experiments
RUN apt-get update && apt-get install -y iperf3 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/project
