#!/bin/bash
#SBATCH --job-name=pam4-c0-fixed
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=01:00:00
set -euo pipefail
: "${PAM4_C0_PACKAGE:?Set C0 executable package path}"
: "${PAM4_C0_RUN_ROOT:?Set C0 campaign directory}"
: "${PAM4_C0_APPROVAL:?Set the fixed-code C0 approval}"
: "${PAM4_C0_SWITCH_PACKAGE:?Set the verified 94aff417 SWITCH64 package}"
: "${PAM4_C0_R5_ORIGINAL:?Set original COMP r5_original directory}"
: "${PAM4_PDK_ROOT:?Set existing private model root}"
: "${SLURM_ARRAY_TASK_ID:?Select approved C0 index 0 through 4}"
case "$SLURM_ARRAY_TASK_ID" in
  0|1|2|3|4) ;;
  *) echo 'C0 index must be 0 through 4' >&2; exit 2 ;;
esac
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
exec /usr/bin/python3.11 -B "$PAM4_C0_PACKAGE/c0_run.py" --mode run \
  --index "$SLURM_ARRAY_TASK_ID" --root "$PAM4_C0_RUN_ROOT" \
  --model-root "$PAM4_PDK_ROOT" --approval "$PAM4_C0_APPROVAL"
