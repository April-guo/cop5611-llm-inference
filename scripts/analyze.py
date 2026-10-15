#!/usr/bin/env python3
"""Summarize run_native results: TTFT, TPOT, TTLT, output length, throughput, slowdown.

Reads results/native/<model>-tp<N>/<jobid>/s*.jsonl (written by scripts/client.py),
skips warm-up pairs and failed requests, and reports per model, TP, scenario and
request role (A or B) for the pair runs:
  - median and P99 of TTFT, TPOT and TTLT (ms);
  - median output length in tokens;
  - median slowdown = pair TTLT / solo TTLT of the same request and repetition;
  - median pair throughput = output tokens of A and B / (A's send to the last chunk).
dllama stops at the end-of-sequence token, so output lengths vary. With --tokenize-bin
and --tokenizer, output tokens are counted with dllama's own tokenizer
(scripts/dllama_tokenize); otherwise the number of streamed chunks is used.
TPOT = (last chunk - first chunk) / (output tokens - 1).
In S2/S3 a pair counts only if B was sent while A was still decoding (trigger_fired).
Python standard library only.

  python scripts/analyze.py results/native [--csv summary.csv] \
      [--tokenize-bin scripts/dllama_tokenize --tokenizer <dllama_tokenizer_*.t>]
"""
import argparse
import csv
import glob
import json
import os
import statistics
import subprocess
import sys
import tempfile


def percentile(values, q):
    """Linear interpolation between closest ranks (same as numpy's default)."""
    xs = sorted(values)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q / 100.0
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def median(values):
    values = list(values)
    return statistics.median(values) if values else float("nan")


def count_tokens(records, tokenize_bin, tokenizer):
    """Set r["n_out"] for every record, with dllama's tokenizer if available."""
    if not tokenize_bin:
        for r in records:
            r["n_out"] = r["n_chunks"]
        return "streamed chunks"
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in.jsonl"), os.path.join(tmp, "out.jsonl")
        with open(src, "w", encoding="utf-8") as f:
            for i, r in enumerate(records):
                f.write(json.dumps({"id": str(i), "text": r["text"]}, ensure_ascii=False) + "\n")
        subprocess.run([tokenize_bin, tokenizer, "count", src, dst], check=True, stdout=subprocess.DEVNULL)
        with open(dst, encoding="utf-8") as f:
            counts = {c["id"]: c["n_tokens"] for c in map(json.loads, f)}
    for i, r in enumerate(records):
        r["n_out"] = counts[str(i)]
    return "dllama tokenizer"


def timing(r):
    t = r["t_chunks"]
    ttft = (t[0] - r["t_send"]) / 1e6
    ttlt = (t[-1] - r["t_send"]) / 1e6
    tpot = (t[-1] - t[0]) / 1e6 / (r["n_out"] - 1) if r["n_out"] > 1 else float("nan")
    return ttft, tpot, ttlt


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", help="results/native directory")
    parser.add_argument("--csv", help="write the summary table to this CSV file")
    parser.add_argument("--tokenize-bin", help="scripts/dllama_tokenize binary")
    parser.add_argument("--tokenizer", help="dllama tokenizer .t file (needed with --tokenize-bin)")
    args = parser.parse_args()

    records, n_failed = [], 0
    for path in sorted(glob.glob(os.path.join(args.root, "*-tp*", "*", "s*.jsonl"))):
        model, tp = os.path.basename(os.path.dirname(os.path.dirname(path))).split("-tp")
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r["warmup"]:
                continue
            if not r["ok"]:
                n_failed += 1
                continue
            r["model"], r["tp"] = model, int(tp)
            records.append(r)
    if not records:
        sys.exit("no results found")
    counted_with = count_tokens(records, args.tokenize_bin, args.tokenizer)

    # Pairs where B did not arrive while A was decoding are not the scenario.
    pairs, invalid = {}, set()
    for r in records:
        if r["mode"] != "pair":
            continue
        key = (r["model"], r["tp"], r["scenario"], r["pair"], r["rep"])
        pairs.setdefault(key, []).append(r)
        if r.get("trigger_fired") is False:
            invalid.add(key)

    solo = {(r["model"], r["tp"], r["id"], r["rep"]): timing(r)[2] for r in records if r["mode"] == "solo"}
    groups, throughput = {}, {}
    for key, rs in pairs.items():
        if key in invalid or len(rs) != 2:
            continue
        model, tp, scenario = key[:3]
        for r in rs:
            groups.setdefault((model, tp, scenario, r["role"]), []).append(r)
        start = min(r["t_send"] for r in rs)
        end = max(r["t_chunks"][-1] for r in rs)
        throughput.setdefault((model, tp, scenario), []).append(sum(r["n_out"] for r in rs) / ((end - start) / 1e9))

    header = ["model", "tp", "scenario", "role", "n", "out_tokens_median", "ttft_median_ms", "ttft_p99_ms",
              "tpot_median_ms", "tpot_p99_ms", "ttlt_median_ms", "ttlt_p99_ms", "slowdown_median",
              "pair_throughput_median_tok_s"]
    rows = []
    for key in sorted(groups):
        model, tp, scenario, role = key
        rs = groups[key]
        t = [timing(r) for r in rs]
        slowdown = [timing(r)[2] / solo[(model, tp, r["id"], r["rep"])]
                    for r in rs if (model, tp, r["id"], r["rep"]) in solo]
        rows.append({
            "model": model, "tp": tp, "scenario": scenario, "role": role, "n": len(rs),
            "out_tokens_median": median(r["n_out"] for r in rs),
            "ttft_median_ms": median(x[0] for x in t), "ttft_p99_ms": percentile([x[0] for x in t], 99),
            "tpot_median_ms": median(x[1] for x in t), "tpot_p99_ms": percentile([x[1] for x in t], 99),
            "ttlt_median_ms": median(x[2] for x in t), "ttlt_p99_ms": percentile([x[2] for x in t], 99),
            "slowdown_median": median(slowdown),
            "pair_throughput_median_tok_s": median(throughput.get((model, tp, scenario), [])),
        })

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for row in rows:
        print("| " + " | ".join(f"{row[h]:.1f}" if isinstance(row[h], float) else str(row[h]) for h in header) + " |")
    print(f"\noutput tokens counted with: {counted_with}", file=sys.stderr)
    print(f"pairs excluded because B arrived after A had finished: {len(invalid)}", file=sys.stderr)
    if n_failed:
        print(f"failed requests skipped: {n_failed}", file=sys.stderr)


if __name__ == "__main__":
    main()
