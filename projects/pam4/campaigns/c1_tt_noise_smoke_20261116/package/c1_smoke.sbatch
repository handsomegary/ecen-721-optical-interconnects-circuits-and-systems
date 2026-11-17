#!/bin/bash
#SBATCH --job-name=pam4-c1-noise
#SBATCH --partition=adademic
#SBATCH --qos=olympus-academic
#SBATCH --account=all
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=05:00:00
#SBATCH --no-requeue

set -eo pipefail
source /opt/coe/cadence/IC231/setup.IC231.linux.bash
export PATH="$HOME/ECEN721/py311bin:/opt/coe/cadence/SPECTRE/tools.lnx86/bin:$PATH"
set -u
: "${PAM4_C1_PACKAGE:?Set the extracted C1 package path}"
: "${PAM4_C1_ROOT:?Set the isolated C1 campaign directory}"
: "${PAM4_C1_APPROVAL:?Set the C1 approval file bound to the campaign}"
: "${PAM4_C0_FORMAL_ROOT:?Set the original formal C0 run root}"
: "${PAM4_C0_FORMAL_PACKAGE:?Set the original formal C0 package path}"
: "${PAM4_PDK_ROOT:?Set the existing private model root}"
: "${SLURM_ARRAY_TASK_ID:?Specify the approved case index with --array}"
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
exec /usr/bin/python3.11 -B "$PAM4_C1_PACKAGE/c1_run.py" run \
  --c0-root "$PAM4_C0_FORMAL_ROOT" --root "$PAM4_C1_ROOT" \
  --approval "$PAM4_C1_APPROVAL" --model-root "$PAM4_PDK_ROOT" \
  --index "$SLURM_ARRAY_TASK_ID"
