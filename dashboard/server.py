#!/usr/bin/env python3
"""Serves the dashboard on http://127.0.0.1:8090 (no extra packages needed).
  python3 dashboard/server.py [--port 8090]
Replays work offline from dashboard/recordings. The Live view reads a running
testbed started with scripts/run_live_demo_host.sh (RYU REST on port 8081, traces
in logs/live)."""
import argparse
import glob
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from frames import FrameBuilder, read_json

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(HERE, '..', 'logs', 'live')
builder = FrameBuilder(os.path.join(LIVE, 'trace'), os.path.join(LIVE, 'live'))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')   # always serve the latest files
        super().end_headers()

    def send_json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith('/api/recordings'):
            out = []
            for path in sorted(glob.glob(os.path.join(HERE, 'recordings', '*.json'))):
                rec = read_json(path, {})
                out.append({'file': 'recordings/' + os.path.basename(path),
                            'title': rec.get('title') or os.path.basename(path)[:-5],
                            'setup': rec.get('setup'), 'scenario': rec.get('scenario'),
                            'frames': len(rec.get('frames', []))})
            return self.send_json(out)
        if self.path.startswith('/api/live'):
            frame = builder.frame()
            frame['meta'] = builder.meta()
            return self.send_json(frame)
        return super().do_GET()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8090)
    args = p.parse_args()
    print('V2X dashboard on http://127.0.0.1:%d' % args.port)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
