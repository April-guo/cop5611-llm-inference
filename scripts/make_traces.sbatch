#!/usr/bin/env bash
#SBATCH --job-name=make-traces
#SBATCH --account=fsu-compsci-dept
#SBATCH --qos=fsu-compsci-dept
#SBATCH --partition=hpg-default
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama/sbatch-output/make-traces-%j.out
#SBATCH --error=/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama/sbatch-output/make-traces-%j.err

# Build the tokenizer tool and generate benchmark/traces/{s1,s2,s3}.jsonl (CPU only).
# Run from the experiment directory (a copy of this repo):
#   cd /blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama/exp && sbatch scripts/make_traces.sbatch

set -euo pipefail
umask 002
P=/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama
EXP=${SLURM_SUBMIT_DIR:-$PWD}
DLLAMA=$P/distributed-llama
TOOL=$EXP/scripts/dllama_tokenize
source "$P/scripts/dllama-env.sh"

g++ -std=c++11 -O2 -march=native -I"$DLLAMA/src" "$EXP/scripts/dllama_tokenize.cpp" \
    "$DLLAMA/src/tokenizer.cpp" "$DLLAMA/src/nn/nn-quants.cpp" "$DLLAMA/src/nn/nn-core.cpp" \
    "$DLLAMA/src/nn/nn-cpu-ops.cpp" "$DLLAMA/src/nn/llamafile/sgemm.cpp" -o "$TOOL" -lpthread

echo "dllama commit: $(git -c safe.directory="$DLLAMA" -C "$DLLAMA" rev-parse HEAD)"
time python "$EXP/scripts/make_traces.py" \
    --sharegpt "$P/datasets/sharegpt/ShareGPT_V3_unfiltered_cleaned_split.json" \
    --longbench "$P/datasets/longbench/data" \
    --tokenize-bin "$TOOL" \
    --tokenizer "$P/models/llama3_1_8b_instruct_q40/dllama_tokenizer_llama3_1_8b_instruct_q40.t" \
    --out "$EXP/benchmark/traces"
