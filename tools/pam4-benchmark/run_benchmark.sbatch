#!/usr/bin/env bash
#SBATCH --job-name=ecen720-pam4-bench
#SBATCH --partition=adademic
#SBATCH --qos=olympus-academic
#SBATCH --account=all
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=02:00:00
#SBATCH --no-requeue
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err
#SBATCH --export=ALL

set -eo pipefail

mode="${1:?Pass matched or aps as the batch script argument}"
cpus="${SLURM_CPUS_PER_TASK:?Submit with an explicit CPU count}"
spectre_args=(-64 bench.scs -format psfascii -raw raw +log spectre.log +lqtimeout 30)

case "$mode" in
    matched)
        if (( cpus != 1 )); then
            echo 'matched mode requires --cpus-per-task=1' >&2
            exit 2
        fi
        ;;
    aps)
        if (( cpus < 1 )); then
            echo 'aps mode requires at least 1 allocated CPU' >&2
            exit 2
        fi
        spectre_args+=(+aps "+mt=$cpus")
        ;;
    *)
        echo 'Pass matched or aps as the batch script argument' >&2
        exit 2
        ;;
esac

cd "${SLURM_SUBMIT_DIR:?}"
test -s bench.scs
test ! -e raw
test ! -e spectre.log
mkdir .benchmark_started

unset OA_HOME LD_LIBRARY_PATH
source /opt/coe/cadence/IC231/setup.IC231.linux.bash
export PATH="/opt/coe/cadence/SPECTRE/tools.lnx86/bin:$PATH"
export LC_ALL=C

{
    printf 'MODE=%s\nSLURM_CPUS_PER_TASK=%s\nSLURM_MEM_PER_NODE=%s\n' \
        "$mode" "$cpus" "${SLURM_MEM_PER_NODE:-unknown}"
    hostname
    grep -F 'Cpus_allowed_list:' "/proc/$$/status"
    sha256sum bench.scs
    printf 'COMMAND='
    printf ' %q' spectre "${spectre_args[@]}"
    printf '\n'
} > benchmark_metadata.txt

TIMEFORMAT='SPECTRE_WALL_S=%R SPECTRE_USER_S=%U SPECTRE_SYS_S=%S'
if { time spectre "${spectre_args[@]}" > spectre_console.log 2>&1; } 2> timing.txt; then
    cat timing.txt
else
    status=$?
    cat timing.txt >&2
    echo "Spectre exited with status $status" >&2
    exit "$status"
fi

grep -E 'spectre completes with 0 errors' spectre.log
test -d raw
echo "ECEN720_BENCHMARK_COMPLETE; results in $PWD"
