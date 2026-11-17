#!/bin/bash
#SBATCH --job-name=pam4-sar7-collectfix
#SBATCH --partition=adademic
#SBATCH --qos=olympus-academic
#SBATCH --account=all
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:10:00
#SBATCH --no-requeue

set -euo pipefail
: "${PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_PACKAGE:?Set this exact collector package}"
: "${PAM4_SAR7_READ_OVERLAP_PACKAGE:?Set immutable original case18 package}"
: "${PAM4_SAR7_READ_OVERLAP_SOURCE_ROOT:?Set completed761649 source root}"
: "${PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_ROOT:?Set separate new output root}"
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8
exec /usr/bin/python3.11 -B "$PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_PACKAGE/sar7_read_overlap_collect_fix.py" collect-only \
  --source-root "$PAM4_SAR7_READ_OVERLAP_SOURCE_ROOT" \
  --output-root "$PAM4_SAR7_READ_OVERLAP_COLLECT_FIX_ROOT"
