#!/usr/bin/env python3
"""Per-slice UDP probe. The destination port selects the slice, so unlike ping
(best effort) this measures RTT, jitter and loss inside a slice.

  udp_probe.py server --port 5000
  udp_probe.py client --dst 10.0.0.11 --port 5000 --size 200 --pps 100 --dur 60 --out f.csv

Replies carry only the 12-byte header: both directions share one meter, so full
size echoes would use up the slice budget twice.
CSV columns: seq, t_send (Unix time), rtt_ms (empty if no reply arrived).
With --live FILE, a JSON summary of the last second is rewritten every second for
the dashboard (packets sent 1.5 to 0.5 s ago, so replies have had time to arrive).
"""
import argparse
import json
import os
import select
import socket
import struct
import time

HEADER = struct.Struct('!Id')


def server(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', args.port))
    while True:
        data, addr = sock.recvfrom(65535)
        try:
            sock.sendto(data[:HEADER.size], addr)
        except OSError:
            pass    # e.g. no route while the peer is mid-handover


def client(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    padding = b'\0' * max(args.size - HEADER.size, 0)
    interval = 1.0 / args.pps
    sent, rtt = {}, {}
    seq = 0
    start = time.time()
    stop_sending = start + args.dur
    next_send = start
    deadline = stop_sending + 2     # late replies still count
    next_live = start + 1.5

    while True:
        now = time.time()
        if now >= deadline:
            break
        if args.live and now >= next_live:
            write_live(args, sent, rtt, seq, now)
            next_live += 1.0
        if now < stop_sending and now >= next_send:
            sent[seq] = now
            try:
                sock.sendto(HEADER.pack(seq, now) + padding, (args.dst, args.port))
            except OSError:
                pass    # counted as sent and lost
            seq += 1
            next_send += interval
            continue
        wait = max(0.0, (next_send if now < stop_sending else deadline) - now)
        ready, _, _ = select.select([sock], [], [], min(wait, 0.05))
        if ready:
            while True:
                try:
                    data = sock.recv(65535)
                except OSError:
                    break
                got, t_sent = HEADER.unpack(data[:HEADER.size])
                rtt.setdefault(got, (time.time() - t_sent) * 1000)

    with open(args.out, 'w') as f:
        f.write('seq,t_send,rtt_ms\n')
        for i in range(seq):
            f.write('%d,%.6f,%s\n' % (i, sent[i], '%.3f' % rtt[i] if i in rtt else ''))


def write_live(args, sent, rtt, seq, now):
    window = [i for i in range(max(0, seq - int(args.pps * 3) - 1), seq)
              if now - 1.5 <= sent[i] < now - 0.5]
    got = sorted(rtt[i] for i in window if i in rtt)
    summary = {'t': round(now, 2), 'flow': args.name, 'dst': args.dst, 'port': args.port,
               'sent': len(window), 'received': len(got),
               'loss_pct': round(100.0 * (1 - len(got) / len(window)), 2) if window else None,
               'kbps': round(len(got) * args.size * 8 / 1000.0, 1),
               'rtt_p50': round(got[len(got) // 2], 3) if got else None,
               'rtt_p95': round(got[min(int(len(got) * 0.95), len(got) - 1)], 3) if got else None,
               'rtt_max': round(got[-1], 3) if got else None}
    tmp = args.live + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(summary, f)
    os.replace(tmp, args.live)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['server', 'client'])
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--dst')
    parser.add_argument('--size', type=int, default=200)
    parser.add_argument('--pps', type=float, default=100)
    parser.add_argument('--dur', type=float, default=60)
    parser.add_argument('--out')
    parser.add_argument('--live', help='JSON file for per-second dashboard stats')
    parser.add_argument('--name', default='', help='flow name shown on the dashboard')
    args = parser.parse_args()
    (server if args.mode == 'server' else client)(args)
