#!/bin/bash
#SBATCH --job-name=pam4-c2-paired
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
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
exec /usr/bin/python3.11 -B "${PAM4_C2_PACKAGE:?Use c2_run.py submit}/c2_run.py" run \
  --c0-root "$PAM4_C0_FORMAL_ROOT" --c1-root "$PAM4_C1_ROOT" --c1-approval "$PAM4_C1_APPROVAL" \
  --root "$PAM4_C2_ROOT" --approval "$PAM4_C2_APPROVAL" --review "$PAM4_C2_REVIEW" \
  --review-sha "$PAM4_C2_REVIEW_SHA" --c1-summary-sha "$PAM4_C2_C1_SUMMARY_SHA" \
  --model-root "$PAM4_PDK_ROOT" --index "$SLURM_ARRAY_TASK_ID"
