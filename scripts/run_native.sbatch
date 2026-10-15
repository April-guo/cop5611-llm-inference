#!/usr/bin/env bash
#SBATCH --job-name=dllama-native
#SBATCH --account=fsu-compsci-dept
#SBATCH --qos=fsu-compsci-dept
#SBATCH --partition=hpg-turin
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:l4:1
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama/sbatch-output/native-%j.out
#SBATCH --error=/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama/sbatch-output/native-%j.err

# Scenarios S1-S3 on dllama's native scheduling (one dllama-api, single-threaded FIFO).
# TP = number of nodes, one L4 per node. Settings follow docs/reproducibility.md.
# Run from the experiment directory (a copy of this repo with benchmark/traces/):
#   MODEL=8b SCENARIOS="s1 s2 s3" REPS=5 PAIRS=1-10 SOLO=1 BUILD=<build dir> \
#       sbatch --nodes=2 scripts/run_native.sbatch
# MODEL: 8b (TP 1, 2, 4, 8) or 70b (TP 4, 8). Results: results/native/<model>-tp<N>/<jobid>/

set -uo pipefail
umask 002
: "${SLURM_JOB_ID:?submit this script with sbatch}"

P=/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama
EXP=${SLURM_SUBMIT_DIR:?}
MODEL=${MODEL:-8b}
SCENARIOS=${SCENARIOS:-"s1 s2 s3"}
REPS=${REPS:-5}
PAIRS=${PAIRS:-1-10}
SOLO=${SOLO:-1}
BUILD=${BUILD:?set BUILD to a build/dllama-<commit> directory}
N=$SLURM_NNODES
W=$((N - 1))
case "$MODEL:$N" in
    8b:1|8b:2|8b:4|8b:8) NAME=llama3_1_8b_instruct_q40 ;;
    70b:4|70b:8) NAME=llama3_3_70b_instruct_q40 ;;
    *) echo "unsupported MODEL=$MODEL with TP=$N (8b: 1,2,4,8; 70b: 4,8)" >&2; exit 1 ;;
esac
MODEL_FILE=$P/models/$NAME/dllama_model_$NAME.m
TOKENIZER=$P/models/$NAME/dllama_tokenizer_$NAME.t
OUT=$P/results/native/$MODEL-tp$N/$SLURM_JOB_ID
WORKER_PORT=$((20000 + SLURM_JOB_ID % 20000))
API_PORT=$((40000 + SLURM_JOB_ID % 20000))
mkdir -p "$OUT"

api_pid=
sampler_pid=
worker_pids=()
cleanup() {
    [ -n "$sampler_pid" ] && kill "$sampler_pid" 2>/dev/null
    [ -n "$api_pid" ] && kill "$api_pid" 2>/dev/null
    # dllama workers never exit on their own; don't wait on their srun steps.
    if [ "${#worker_pids[@]}" -gt 0 ]; then
        kill "${worker_pids[@]}" 2>/dev/null
        sleep 2
        kill -KILL "${worker_pids[@]}" 2>/dev/null
    fi
    echo "finished_at=$(date -Is)" >> "$OUT/run.txt"
}
trap cleanup EXIT
die() { echo "ERROR: $*" | tee -a "$OUT/run.txt" >&2; exit 1; }

source "$P/scripts/dllama-env.sh" || die "cannot load the environment"
[ -x "$BUILD/dllama-api" ] || die "no dllama-api in $BUILD"

# Run record
{
    echo "job=$SLURM_JOB_ID"
    echo "started_at=$(date -Is)"
    echo "model=$MODEL tp=$N scenarios=$SCENARIOS reps=$REPS pairs=$PAIRS solo=$SOLO"
    echo "model_file=$MODEL_FILE"
    echo "build=$BUILD"
    sed 's/^/build_/' "$BUILD/BUILD_INFO.txt"
    echo "exp_dir=$EXP"
    echo "exp_commit=$(git -C "$EXP" rev-parse HEAD 2>/dev/null || echo 'not a git checkout')"
    echo "exp_dirty=$(git -C "$EXP" status --porcelain 2>/dev/null | wc -l)"
    echo "nodes=$SLURM_JOB_NODELIST"
    echo "api_port=$API_PORT worker_port=$WORKER_PORT"
} > "$OUT/run.txt"

# Per-node facts: addresses, CPU, GPU, driver, Vulkan devices, other jobs on the node
srun --nodes="$N" --ntasks="$N" --ntasks-per-node=1 --gres=gpu:l4:1 --output="$OUT/node-%t.txt" bash -c '
    h=$(hostname -s)
    echo "host=$h"
    echo "ip=$(getent ahostsv4 "$h" | awk "NR==1{print \$1}")"
    echo "cpu=$(lscpu | sed -n "s/^Model name: *//p")"
    echo "gpu=$(nvidia-smi --query-gpu=uuid,name,driver_version --format=csv,noheader | tr "\n" ";")"
    echo "vulkan_l4=$(vulkaninfo --summary 2>/dev/null | grep -cE "deviceName *= *NVIDIA L4")"
    echo "cotenant_jobs=$(squeue -w "$h" -h -o "%i:%u:%b" | tr "\n" " ")"
