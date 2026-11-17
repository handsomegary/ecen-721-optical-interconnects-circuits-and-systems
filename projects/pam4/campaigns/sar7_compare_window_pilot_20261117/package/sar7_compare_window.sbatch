#!/bin/bash
#SBATCH --job-name=pam4-sar7-compare_window
#SBATCH --partition=adademic
#SBATCH --qos=olympus-academic
#SBATCH --account=all
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:12:00
#SBATCH --no-requeue

set -eo pipefail
source /opt/coe/cadence/IC231/setup.IC231.linux.bash
export PATH="$HOME/ECEN721/py311bin:/opt/coe/cadence/SPECTRE/tools.lnx86/bin:$PATH"
set -u
: "${PAM4_SAR7_COMPARE_WINDOW_PACKAGE:?Set this exact reviewed package}"
: "${PAM4_SAR7_READ_OVERLAP_PACKAGE:?Set immutable case18 parent}"
: "${PAM4_SAR7_COMPARE_WINDOW_ROOT:?Set the new isolated root}"
: "${PAM4_SAR7_COMPARE_WINDOW_APPROVAL:?Set its exact approval}"
: "${PAM4_PDK_ROOT:?Set existing approved private model root}"
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
exec /usr/bin/python3.11 -B "$PAM4_SAR7_COMPARE_WINDOW_PACKAGE/sar7_compare_window.py" run \
  --root "$PAM4_SAR7_COMPARE_WINDOW_ROOT" --approval "$PAM4_SAR7_COMPARE_WINDOW_APPROVAL" \
  --model-root "$PAM4_PDK_ROOT"
