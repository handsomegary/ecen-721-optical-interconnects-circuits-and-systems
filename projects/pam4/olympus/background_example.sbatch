#!/usr/bin/env bash
#SBATCH --job-name=ecen720-pam4
#SBATCH --partition=adademic
#SBATCH --qos=olympus-academic
#SBATCH --account=all
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=04:00:00
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err
#SBATCH --export=ALL

set -eo pipefail
: "${PROJECT_BUNDLE_ROOT:?Export PROJECT_BUNDLE_ROOT before sbatch}"
cd "${SLURM_SUBMIT_DIR:?}"
test -f input.scs

unset OA_HOME LD_LIBRARY_PATH
source /opt/coe/cadence/IC231/setup.IC231.linux.bash
export PATH="/opt/coe/cadence/SPECTRE/tools.lnx86/bin:$PATH"

spectre input.scs > spectre.log 2>&1
export PROJECT_RAW_DIR="$PWD/input.raw"
ocean -nograph -restore "$PROJECT_BUNDLE_ROOT/olympus/check_results.ocn" </dev/null > ocean_read.log 2>&1
grep -F 'PAM4_OCEAN_READ_PASS' ocean_read.log
echo "PAM4_BATCH_COMPLETE; results in $PWD"
