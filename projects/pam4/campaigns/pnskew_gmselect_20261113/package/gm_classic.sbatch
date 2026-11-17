#!/bin/bash
#SBATCH --job-name=pam4-gmselect
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
set -euo pipefail
: "${PAM4_GM_PACKAGE:?Set the reviewed package path}"
: "${PAM4_GM_RUN_ROOT:?Set a new campaign directory}"
: "${PAM4_GM_APPROVAL:?Set the new approved case manifest}"
: "${PAM4_PDK_ROOT:?Set the existing private model tree}"
: "${SLURM_ARRAY_TASK_ID:?Select approved array indices}"
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
exec /usr/bin/python3.11 -B "$PAM4_GM_PACKAGE/gm_select.py" --mode run \
    --index "$SLURM_ARRAY_TASK_ID" --root "$PAM4_GM_RUN_ROOT" \
    --model-root "$PAM4_PDK_ROOT" --approval "$PAM4_GM_APPROVAL"
