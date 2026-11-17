#!/bin/bash
#SBATCH --job-name=pam4-sar7-dac-drive
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
: "${PAM4_SAR7_FAST_PACKAGE:?Set frozen 761321 package path}"
: "${PAM4_SAR7_DAC_DRIVE_PACKAGE:?Set the driver pilot package path}"
: "${PAM4_SAR7_DAC_DRIVE_ROOT:?Set an isolated driver pilot run directory}"
: "${PAM4_SAR7_DAC_DRIVE_APPROVAL:?Set the driver pilot approval file}"
: "${PAM4_PDK_ROOT:?Use the original private PDK root}"
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
exec /usr/bin/python3.11 -B "$PAM4_SAR7_DAC_DRIVE_PACKAGE/sar7_dac_drive.py" run \
  --root "$PAM4_SAR7_DAC_DRIVE_ROOT" --approval "$PAM4_SAR7_DAC_DRIVE_APPROVAL" --model-root "$PAM4_PDK_ROOT"
