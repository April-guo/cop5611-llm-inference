#!/usr/bin/env bash
# Submit the full native-queue matrix as one dependency chain, one job per
# (model, TP, scenario): 8B TP 1,2,4,8, then 70B TP 4,8; each with S1, S2, S3.
# Each job waits for the previous one to end (afterany), so only one of our jobs
# runs at a time and a failed job does not block the rest.
# 5 repetitions x 10 pairs, with solo runs. Time limits are ~1.5-2x the pilot timing.
# Run from the experiment directory:
#   cd /blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama/exp && bash scripts/submit_native_all.sh

set -euo pipefail
P=/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama
BUILD=${BUILD:-$P/build/dllama-4d67814}
LOG=$P/results/native/SUBMITTED.txt
[ -x "$BUILD/dllama-api" ] || { echo "no build at $BUILD" >&2; exit 1; }
mkdir -p "$(dirname "$LOG")"

declare -A LIMIT=(
    [8b:s1]=01:00:00  [8b:s2]=03:00:00  [8b:s3]=02:00:00
    [70b:s1]=03:00:00 [70b:s2]=10:00:00 [70b:s3]=05:00:00
)

prev=
echo "# submitted $(date -Is) build=$BUILD" >> "$LOG"
for config in 8b:1 8b:2 8b:4 8b:8 70b:4 70b:8; do
    model=${config%%:*}
    tp=${config##*:}
    for scenario in s1 s2 s3; do
        dep=()
        [ -n "$prev" ] && dep=(--dependency=afterany:$prev)
        prev=$(MODEL=$model SCENARIOS=$scenario REPS=5 PAIRS=1-10 SOLO=1 BUILD=$BUILD \
            sbatch --parsable "${dep[@]}" --nodes="$tp" --time="${LIMIT[$model:$scenario]}" \
            --job-name="n-$model-tp$tp-$scenario" scripts/run_native.sbatch)
        echo "$prev $model tp=$tp $scenario time=${LIMIT[$model:$scenario]}" | tee -a "$LOG"
    done
done
