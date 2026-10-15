#!/usr/bin/env python3
"""Replay one scenario trace against a running dllama-api and record streaming timing.

For each selected pair of the trace (Python standard library only):
  pair mode: send A, then send B right after A ("together", S1) or when A's Nth
             streamed chunk arrives ("after_tokens", S2/S3). dllama-api serves one
             request at a time, so B waits in the server's listen queue until A is done.
  solo mode (--solo): afterwards send A alone, then B alone, as the slowdown reference.
Requests use stream=true, temperature 0 and seed 42 with dllama's native behavior:
generation stops at the end-of-sequence token, so max_tokens is only an upper bound.
A chunk is usually one token, but dllama's EOS detector can hold back a piece and send
it with the next one, so exact output token counts are computed later (analyze.py).
Times are time.monotonic_ns() on the machine running this client (the root node);
one JSON line is written per request.

  python scripts/client.py --trace benchmark/traces/s1.jsonl --port 30000 \
      --out results.jsonl --rep 1 --pairs 1-10 --solo
"""
import argparse
import http.client
import json
import sys
import threading
import time


def parse_pairs(text):
    selected = set()
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        selected.update(range(int(lo), int(hi or lo) + 1))
    return selected


class Request:
    def __init__(self, args, spec, meta):
        self.args = args
        self.spec = spec
        self.record = dict(meta, id=spec["id"], source=spec["source"],
                           prompt_tokens=spec["prompt_tokens"], max_tokens=spec["max_tokens"])
        self.conn = None
        self.thread = None

    def send(self):
        body = {"messages": self.spec["messages"], "max_tokens": self.spec["max_tokens"],
                "stream": True, "temperature": self.args.temperature, "seed": self.args.seed}
        data = json.dumps(body).encode("utf-8")
        self.conn = http.client.HTTPConnection("127.0.0.1", self.args.port, timeout=self.args.timeout)
        self.conn.connect()
        self.record["t_send"] = time.monotonic_ns()
        self.conn.request("POST", "/v1/chat/completions", body=data,
                          headers={"Content-Type": "application/json"})

    def read(self, on_token=None):
        times, pieces = [], []
        try:
            response = self.conn.getresponse()
            self.record["http_status"] = response.status
            self.record["t_headers"] = time.monotonic_ns()
            while True:
                line = response.readline()
                if not line:
                    break
                now = time.monotonic_ns()
                line = line.strip()
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    break
                choice = json.loads(payload)["choices"][0]
                if choice.get("finish_reason"):
                    self.record["finish_reason"] = choice["finish_reason"]
                    continue
                times.append(now)
                pieces.append((choice.get("delta") or {}).get("content", ""))
                if on_token is not None:
                    on_token(len(times))
        except Exception as error:  # keep the partial record, mark it as failed
            self.record["error"] = repr(error)
        finally:
            self.conn.close()
        self.record["t_chunks"] = times
        self.record["n_chunks"] = len(times)
        self.record["text"] = "".join(pieces)
        self.record["ok"] = ("error" not in self.record and self.record.get("http_status") == 200
                             and len(times) > 0)

    def start_reader(self, on_token=None):
        self.thread = threading.Thread(target=self.read, args=(on_token,))
        self.thread.start()


def run_pair(args, pair, rep, out):
    meta = {"scenario": pair["scenario"], "pair": pair["pair"], "warmup": pair["warmup"],
            "rep": rep, "mode": "pair", "arrival": pair["arrival"]["type"]}
    a = Request(args, pair["A"], dict(meta, role="A"))
    b = Request(args, pair["B"], dict(meta, role="B"))
    t0 = time.monotonic_ns()
    trigger = threading.Event()
    arrival = pair["arrival"]
    if arrival["type"] == "after_tokens":
        wanted = arrival["tokens"]

        def on_a_token(n):
            if n == wanted:
                trigger.set()

        a.send()
        a.start_reader(on_a_token)
        while not trigger.wait(1.0):
            if not a.thread.is_alive():  # A ended (or failed) before its trigger chunk
                break
        # B must arrive while A is still decoding; otherwise this pair is not the scenario.
        b.record["trigger_fired"] = trigger.is_set()
    else:  # together: A is sent first, B right after, so the server's FIFO order is A, B
        a.send()
        a.start_reader()
    b.send()
    b.start_reader()
    a.thread.join()
    b.thread.join()
    for r in (a, b):
        r.record["t0"] = t0
        if arrival["type"] == "after_tokens":
            r.record["trigger_chunks"] = arrival["tokens"]
        out.write(json.dumps(r.record, ensure_ascii=False) + "\n")
    out.flush()
    return a.record["ok"] and b.record["ok"]


def run_solo(args, pair, rep, out):
    ok = True
    for role in ("A", "B"):
        meta = {"scenario": pair["scenario"], "pair": pair["pair"], "warmup": pair["warmup"],
                "rep": rep, "mode": "solo", "arrival": "solo", "role": role}
        r = Request(args, pair[role], meta)
        r.record["t0"] = time.monotonic_ns()
        r.send()
        r.read()
        out.write(json.dumps(r.record, ensure_ascii=False) + "\n")
        out.flush()
        ok = ok and r.record["ok"]
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--out", required=True, help="JSON-lines file to append to")
    parser.add_argument("--rep", type=int, required=True)
    parser.add_argument("--pairs", required=True, help='pair numbers, e.g. "0" or "1-10"')
    parser.add_argument("--solo", action="store_true", help="also run A and B alone after each pair")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=float, default=7200.0)
    args = parser.parse_args()

    selected = parse_pairs(args.pairs)
    with open(args.trace, encoding="utf-8") as f:
        pairs = [p for p in map(json.loads, f) if p["pair"] in selected]
    failures = 0
    with open(args.out, "a", encoding="utf-8") as out:
        for pair in pairs:
            ok = run_pair(args, pair, args.rep, out)
            if args.solo:
                ok = run_solo(args, pair, args.rep, out) and ok
            failures += 0 if ok else 1
            print(f"{pair['scenario']} pair {pair['pair']} rep {args.rep}: {'ok' if ok else 'FAILED'}", flush=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
