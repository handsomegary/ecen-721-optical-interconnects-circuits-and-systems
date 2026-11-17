#!/usr/bin/env bash
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
cd "${SLURM_SUBMIT_DIR:?}"
test -f input.scs
test -f measurement_config.il
test -f measure_transient.ocn
test ! -e input.raw
test ! -e measurements.csv
mkdir .run_started

unset OA_HOME LD_LIBRARY_PATH
source /opt/coe/cadence/IC231/setup.IC231.linux.bash
export PATH="/opt/coe/cadence/SPECTRE/tools.lnx86/bin:$PATH"
export ECEN720_RUN_DIR="$PWD"

spectre input.scs > spectre.log 2>&1
grep -E 'spectre completes with 0 errors' spectre.log
ocean -nograph -restore "$ECEN720_RUN_DIR/measure_transient.ocn" </dev/null > ocean_read.log 2>&1
grep -F 'ECEN720_MEASURE_PASS:' ocean_read.log
test -s measurements.csv.tmp
mv measurements.csv.tmp measurements.csv
echo "ECEN720_LONG_BATCH_COMPLETE; results in $PWD"
