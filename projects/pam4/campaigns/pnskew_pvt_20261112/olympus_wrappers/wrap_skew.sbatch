#!/bin/bash
#SBATCH --job-name=pam4-skew
#SBATCH --partition=adademic
#SBATCH --qos=olympus-academic
#SBATCH --account=all
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=03:00:00
#SBATCH --no-requeue
#SBATCH --output=$HOME/ecen720_28nm/runs/pam4/pnskew_pvt_20261112_r1.6FKXOs/logs/skew-%A_%a.log
set -eo pipefail
unset OA_HOME LD_LIBRARY_PATH PYTHONOPTIMIZE
source /opt/coe/cadence/IC231/setup.IC231.linux.bash
export PATH="$HOME/ECEN721/py311bin:/opt/coe/cadence/SPECTRE/tools.lnx86/bin:$PATH"
export PAM4_STUDY_ROOT=$HOME/ecen720_28nm/runs/pam4/pnskew_pvt_20261112_r1.6FKXOs/pkg PAM4_SKEW_ADMISSION=$HOME/ecen720_28nm/runs/pam4/pnskew_pvt_20261112_r1.6FKXOs/admission.json PAM4_RUN_ROOT=$HOME/ecen720_28nm/runs/pam4/pnskew_pvt_20261112_r1.6FKXOs/run
export PAM4_PDK_ROOT=$HOME/ecen720_28nm/tools/local_replay_migration_20261108/private_models/r7_vm_shrink
export PAM4_PVT_CASES=$HOME/ecen720_28nm/runs/pam4/pnskew_pvt_20261112_r1.6FKXOs/pkg/pvt/cases PAM4_PVT_CASE_LIST=$HOME/ecen720_28nm/runs/pam4/pnskew_pvt_20261112_r1.6FKXOs/pkg/pvt/cases/case_ids.txt
echo "python3=$(python3 -V) spectre=$(command -v spectre) host=$(hostname)"
bash $HOME/ecen720_28nm/runs/pam4/pnskew_pvt_20261112_r1.6FKXOs/pkg/skew_classic.sbatch