' || die "per-node probe failed"
cat "$OUT"/node-*.txt > "$OUT/nodes.txt"
[ "$(grep -c '^vulkan_l4=1$' "$OUT/nodes.txt")" = "$N" ] || die "not every node sees exactly one L4"
build_cpu=$(sed -n 's/^cpu=//p' "$BUILD/BUILD_INFO.txt")
[ "$(grep '^cpu=' "$OUT/nodes.txt" | sort -u)" = "cpu=$build_cpu" ] || die "node CPU differs from the build CPU ($build_cpu)"

cd "$BUILD" || die "cd $BUILD"
ROOT_NODE=$(hostname -s)
WORKERS=()
for node in $(scontrol show hostnames "$SLURM_JOB_NODELIST"); do
    [ "$node" = "$ROOT_NODE" ] && continue
    srun --nodes=1 --ntasks=1 -w "$node" --gres=gpu:l4:1 --cpus-per-task="${SLURM_CPUS_PER_TASK:-4}" \
        stdbuf -oL -eL ./dllama worker --host 0.0.0.0 --port "$WORKER_PORT" \
        --nthreads 1 --gpu-index 0 --net-turbo 1 > "$OUT/worker-$node.log" 2>&1 &
    worker_pids+=($!)
    WORKERS+=("$(getent ahostsv4 "$node" | awk 'NR==1{print $1}'):$WORKER_PORT")
done
if [ "$W" -gt 0 ]; then
    for i in $(seq 1 300); do
        [ "$(grep -l "Listening on 0.0.0.0:$WORKER_PORT" "$OUT"/worker-*.log 2>/dev/null | wc -l)" = "$W" ] && break
        sleep 1
    done
    [ "$(grep -l "Listening on 0.0.0.0:$WORKER_PORT" "$OUT"/worker-*.log | wc -l)" = "$W" ] || die "workers did not start"
fi

API_ARGS=(--model "$MODEL_FILE" --tokenizer "$TOKENIZER" --buffer-float-type q80 --nthreads 1
          --gpu-index 0 --max-seq-len 4096 --temperature 0 --topp 0.9 --seed 42 --net-turbo 1
          --host 127.0.0.1 --port "$API_PORT")
[ "$W" -gt 0 ] && API_ARGS+=(--workers "${WORKERS[@]}")
echo "api_command=./dllama-api ${API_ARGS[*]}" >> "$OUT/run.txt"
t_launch=$(date +%s.%N)
stdbuf -oL -eL ./dllama-api "${API_ARGS[@]}" > "$OUT/api.log" 2>&1 &
api_pid=$!

# Ready when /v1/models answers (the startup log is not reliable for this).
ready=0
for i in $(seq 1 1800); do
    kill -0 "$api_pid" 2>/dev/null || die "dllama-api exited during startup; see api.log"
    if python -c "import http.client,sys; c=http.client.HTTPConnection('127.0.0.1',$API_PORT,timeout=2); c.request('GET','/v1/models'); sys.exit(c.getresponse().status!=200)" 2>/dev/null; then
        ready=1; break
    fi
    sleep 1
done
[ "$ready" = 1 ] || die "dllama-api not ready after 30 min"
echo "model_load_seconds=$(python -c "print(round($(date +%s.%N) - $t_launch, 1))")" >> "$OUT/run.txt"

nvidia-smi --query-gpu=timestamp,memory.used,utilization.gpu --format=csv,noheader,nounits -lms 500 \
    > "$OUT/root-gpu.csv" 2>&1 &
sampler_pid=$!

status=0
for scenario in $SCENARIOS; do
    trace=$EXP/benchmark/traces/$scenario.jsonl
    [ -f "$trace" ] || die "missing trace $trace"
    python "$EXP/scripts/client.py" --trace "$trace" --port "$API_PORT" --out "$OUT/$scenario.jsonl" \
        --rep 0 --pairs 0 > "$OUT/client-$scenario.log" 2>&1 || status=1        # warm-up pair
    for rep in $(seq 1 "$REPS"); do
        python "$EXP/scripts/client.py" --trace "$trace" --port "$API_PORT" --out "$OUT/$scenario.jsonl" \
            --rep "$rep" --pairs "$PAIRS" $([ "$SOLO" = 1 ] && echo --solo) >> "$OUT/client-$scenario.log" 2>&1 || status=1
    done
done

grep -E 'VmHWM|VmRSS' "/proc/$api_pid/status" 2>/dev/null | sed 's/^/root_api_/; s/:\s*/=/' >> "$OUT/run.txt"
python - "$OUT" <<'PY' | tee -a "$OUT/run.txt"
import glob, json, sys
records = [json.loads(l) for f in glob.glob(sys.argv[1] + "/s*.jsonl") for l in open(f)]
bad = [r["id"] + "/" + r["mode"] + "/rep" + str(r["rep"]) for r in records if not r["ok"]]
print(f"requests={len(records)} ok={len(records) - len(bad)} failed={len(bad)} {' '.join(bad[:10])}")
PY
echo "client_status=$status" >> "$OUT/run.txt"
exit "$status"
