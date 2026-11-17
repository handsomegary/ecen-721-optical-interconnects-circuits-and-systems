#!/bin/bash
#SBATCH --job-name=pam4-sar7-cml-drive2
#SBATCH --partition=adademic
#SBATCH --qos=olympus-academic
#SBATCH --account=all
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:12:00
#SBATCH --no-requeue
#SBATCH --signal=B:TERM@60

set -eo pipefail
: "${PAM4_SAR7_CML_DRIVE2_PACKAGE:?Set exact reviewed package}"
: "${PAM4_SAR7_CML_DRIVE2_ROOT:?Set approved isolated root}"
: "${PAM4_SAR7_CML_DRIVE2_APPROVAL:?Set its exact approval}"
# Claude begins the lease BEFORE sbatch. A pending accepted job retains it.
# Do not exec the run: EXIT must restore even on setup, run or collection failure.
restore_c2_on_exit() {
  original_rc=$?
  trap - EXIT
  set +e
  /usr/bin/python3.11 -B "$PAM4_SAR7_CML_DRIVE2_PACKAGE/c2_slot_lease.py" restore \
    --root "$PAM4_SAR7_CML_DRIVE2_ROOT" --approval "$PAM4_SAR7_CML_DRIVE2_APPROVAL"
  restore_rc=$?
  if [ "$restore_rc" -ne 0 ]; then
    echo "ERROR: C2 lease NOT verified restored; inspect c2_slot_lease_events.jsonl and restore explicitly." >&2
    if [ "$original_rc" -eq 0 ]; then original_rc=70; fi
  fi
  exit "$original_rc"
}
trap restore_c2_on_exit EXIT
trap 'exit 143' TERM
source /opt/coe/cadence/IC231/setup.IC231.linux.bash
export PATH="$HOME/ECEN721/py311bin:/opt/coe/cadence/SPECTRE/tools.lnx86/bin:$PATH"
set -u
: "${PAM4_SAR7_ACCEPT_GAP_PACKAGE:?Set immutable case21 parent}"
: "${PAM4_PDK_ROOT:?Set existing approved private model root}"
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 SPECTRE_DEFAULTS=-E
/usr/bin/python3.11 -B "$PAM4_SAR7_CML_DRIVE2_PACKAGE/c2_slot_lease.py" status --require-active \
  --root "$PAM4_SAR7_CML_DRIVE2_ROOT" --approval "$PAM4_SAR7_CML_DRIVE2_APPROVAL"
/usr/bin/python3.11 -B "$PAM4_SAR7_CML_DRIVE2_PACKAGE/sar7_cml_drive2.py" run \
  --root "$PAM4_SAR7_CML_DRIVE2_ROOT" --approval "$PAM4_SAR7_CML_DRIVE2_APPROVAL" \
  --model-root "$PAM4_PDK_ROOT"
