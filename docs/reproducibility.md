# Reproducibility Checklist

Fill in every blank before running formal experiments, and update this file whenever an item changes.

All paths below are under `/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama/` on HiPerGator.

---

## 1. Code

- dllama commit: `59af889085c6c0316a4524a92b42f04caa4bcc6d` (upstream b4rtaz/distributed-llama)
- Commit of our modified dllama (write "none" if unmodified): none (not modified yet)
- Commit of this repository:

## 2. Build

- Partition used for building: hpg-turin
- Compiler version: gcc 12.2.0 (`module load gcc/12.2.0`)
- Conda environment: `envs/dllama-py310` (full package list in `envs/dllama-py310.explicit.txt`)
- sha256 of `dllama`:
- sha256 of `dllama-api`:

> Build once and use the same binaries for all experiments. Load the environment with `source scripts/dllama-env.sh`.

## 3. Models

- 8B source: b4rtaz/Llama-3_1-8B-Q40-Instruct-Distributed-Llama (revision `c4b7e78`)
- 8B file path: `models/llama3_1_8b_instruct_q40/dllama_model_llama3_1_8b_instruct_q40.m`
- 8B sha256: `3d4ea2faf8581a50ce4c6ca3b4467980042618ea471c0c175f6a102ee2f22304`
- 70B source: b4rtaz/Llama-3_3-70B-Q40-Instruct-Distributed-Llama (revision `15da94e`)
- 70B file path: `models/llama3_3_70b_instruct_q40/dllama_model_llama3_3_70b_instruct_q40.m`
- 70B sha256: `0d2d2349fecf99cc9e5e141fde925029a822cedac4b76530ac1a51c484b66aad` (the publisher lists sha256 only for the 11 parts, all of which were checked; this value is for the joined file and was computed by us)
- Tokenizer sha256: `c83472ef1171f5fc2c306cf19b45f1639e6f3c260d5fb6a4888fffe5e86a4220` (the 8B and 70B tokenizers are the same file)

> To verify: in the model directory, run `sha256sum -c SHA256SUMS`.

## 4. Datasets

- ShareGPT source: anon8231489123/ShareGPT_Vicuna_unfiltered (revision `192ab21`)
- ShareGPT file path: `datasets/sharegpt/ShareGPT_V3_unfiltered_cleaned_split.json`
- ShareGPT sha256: `35f0e213ce091ed9b9af2a1f0755e9d39f9ccec34ab281cd4ca60d70f6479ba4`
- LongBench source: zai-org/LongBench, formerly THUDM/LongBench (revision `5e628be`)
- LongBench file path: `datasets/longbench/data/` (extracted from `datasets/longbench/data.zip`)
- LongBench sha256: `cb45b11a4133c6bc1d6a44b0f8e701335ff1e543195db1103472e575857f7f64` (`data.zip`; values for every extracted file are in `datasets/longbench/SHA256SUMS`)
- Subsets used:

> To verify: in the dataset directory, run `sha256sum -c SHA256SUMS`.

## 5. Hardware

- Partition and GPU model: hpg-turin, NVIDIA L4 (23,034 MiB memory)
- GPUs per node:
- Number of nodes:
- CPU cores per node:
- Memory per node:
- Network interface for cross-node traffic:

## 6. Run Parameters

- TP size:
- seed:
- temperature:
- top-p:
- max-seq-len:
- net-turbo:
- buffer-float-type: q80 (required for Q40 models)
- nthreads: 1 (required by the GPU backend)

> By default, dllama picks a different seed on every run and uses temperature 0.8, so these must be set explicitly.

## 7. Output Length

- Tokens generated per request:
- Stop at the end-of-sequence token or not:

> If different configurations generate different lengths, their latencies cannot be compared.

## 8. Workload

- Trace file path:
- Trace sha256:
- Sampling seed:
- Number of requests:
- Arrival process and rate:

## 9. Measurement Method

- Warm-up runs (not counted):
- Repetitions per configuration:
- Statistics reported:

## 10. Records to Save for Every Run

- Job ID, nodes, start and end times
- Full run command
- Driver version
- Other users' jobs on the same nodes
- Location of the result files
