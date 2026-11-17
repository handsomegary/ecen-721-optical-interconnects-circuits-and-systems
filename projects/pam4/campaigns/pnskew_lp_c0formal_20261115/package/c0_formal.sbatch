#!/bin/bash
#SBATCH --job-name=pam4-c0-formal
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=01:30:00
set -euo pipefail
: "${PAM4_C0_FORMAL_PACKAGE:?Set the formal C0 package path}"
: "${PAM4_C0_FORMAL_ROOT:?Set the new formal C0 run root}"
: "${PAM4_C0_FORMAL_APPROVAL:?Set the bound formal C0 approval file}"
: "${PAM4_C0_STAGE:?Set phase, code or payload}"
: "${PAM4_PDK_ROOT:?Set the existing private model root}"
: "${SLURM_ARRAY_TASK_ID:?Specify a stage case index}"
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
exec /usr/bin/python3.11 -B "$PAM4_C0_FORMAL_PACKAGE/c0_formal.py" run \
  --root "$PAM4_C0_FORMAL_ROOT" --stage "$PAM4_C0_STAGE" --index "$SLURM_ARRAY_TASK_ID" \
  --model-root "$PAM4_PDK_ROOT" --approval "$PAM4_C0_FORMAL_APPROVAL"
