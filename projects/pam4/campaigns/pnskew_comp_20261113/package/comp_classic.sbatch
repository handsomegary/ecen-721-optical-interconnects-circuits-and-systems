#!/bin/bash
#SBATCH --job-name=pam4-deskew
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
set -euo pipefail
: "${PAM4_COMP_PACKAGE:?Review and verify the package first}"
: "${PAM4_COMP_RUN_ROOT:?Set the campaign path under ecen720_28nm/runs}"
: "${PAM4_COMP_APPROVAL:?Set the reviewed approval JSON}"
: "${PAM4_PDK_ROOT:?Set the existing private Olympus kit root}"
: "${SLURM_ARRAY_TASK_ID:?Select explicitly approved case indices}"
export SPECTRE_DEFAULTS=-E PYTHONIOENCODING=utf-8 LC_ALL=C.UTF-8
kind="${PAM4_COMP_KIND:-ac}"
extra=()
if [[ "$kind" != ac ]]; then
    extra+=(--admission "${PAM4_SKEW_ADMISSION:?Use the original r5 admission}")
fi
if [[ "$kind" == pilot ]]; then
    extra+=(--code "${PAM4_COMP_PILOT_CODE:?Select a permitted foreground code}")
elif [[ "$kind" == payload ]]; then
    extra+=(--observations "${PAM4_COMP_OBSERVATIONS:?Use validated pilot JSON}")
fi
exec /usr/bin/python3.11 -B "$PAM4_COMP_PACKAGE/comp_run.py" --mode run \
    --kind "$kind" --index "$SLURM_ARRAY_TASK_ID" \
    --plan "$PAM4_COMP_PACKAGE/comp_plan.json" --root "$PAM4_COMP_RUN_ROOT" \
    --model-root "$PAM4_PDK_ROOT" --approval "$PAM4_COMP_APPROVAL" "${extra[@]}"
