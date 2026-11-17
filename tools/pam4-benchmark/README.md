# PAM4 APS benchmark

在 repo 根目錄先設定 `PROJECT6_PDK_ROOT`，再為每次測速建立新目錄。用 `--case baseline_noise --mode full` 產生 `bench.scs`，同一份網表可複製到第二次測速的目錄，並在兩個目錄用 `sha256sum bench.scs` 比對。腳本接受 `aps` 作為第一個參數，使用 Slurm 的 `SLURM_CPUS_PER_TASK` 設定 Spectre 的執行緒數。核對目前課程資源與佇列限制後，再用 `sbatch --cpus-per-task=<N> .../run_benchmark.sbatch aps` 提交。

完成後比對兩份 `timing.txt` 的 `SPECTRE_WALL_S`，並核對計算節點、網表、Spectre 版本與分析模式。先前同節點的 1 核／4 核結果分別為 1099.585 s／515.448 s。詳細量測條件見[測速筆記](https://github.com/<owner>/olympus-cadence-ocean-analog-notes/blob/main/docs/pam4-aps-benchmark.md)。
