#!/bin/bash
#SBATCH --job-name=pam4-gm-switch64-retry
#SBATCH --array=84,86%2
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:30:00
set -euo pipefail
: "${PAM4_DRIVE_PACKAGE:?Set reviewed retry package path}"
: "${PAM4_DRIVE_RUN_ROOT:?Set a separate endpoint retry campaign directory}"
: "${PAM4_DRIVE_APPROVAL:?Set the endpoint retry approval}"
: "${PAM4_PDK_ROOT:?Set the existing private model root}"
: "${SLURM_ARRAY_TASK_ID:?Select 84 or 86}"
case "$SLURM_ARRAY_TASK_ID" in
  84|86) ;;
  *) echo 'Only SWITCH64 indices 84 and 86 can use this wrapper' >&2; exit 2 ;;
esac
test -d "$PAM4_DRIVE_RUN_ROOT"
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
exec /usr/bin/python3.11 -B "$PAM4_DRIVE_PACKAGE/gm_switch64_retry.py" --mode run \
  --index "$SLURM_ARRAY_TASK_ID" --root "$PAM4_DRIVE_RUN_ROOT" \
  --model-root "$PAM4_PDK_ROOT" --approval "$PAM4_DRIVE_APPROVAL"
