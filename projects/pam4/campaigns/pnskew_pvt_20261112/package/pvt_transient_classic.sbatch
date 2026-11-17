#!/bin/bash
#SBATCH --job-name=pam4-pvt-tran-classic
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=03:00:00
set -euo pipefail
: "${PAM4_STUDY_ROOT:?Use the reviewed package path}"
: "${PAM4_SKEW_ADMISSION:?Use the verified original r5 admission JSON}"
: "${PAM4_RUN_ROOT:?Use a fresh owned campaign directory}"
: "${SLURM_ARRAY_TASK_ID:?Choose case index 0 or 1}"
export LC_ALL=C.UTF-8 LANG=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
python3 -B "$PAM4_STUDY_ROOT/run_case.py" pvt-transient --admission "$PAM4_SKEW_ADMISSION" \
  --case-index "$SLURM_ARRAY_TASK_ID" --run-root "$PAM4_RUN_ROOT" --retire-new-raw
