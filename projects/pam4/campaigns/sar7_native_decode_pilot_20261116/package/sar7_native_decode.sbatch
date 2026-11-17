#!/bin/bash
#SBATCH --job-name=pam4-sar7-native-decode
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
: "${PAM4_SAR7_NATIVE_DECODE_PACKAGE:?Set this pilot package path}"
: "${PAM4_SAR7_NATIVE_DECODE_ROOT:?Set this isolated run path}"
: "${PAM4_SAR7_NATIVE_DECODE_APPROVAL:?Set this pilot approval file}"
: "${PAM4_PDK_ROOT:?Use approved private model root}"
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
exec /usr/bin/python3.11 -B "$PAM4_SAR7_NATIVE_DECODE_PACKAGE/sar7_native_decode.py" run \
  --root "$PAM4_SAR7_NATIVE_DECODE_ROOT" --approval "$PAM4_SAR7_NATIVE_DECODE_APPROVAL" --model-root "$PAM4_PDK_ROOT"
