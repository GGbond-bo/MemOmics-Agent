# 集群 rds 目录普查（铁规 12.1 / 12.2 的实测底稿）

2026-10-18 实测：`/cluster/share/liuyuxuan3/Muscle/`（他人目录，`liuyuxuan3`）。
用户口述：「示例组织 snRNA、60 万细胞、**23 个注释**、不是 ATAC」→ 要确认哪个文件是它。

## 1. 为什么不能逐个读

- 目录下 20 个 rds，合计约 60 GB；最大 `MF.rds` 23.5 GB、`scRNA_scATAC_integrated_harmony2.rds` 21.4 GB。
- `session_start` 读一次 7 GB 对象 = 225 秒、会话 RSS 37 GB —— 逐个读 20 个不现实。
- 正解：**一个普查作业**（`scripts/census_rds_meta.R`）跑完全目录，日志落工作盘，pull 回来本机解析。

## 2. 提交与回收（可复用骨架）

```bash
# 本机
remote_cluster push  local=<results/<sid>/scripts/census_rds_meta.R>  remote=/cluster/share/user/census_rds_meta.R
remote_cluster submit command="Rscript --vanilla census_rds_meta.R /cluster/share/liuyuxuan3/Muscle 0326 Merge > census.log 2>&1" \
                      cwd=/cluster/share/user job_name=census_rds_meta
# 完成核对（一次拿全，别每轮重复）
remote_cluster run "tail -c 1500 /cluster/share/user/census.log; grep -n 'n=2[0-9]' /cluster/share/user/census.log | head -40"
remote_cluster pull remote=/cluster/share/user/census.log local=<results/<sid>/results/>
```

- 56 KB 日志整份读进上下文很浪费 → **pull 回本机后 `execute_code` 解析**：按 `########` 切块，
  每块抓 `SEURAT | genes: X | cells: Y`、逐列 `[列名] n=N`，过滤 `nCount|nFeature|percent|pct_|_index|Score`
  噪声列后只打印关键列 → 20 行紧凑表。
- 先 `grep -n 'n=2[0-9]'` 做便宜的一遍，能直接捞到「类目数落在目标区间」的列。

## 3. 两条实测教训

### 3.1 手写文件清单会静默漏文件

第一版脚本把 20 个路径**手写**进 `c()` 数组 → 漏掉了 `MF.rds`（23.5 GB，剩余最可能的候选），
日志里完全看不出少了东西。第二版改成自发现：

```r
all_files <- c(list.files(base, pattern="\\.rds$", full.names=TRUE),
               list.files(file.path(base,"0326"),  pattern="\\.rds$", full.names=TRUE),
               list.files(file.path(base,"Merge"), pattern="\\.rds$", full.names=TRUE))
```
并在开头 `for (f in all_files) cat(sprintf("  %8.2f GB  %s\n", file.size(f)/2^30, f))` ——
**清单 + 体积先打出来**，漏文件一眼可见（有没有 23.5 GB 那行）。

### 3.2 `unable to find required package 'Seurat'` ≠ 文件损坏

同一脚本内 15 个文件读出维度、5 个报错：

```
EC.rds / Immune.rds / 0326·FAP_process.rds / 0326·Immune.rds / Merge·Merge_MuSC.rds
→ ERROR: unable to find required package 'Seurat'
```
而 **604,244 细胞的 v5 对象同期读取成功** —— 典型"一半成一半败"，极易误判成文件损坏/权限问题。

根因是**版本差**：`Seurat` 类在 v5 由 **SeuratObject** 定义（不加载 Seurat 也能 readRDS），
在 v4 由 **Seurat** 包定义（不加载就报这句）。
→ 修复 = 脚本开头 `if (requireNamespace("Seurat", quietly=TRUE)) library(Seurat)`。
**不是**缺包（Seurat 已装），**不是**文件坏，**不要** pull 回本机重试、不要报"该文件无法读取"。

## 4. 本次普查结论（照录，供对照）

| 文件 | 细胞数 | 最大生物学注释列 |
|---|---|---|
| **Muscle_All.rds**（7.07 GB） | **604,244** | `Annotation_Level1` 6 / `Annotation` 10 / `celltype` 11 / `leiden_1` 18（纯簇号） |
| Merge/Exer_MF.rds | 114,049 | — |
| Merge/FSHD_MF.rds | 80,672 | — |
| integrated_harmony_FAP.rds | 66,265 | `SCT_snn_res.1.5` 26（纯簇号） |
| FAP.rds / FAP_old.rds | 39,727 | `SCT_snn_res.1.5` 25（纯簇号） |
| integrated_harmony_Immnue.rds | 35,862 | **`Annotation` 21 类（免疫细类：cDC2/CD16+ Mono/…/Plasmablast）** |
| Merge/FSHD_MuSC.rds | 35,626 | — |
| integrated_harmony_EC.rds | 29,082 | `SCT_snn_res.1` 20（纯簇号） |
| integrated_harmony_MuSC.rds | 23,898 | — |
| Immune_0330.rds | 20,854 | — |
| Merge/Exer_MuSC.rds | 16,024 | — |
| MuSC.rds | 15,810 | — |
| 5 个 v4 对象 | 读取失败 | 见 3.2（补 `library(Seurat)` 后复查） |

→ **细胞数吻合（604,244 ≈ 60 万），但注释对不上：最多 11 类，没有任何一列是 23 类**；
唯一"几十个小群"的是免疫子集的 21 类注释，但只有 3.5 万细胞。
交付按铁规 12 第 4 条：匹配了什么 / 缺了什么 / 未读候选表 / 问用户点哪个。

**体积估算锚点（复用）**：60 万细胞 ≈ 7–12 GB（实测 604,244 → 7.07 GB）；20–25 GB 对应 150–200 万细胞。

## 5. 边界

- 别人目录（`liuyuxuan3`）可能 `Permission denied` → 是**读取权限**问题，不是数据不存在；让人开权限或复制到可读路径。
- 普查作业是**只读**、长于 60 秒 → 走 `submit` 后台，别用 `run` 前台硬等。
- 首轮三入口全 `timed out`（proxy-jump banner）后，用户说"再试试"即全通 → 跳板瞬断很常见，**重试一次再报**。