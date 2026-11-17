#!/bin/bash
#SBATCH --job-name=pam4-c0-plate-m60
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=01:30:00
set -euo pipefail
: "${PAM4_C0_PLATE_PACKAGE:?Set the one-case package path}"
: "${PAM4_C0_FORMAL_ROOT:?Set the original formal C0 campaign}"
: "${PAM4_C0_PLATE_ROOT:?Set the new isolated one-case campaign}"
: "${PAM4_C0_PLATE_APPROVAL:?Set the bound one-case approval}"
: "${PAM4_PDK_ROOT:?Set the existing private model root}"
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
exec /usr/bin/python3.11 -B "$PAM4_C0_PLATE_PACKAGE/c0_plate_m60.py" run \
  --root "$PAM4_C0_FORMAL_ROOT" --run-root "$PAM4_C0_PLATE_ROOT" \
  --model-root "$PAM4_PDK_ROOT" --approval "$PAM4_C0_PLATE_APPROVAL"
