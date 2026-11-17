#!/bin/bash
#SBATCH --job-name=pam4-sar7-cdac-fix
#SBATCH --partition=adademic
#SBATCH --qos=olympus-academic
#SBATCH --account=all
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:10:00
#SBATCH --no-requeue

set -eo pipefail
source /opt/coe/cadence/IC231/setup.IC231.linux.bash
export PATH="$HOME/ECEN721/py311bin:/opt/coe/cadence/SPECTRE/tools.lnx86/bin:$PATH"
set -u
: "${PAM4_SAR7_CDAC_FIX_PACKAGE:?Set the reviewed correction package}"
: "${PAM4_SAR7_CDAC_FIX_ROOT:?Set the new correction root}"
: "${PAM4_SAR7_CDAC_FIX_APPROVAL:?Set the correction approval file}"
: "${PAM4_SAR7_CML_RDEG_PACKAGE:?Set the original RDEG package}"
: "${PAM4_SAR7_RELAXED_PACKAGE:?Set the original relaxed package}"
: "${PAM4_SAR7_PACKAGE:?Set the original SAR7 package}"
: "${PAM4_PDK_ROOT:?Set the existing verified private model root}"
case "${1:-}" in 0|1) ;; *) echo 'Supply the approved case index 0 or 1' >&2; exit 2 ;; esac
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
exec /usr/bin/python3.11 -B "$PAM4_SAR7_CDAC_FIX_PACKAGE/sar7_cdac_fix.py" run \
  --index "$1" --root "$PAM4_SAR7_CDAC_FIX_ROOT" \
  --model-root "$PAM4_PDK_ROOT" --approval "$PAM4_SAR7_CDAC_FIX_APPROVAL"
