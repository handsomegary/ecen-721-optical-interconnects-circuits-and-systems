#!/bin/bash
#SBATCH --job-name=pam4-sar7-qaudit
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
: "${PAM4_SAR7_QBUFFER_AUDIT_PACKAGE:?Set the reviewed audit package}"
: "${PAM4_SAR7_QBUFFER_PACKAGE:?Set the frozen qbuffer package}"
: "${PAM4_SAR7_STRONG_DECODE_PACKAGE:?Set the frozen strong package}"
: "${PAM4_SAR7_QBUFFER_SOURCE_ROOT:?Set completed qbuffer root}"
: "${PAM4_SAR7_STRONG_SOURCE_ROOT:?Set completed strong root}"
: "${PAM4_SAR7_QBUFFER_AUDIT_ROOT:?Set a separate new audit output root}"
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8
exec /usr/bin/python3.11 -B "$PAM4_SAR7_QBUFFER_AUDIT_PACKAGE/sar7_qbuffer_audit.py" audit \
  --qbuffer-root "$PAM4_SAR7_QBUFFER_SOURCE_ROOT" \
  --strong-root "$PAM4_SAR7_STRONG_SOURCE_ROOT" \
  --output-root "$PAM4_SAR7_QBUFFER_AUDIT_ROOT"
