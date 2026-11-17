#!/bin/bash
#SBATCH --job-name=pam4-c0-aligned
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=01:00:00
set -euo pipefail
: "${PAM4_C0_ALIGN_PACKAGE:?Set alignment package path}"
: "${PAM4_C0_ORIGINAL_PACKAGE:?Set original C0 package path}"
: "${PAM4_C0_RUN_ROOT:?Set existing C0 campaign directory}"
: "${PAM4_C0_APPROVAL:?Set original five-case approval path}"
: "${PAM4_C0_SWITCH_PACKAGE:?Set verified SWITCH64 package path}"
: "${PAM4_C0_R5_ORIGINAL:?Set COMP r5_original directory}"
: "${PAM4_PDK_ROOT:?Set existing private model root}"
: "${SLURM_ARRAY_TASK_ID:?Select C0 index 1 through 4}"
case "$SLURM_ARRAY_TASK_ID" in
  1|2|3|4) ;;
  *) echo 'Use collect-only for C0 index 0' >&2; exit 2 ;;
esac
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
/usr/bin/python3.11 -B "$PAM4_C0_ALIGN_PACKAGE/c0_rescore.py" \
  --mode check-baseline --root "$PAM4_C0_RUN_ROOT"
/usr/bin/python3.11 -B "$PAM4_C0_ORIGINAL_PACKAGE/c0_run.py" --mode run \
  --index "$SLURM_ARRAY_TASK_ID" --root "$PAM4_C0_RUN_ROOT" \
  --model-root "$PAM4_PDK_ROOT" --approval "$PAM4_C0_APPROVAL"
exec /usr/bin/python3.11 -B "$PAM4_C0_ALIGN_PACKAGE/c0_rescore.py" --mode collect-only \
  --index "$SLURM_ARRAY_TASK_ID" --root "$PAM4_C0_RUN_ROOT"
