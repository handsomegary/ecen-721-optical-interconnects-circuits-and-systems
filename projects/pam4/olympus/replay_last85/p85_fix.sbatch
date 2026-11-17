#!/usr/bin/env bash
#SBATCH --job-name=pam4-last85
#SBATCH --partition=adademic
#SBATCH --qos=olympus-academic
#SBATCH --account=all
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --no-requeue
#SBATCH --output=slurm-p85-%j.log
set -eo pipefail
umask 077
cd "${SLURM_SUBMIT_DIR:?}"
sha256sum --quiet -c SHA256SUMS
unset OA_HOME LD_LIBRARY_PATH PYTHONOPTIMIZE
export PYTHONDONTWRITEBYTECODE=1 LC_ALL=C
source "${CADENCE_SETUP:?}"
export PATH="${SPECTRE_BIN:?}:$PATH"
P85_WORKERS=2 P85_WALL_S=9000 /usr/bin/python3.11 p85.py
