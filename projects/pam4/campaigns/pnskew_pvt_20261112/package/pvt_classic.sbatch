#!/bin/bash
#SBATCH --job-name=pam4-pvt-classic
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00
set -euo pipefail
: "${PAM4_STUDY_ROOT:?Use the reviewed package path}"
: "${PAM4_PVT_CASES:?Use the reviewed portable case directory}"
: "${PAM4_PVT_CASE_LIST:?Use the newline-separated reviewed case IDs}"
: "${PAM4_PDK_ROOT:?Use the existing private shrink model tree}"
: "${PAM4_RUN_ROOT:?Use a fresh owned campaign directory}"
: "${SLURM_ARRAY_TASK_ID:?Choose a zero-based index in the reviewed list}"
export LC_ALL=C.UTF-8 LANG=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
case_id=$(python3 -B -c 'import re,sys; from pathlib import Path; rows=Path(sys.argv[1]).read_text(encoding="utf-8").splitlines(); i=int(sys.argv[2]); assert 0<=i<len(rows); s=rows[i]; assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,120}",s); print(s)' "$PAM4_PVT_CASE_LIST" "$SLURM_ARRAY_TASK_ID")
python3 -B "$PAM4_STUDY_ROOT/run_case.py" pvt --case-dir "$PAM4_PVT_CASES/$case_id" \
  --pdk-root "$PAM4_PDK_ROOT" --run-root "$PAM4_RUN_ROOT" --retire-new-raw
