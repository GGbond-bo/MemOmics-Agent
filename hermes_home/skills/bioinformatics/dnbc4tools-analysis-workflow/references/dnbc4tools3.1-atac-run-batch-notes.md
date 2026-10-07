# dnbc4tools 3.1 atac run 批量比对实测记录（2026-09-01）

真实场景：Windows 11 本机 + WSL2 Ubuntu，dnbc4tools 3.1（FTP 版），人类 GRCh38 snATAC 文库批量比对。
24 个文库位于 `F:\CRGMara1\`，用户要求逐库循环跑，输出到 `F:\output`。

## 数据规模（实测）

| 项 | 值 |
|----|-----|
| 文库数 | 24（`1335/1888/2183/2200/2297/665/714/934` × \_snATAC(-1/-2/-3 或 \_Lib-1/-2/-3)） |
| 单个文库 fq.gz | 2–6 个文件（88–174G/库），全量输入 ~3.0T |
| 多 lane 文库 | 1888_snATAC-3(4fq)、665_snATAC_Lib-3(4fq)、934_snATAC-1(4fq)、934_snATAC-2(6fq) |
| 命名规则 | `E2500xxxxx_L01_N_1.fq.gz` / `_2.fq.gz`（R1/R2 后缀） |
| F 盘剩余 | 224G（3.7T 已用 3.5T）→ 全量输出 500G–2T 必爆盘 → 需与用户确认策略 |
| WSL 配置 | 48GB RAM（.wslconfig memory=48GB processors=16 swap=8GB，`wsl --shutdown` 后生效），16 线程 |

## 关键路径（v3.1）

- 索引权威源：WSL 内部 `/data/GRCh38_ref/GRCh38_atac_index/Homo_sapiens/`（ref.json 版本 3.1，genome.fa 3.15G + genome.index 12.3G + genes.gtf 1.3G）
- `--genomeDir` 必须传 **`.../Homo_sapiens/`**（含 ref.json 的那层），ref.json 相对路径以该层为根
- E 盘副本：`/mnt/e/Human_gene_reference/GRCh38_atac_index/Homo_sapiens/ref.json`（16GB 已复制）

## 循环脚本模式（templates/atac_run_batch.sh）

- `SLIB=<文库名>` 试跑/重跑单库；空则全量循环
- 断点续跑：`output/singlecell.csv` 存在则跳过该库
- R1/R2 收集：`mapfile -t` + `ls *_{1,2}.fq.gz` 拍序 + `_fastq.gz` 兜底，多 lane 逗号合并
- 每库日志独立 `logs/<lib>.log`，批次日志 `logs/batch.log`

## 试点结论（2200_snATAC_Lib-2，88G）

- 启动方式：`wsl -e bash -lc "cd /data && SLIB=2200_snATAC_Lib-2 bash /mnt/e/MemOmics-Agent/results/memomics-98c2d985/scripts/atac_run_batch.sh"`
- 后台 + notify_on_complete=true；预计 60–120 分钟/库（16 线程）

## 铁律提醒

1. **Git Bash ≠ WSL**：`/mnt/*` `/data` 只能 `wsl -e bash -lc` 里访问；Git Bash 只见 `/f/`（盘符映射）。
2. **先试点后全量**：单库输出体积未知时不要直接 24 库全跑（空间核算）。
3. v3.1 参数已核对（--threads 有、--need_bam 改名、--merge_cutoff 默认 500、--fastqs 目录输入可用），详见 SKILL.md atac run 要点。