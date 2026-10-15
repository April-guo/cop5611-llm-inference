#!/usr/bin/env python3
"""Build the request traces for scenarios S1-S3 (see docs/reproducibility.md, section 8).

  S1: A and B are short prompts with 128-token outputs; A is sent, then B right after it.
  S2: A is a short prompt with a 128-token output; B is a 3,000-token LongBench prompt
      with a 128-token output, sent when the client receives A's 16th token.
  S3: A is a short prompt with a 1024-token output; B is a short prompt with a 128-token
      output, sent when the client receives A's 16th token.

Each scenario has 1 warm-up pair (pair 0) and 10 measured pairs; every prompt is distinct.
Short prompts are the first user turn of a ShareGPT conversation, 32-256 tokens. Long
prompts are LongBench v1 qasper and gov_report records in a fixed instruction template,
truncated in the middle to 3,000 tokens (LongBench's truncation method). Token counts come
from dllama's own tokenizer (scripts/dllama_tokenize.cpp) and cover the message content
only; the Llama 3 chat template adds about 10 tokens. Random choices use one seeded RNG.

  python scripts/make_traces.py --sharegpt <ShareGPT_V3_unfiltered_cleaned_split.json> \
      --longbench <longbench/data> --tokenize-bin <dllama_tokenize> \
      --tokenizer <dllama_tokenizer_*.t> --out benchmark/traces
"""
import argparse
import json
import os
import random
import subprocess
import tempfile

SEED = 42
PAIRS = 10
WARMUP_PAIRS = 1
SHORT_MIN_TOKENS, SHORT_MAX_TOKENS = 32, 256
LONG_TOKENS = 3000
SHORT_OUTPUT, LONG_OUTPUT = 128, 1024
TRIGGER_TOKENS = 16
# Character pre-filters, so the slow tokenizer only sees plausible candidates.
SHORT_MIN_CHARS, SHORT_MAX_CHARS = 64, 2000
LONG_MIN_CHARS = 16000   # about 4,000 tokens, always longer than LONG_TOKENS
LONG_KEEP_CHARS = 9000   # kept from each end; the token-level cut falls inside the removed middle

LONGBENCH_TEMPLATES = {
    "qasper": "Read the article and answer the question as concisely as you can.\n\n"
              "Article: {context}\n\nQuestion: {input}\n\nAnswer:",
    "gov_report": "Read the government report and write a one-page summary of it.\n\n"
                  "Report:\n{context}\n\nNow write a one-page summary of the report.\n\nSummary:",
}


