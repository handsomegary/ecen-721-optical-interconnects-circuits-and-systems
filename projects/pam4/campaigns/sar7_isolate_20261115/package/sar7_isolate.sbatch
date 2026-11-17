#!/bin/bash
#SBATCH --job-name=pam4-sar7-isolate
#SBATCH --partition=adademic
#SBATCH --qos=olympus-academic
#SBATCH --account=all
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:30:00
#SBATCH --no-requeue

set -eo pipefail
source /opt/coe/cadence/IC231/setup.IC231.linux.bash
export PATH="$HOME/ECEN721/py311bin:/opt/coe/cadence/SPECTRE/tools.lnx86/bin:$PATH"
set -u
: "${PAM4_SAR7_ISOLATE_PACKAGE:?Set the isolation package path}"
: "${PAM4_SAR7_ISOLATE_ROOT:?Set the isolation root}"
: "${PAM4_SAR7_ISOLATE_APPROVAL:?Set the isolation approval}"
: "${PAM4_SAR7_RELAXED_PACKAGE:?Set the measured relaxed package path}"
: "${PAM4_SAR7_PACKAGE:?Set the original SAR7 package path}"
: "${PAM4_PDK_ROOT:?Set the original private PDK root}"
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
exec /usr/bin/python3.11 -B "$PAM4_SAR7_ISOLATE_PACKAGE/sar7_isolate.py" run \
  --root "$PAM4_SAR7_ISOLATE_ROOT" --model-root "$PAM4_PDK_ROOT" --approval "$PAM4_SAR7_ISOLATE_APPROVAL"
