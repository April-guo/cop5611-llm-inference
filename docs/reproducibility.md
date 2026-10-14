# Reproducibility Checklist

Fill in every blank before running formal experiments, and update this file whenever an item changes.

All paths below are under `/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama/` on HiPerGator.

---

## 1. Code

- dllama commit: `59af889085c6c0316a4524a92b42f04caa4bcc6d` (upstream b4rtaz/distributed-llama)
- Commit of our modified dllama (write "none" if unmodified): `579dc36224e90ef99412c45cf3428d7e33ea1a96` (April-guo/distributed-llama `main`; fixes the uninitialized `Tokenizer::addBos`, so BOS is always added)
- Commit of this repository:

## 2. Build

- Partition used for building: hpg-turin
- Compiler version: gcc 12.2.0 (`module load gcc/12.2.0`)
- Conda environment: `envs/dllama-py310` (full package list in `envs/dllama-py310.explicit.txt`)

> Build once and use the same binaries for all experiments. Load the environment with `source scripts/dllama-env.sh`.

## 3. Models

- 8B source: b4rtaz/Llama-3_1-8B-Q40-Instruct-Distributed-Llama (revision `c4b7e78`)
- 8B file path: `models/llama3_1_8b_instruct_q40/dllama_model_llama3_1_8b_instruct_q40.m`
- 70B source: b4rtaz/Llama-3_3-70B-Q40-Instruct-Distributed-Llama (revision `15da94e`)
- 70B file path: `models/llama3_3_70b_instruct_q40/dllama_model_llama3_3_70b_instruct_q40.m`

## 4. Datasets

- ShareGPT source: anon8231489123/ShareGPT_Vicuna_unfiltered (revision `192ab21`)
- ShareGPT file path: `datasets/sharegpt/ShareGPT_V3_unfiltered_cleaned_split.json`
- LongBench source: zai-org/LongBench, formerly THUDM/LongBench (revision `5e628be`)
- LongBench file path: `datasets/longbench/data/` (extracted from `datasets/longbench/data.zip`)
- Subsets used: LongBench v1 `qasper` and `gov_report`; ShareGPT first user turns (see section 8)

## 5. Hardware

- Partition and GPU model: hpg-turin, NVIDIA L4 (23,034 MiB memory)
- GPUs per node: 1
- Number of nodes: equal to the TP size
- CPU cores per node: 4
- Memory per node: 16 GB
- Network interface for cross-node traffic: `bond0` (the address the node hostname resolves to)

## 6. Run Parameters

- TP size: 8B: 1 (reference), 2, 4, 8; 70B: 4, 8 (70B does not fit in L4 memory at TP 1 or 2)
- seed: 42
- temperature: 0
- top-p: 0.9 (no effect at temperature 0)
- max-seq-len: 4096 (prompt + output must fit; long LongBench prompts need truncation or a larger value)
- net-turbo: 1
- buffer-float-type: q80 (required for Q40 models)
- nthreads: 1 (required by the GPU backend)

> By default, dllama picks a different seed on every run and uses temperature 0.8, so these must be set explicitly.

## 7. Output Length

- Tokens generated per request: 128 for short outputs; 1024 for the long-output request in scenario 3
- Stop at the end-of-sequence token or not: no, always generate exactly this many tokens (needs a small patch to `dllama-api`; not done yet)

> If different configurations generate different lengths, their latencies cannot be compared.

## 8. Workload

- Scenarios: (1) two short requests arrive together; (2) a long-input request arrives while another request is decoding; (3) a short request arrives while another request is generating a long output
- Short prompts: the first user turn of a ShareGPT conversation, 32–256 tokens
- Long prompts: LongBench v1 `qasper` and `gov_report`, truncated in the middle to 3,000 tokens (as LongBench's own evaluation does)
- Token counts: measured with the Llama 3 tokenizer we run
- Trace file path: `benchmark/traces/` (to be generated)
- Sampling seed: 42
- Number of requests: 10 pairs per scenario (2 requests per pair)
- Arrival process and rate: scenario 1, both requests arrive at the same time; scenarios 2 and 3, the second request arrives 1 s after the first one starts

## 9. Measurement Method

- Warm-up runs (not counted): 1 request pair per configuration; model-load time is recorded separately
- Repetitions per configuration: 5 (50 requests per configuration)
- Statistics reported: median and P99 of TTFT, TPOT and TTLT; mean throughput; slowdown = latency when sharing ÷ latency when running alone

## 10. Records to Save for Every Run

- Job ID, nodes, start and end times
- Full run command
- Driver version
- Other users' jobs on the same nodes
- Location of the result files