def run_tokenizer(args, mode, items):
    """Run dllama_tokenize on a list of {"id", "text", ...} dicts; return results by id."""
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = os.path.join(tmp, "in.jsonl"), os.path.join(tmp, "out.jsonl")
        with open(src, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        subprocess.run([args.tokenize_bin, args.tokenizer, mode, src, dst],
                       check=True, stdout=subprocess.DEVNULL)
        with open(dst, encoding="utf-8") as f:
            return {r["id"]: r for r in map(json.loads, f)}


def short_prompts(args, rng, count):
    with open(args.sharegpt, encoding="utf-8") as f:
        conversations = json.load(f)
    candidates, seen = [], set()
    for conversation in conversations:
        turns = conversation.get("conversations") or []
        if not turns or turns[0].get("from") != "human":
            continue
        text = (turns[0].get("value") or "").strip()
        if not SHORT_MIN_CHARS <= len(text) <= SHORT_MAX_CHARS or "<|" in text or text in seen:
            continue
        seen.add(text)
        candidates.append((conversation["id"], text))
    rng.shuffle(candidates)

    chosen = []
    for start in range(0, len(candidates), 500):
        batch = candidates[start:start + 500]
        counts = run_tokenizer(args, "count", [{"id": str(i), "text": t} for i, (_, t) in enumerate(batch)])
        for i, (conversation_id, text) in enumerate(batch):
            n = counts[str(i)]["n_tokens"]
            if SHORT_MIN_TOKENS <= n <= SHORT_MAX_TOKENS:
                chosen.append({"source": f"sharegpt:{conversation_id}", "content": text, "prompt_tokens": n})
                if len(chosen) == count:
                    return chosen
    raise SystemExit(f"only {len(chosen)} short prompts found, need {count}")


def long_prompts(args, rng, count):
    candidates = []
    for task, template in LONGBENCH_TEMPLATES.items():
        with open(os.path.join(args.longbench, f"{task}.jsonl"), encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                text = template.format(context=record["context"], input=record["input"])
                if len(text) >= LONG_MIN_CHARS and "<|" not in text:
                    candidates.append((f"longbench:{task}:{record['_id']}", text))
    rng.shuffle(candidates)
    picked = candidates[:count]
    if len(picked) < count:
        raise SystemExit(f"only {len(picked)} long prompts found, need {count}")
    items = [{"id": str(i), "text": t[:LONG_KEEP_CHARS] + t[-LONG_KEEP_CHARS:], "max_tokens": LONG_TOKENS}
             for i, (_, t) in enumerate(picked)]
    results = run_tokenizer(args, "truncate", items)
    prompts = []
    for i, (source, _) in enumerate(picked):
        r = results[str(i)]
        if r["n_tokens_before"] <= LONG_TOKENS or r["n_tokens"] < LONG_TOKENS - 10:
            raise SystemExit(f"{source}: unexpected token counts {r['n_tokens_before']} -> {r['n_tokens']}")
        prompts.append({"source": source, "content": r["text"], "prompt_tokens": r["n_tokens"]})
    return prompts


def request(scenario, pair, role, prompt, max_tokens):
    return {"id": f"{scenario}-p{pair:02d}-{role}", "source": prompt["source"],
            "messages": [{"role": "user", "content": prompt["content"]}],
            "prompt_tokens": prompt["prompt_tokens"], "max_tokens": max_tokens}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sharegpt", required=True)
    parser.add_argument("--longbench", required=True, help="directory with qasper.jsonl and gov_report.jsonl")
    parser.add_argument("--tokenize-bin", required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    rng = random.Random(SEED)
    n = WARMUP_PAIRS + PAIRS
    short = iter(short_prompts(args, rng, 5 * n))   # S1 uses 2 per pair, S2 1, S3 2
    long = iter(long_prompts(args, rng, n))
    together = {"type": "together"}
    after = {"type": "after_tokens", "request": "A", "tokens": TRIGGER_TOKENS}

    traces = {"s1": [], "s2": [], "s3": []}
    for p in range(n):
        traces["s1"].append({"scenario": "s1", "pair": p, "warmup": p < WARMUP_PAIRS, "arrival": together,
                             "A": request("s1", p, "A", next(short), SHORT_OUTPUT),
                             "B": request("s1", p, "B", next(short), SHORT_OUTPUT)})
    for p in range(n):
        traces["s2"].append({"scenario": "s2", "pair": p, "warmup": p < WARMUP_PAIRS, "arrival": after,
                             "A": request("s2", p, "A", next(short), SHORT_OUTPUT),
                             "B": request("s2", p, "B", next(long), SHORT_OUTPUT)})
    for p in range(n):
        traces["s3"].append({"scenario": "s3", "pair": p, "warmup": p < WARMUP_PAIRS, "arrival": after,
                             "A": request("s3", p, "A", next(short), LONG_OUTPUT),
                             "B": request("s3", p, "B", next(short), SHORT_OUTPUT)})

    os.makedirs(args.out, exist_ok=True)
    for scenario, pairs in traces.items():
        with open(os.path.join(args.out, f"{scenario}.jsonl"), "w", encoding="utf-8") as f:
            for pair in pairs:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")
    with open(os.path.join(args.out, "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump({"seed": SEED, "pairs_per_scenario": PAIRS, "warmup_pairs": WARMUP_PAIRS,
                   "short_prompt_tokens": [SHORT_MIN_TOKENS, SHORT_MAX_TOKENS],
                   "long_prompt_tokens": LONG_TOKENS, "short_output": SHORT_OUTPUT,
                   "long_output": LONG_OUTPUT, "trigger_tokens": TRIGGER_TOKENS,
                   "longbench_templates": LONGBENCH_TEMPLATES,
                   "sharegpt": args.sharegpt, "longbench": args.longbench, "tokenizer": args.tokenizer},
                  f, indent=2, ensure_ascii=False)
        f.write("\n")
    for scenario, pairs in traces.items():
        a = [x["A"]["prompt_tokens"] for x in pairs]
        b = [x["B"]["prompt_tokens"] for x in pairs]
        print(f"{scenario}: {len(pairs)} pairs; A prompt tokens {min(a)}-{max(a)}; B prompt tokens {min(b)}-{max(b)}")


if __name__ == "__main__":
    main()
