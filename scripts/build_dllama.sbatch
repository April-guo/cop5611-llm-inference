#!/usr/bin/env bash
#SBATCH --job-name=dllama-build
#SBATCH --account=fsu-compsci-dept
#SBATCH --qos=fsu-compsci-dept
#SBATCH --partition=hpg-turin
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama/sbatch-output/build-%j.out
#SBATCH --error=/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama/sbatch-output/build-%j.err

# Build dllama and dllama-api (Vulkan) once, from the team fork's current commit, on an
# hpg-turin node: the Makefile uses -march=native, so binaries must be built on the CPU
# type they run on. Every experiment uses these binaries; no job rebuilds.
#   sbatch scripts/build_dllama.sbatch
# Output: build/dllama-<commit>/ with the binaries, the shaders and BUILD_INFO.txt.

set -euo pipefail
umask 002
P=/blue/fsu-compsci-dept/yh26e.fsu/cop5611-dllama
SRC=$P/distributed-llama
G="git -c safe.directory=$SRC -C $SRC"

[ -z "$($G status --porcelain)" ] || { echo "the source tree has local changes" >&2; exit 1; }
COMMIT=$($G rev-parse HEAD)
OUT=$P/build/dllama-${COMMIT:0:7}
[ -e "$OUT" ] && { echo "$OUT already exists" >&2; exit 1; }

source "$P/scripts/dllama-env.sh"
mkdir -p "$OUT"
cp "$SRC/Makefile" "$OUT/"
cp -a "$SRC/src" "$OUT/"
DLLAMA_VULKAN=1 make -C "$OUT" -j "${SLURM_CPUS_PER_TASK:-4}" dllama dllama-api > "$OUT/build.log" 2>&1

{
    echo "commit=$COMMIT"
    echo "origin=$($G remote get-url origin)"
    echo "built_at=$(date -Is)"
    echo "job=${SLURM_JOB_ID:-}"
    echo "node=$(hostname -s)"
    echo "cpu=$(lscpu | sed -n 's/^Model name: *//p')"
    echo "compiler=$(g++ --version | head -1)"
    echo "glslc=$(glslc --version | head -1)"
    echo "command=DLLAMA_VULKAN=1 make dllama dllama-api"
} > "$OUT/BUILD_INFO.txt"
( cd "$OUT" && sha256sum dllama dllama-api src/nn/vulkan/*.spv ) > "$OUT/SHA256SUMS"
chmod a-w "$OUT/dllama" "$OUT/dllama-api"
cat "$OUT/BUILD_INFO.txt"
