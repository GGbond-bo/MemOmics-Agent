# ssh3 环境实测清单（2026-10-08）

> 全部结论来自登录节点**只读实测**（`ls` / `--version` / `find.package` / `find_spec`），非推断。
> 节点 `cngb-supermem-a15-3.cngb.sz.hpc`（CNGB 深圳超算）｜账号 `zhangbo11`｜SGE 8.1.9｜工作目录 `/hwfssz3/PS_JLU/zhangbo`

## 两个来源，都已验证可访问 ✅

| 来源 | 路径 | 权限 | 调用方式 |
|---|---|---|---|
| 别人的 conda（zhangxiao6） | `/hwfssz3/PS_JLU/zhangxiao6/software/miniconda3` | `drwxr-xr-x`、属主他人 → **只读可用、装不了包** | `source .../bin/activate <env>`；或绝对路径 `.../envs/<env>/bin/Rscript` |
| 自己的 envs（zhangbo） | `/hwfssz3/PS_JLU/zhangbo/envs/R4.4.1_zb` | 自己的 → 可写 | `/hwfssz3/PS_JLU/zhangbo/envs/R4.4.1_zb/bin/Rscript` |

`source <conda_root>/bin/activate sc-analysis` 实测成功（activate 不需要写权限）。

## R 环境

| env | R 版本 | 包数 | 实测关键内容 | 备注 |
|---|---|---|---|---|
| **R4.41** | 4.4.1 | 694 | Seurat 5.3.0 / monocle3 1.4.27 / Signac 1.14.0 / hdWGCNA 0.4.7 / DESeq2 1.46.0 / clusterProfiler 4.14.6 / harmony 1.2.3 / SeuratDisk / limma 3.62.2 / BSgenome.Hsapiens.UCSC.hg38 1.4.5 / ComplexHeatmap 2.22.0 / sctransform 0.4.1 / ggplot2 3.5.2 | ⭐ RNA 最全能 |
| **R4.3.3** | 4.3.3 | 399 | **ArchR 1.0.3** / Seurat 5.3.0 / Signac 1.14.0 / ComplexHeatmap 2.18.0 / BSgenome.hg38；**缺** DESeq2、clusterProfiler | ATAC 备选 |
| **ARCHR** | 4.4.1 | — | **ArchR 1.0.3** / Signac 1.15.0 / ComplexHeatmap 2.22.0 | ⭐ ATAC 首选 |
| R4.2.2 | 4.2.2 | — | 旧版兼容 | 备 |
| gsea-coda | 4.3.3 | — | 富集 | 备 |
| milopy | 4.5.3 | — | 邻域富集（空间） | 备 |
| r_draw / r-sccode | 4.4.1 / 4.3.0 | — | 画图 / 单细胞代码库 | 备 |
| MACS2 | R 3.5.0 | — | peak calling | 备 |
| ⚠️ `cellchat` | 4.2.2 | 289 | **`find.package("CellChat")` 为空 → 没有 CellChat** | 名不副实 |
| ⚠️ `monocle3` | 4.3.1 | **仅 14** | **没有 monocle3**；libPaths 指向 `~/R/x86_64-conda-linux-gnu-library/4.3` | 名不副实 |

## Python 环境

| env | Python | 实测关键内容 |
|---|---|---|
| **sc-analysis** | 3.9.23 | scanpy 1.10.3 / anndata 0.10.9 / squidpy 1.2.2 / harmonypy 0.0.10 / sklearn 1.6.1 / umap 0.5.9 / leidenalg / seaborn 0.13.2 / statsmodels 0.14.5 / pandas 2.3.1 / numpy 1.26.4；**无** torch、scvi、celltypist、pyscenic ⭐ |
| **scenic** | 3.10.18 | **pyscenic 0.12.1** / ctxcore 0.2.0 / scanpy 1.10.4 / loompy 3.0.8 ⭐ pySCENIC 专用 |
| celltypist / cellscope | 3.10.18 | 细胞注释 |
| omicverse | 3.10.20 | |
| scvelo_env | 3.11.14 | RNA velocity |
| pyscenic | 3.10.18 | |
| hotspot | 3.8.20 | |
| bonsai / bonsai313 | 3.14.7 / 3.13.15 | |
| Alig | 3.13.2 | 比对 |
| senepy | 3.9.23 | |
| eggnog | 3.11.12 | |
| jupyter / py39 / datatable | 3.13.2 / 3.9.18 / 3.7.16 | |
| ldsc / LDSC | 2.7.18 | LD score |
| htslib / liftover / fatotwobit | 无解释器 | CLI 工具目录 |

## 自己的 R4.4.1_zb（384 包）— 撑不起主力

有：Seurat **5.5.1**、limma 3.62.2、GenomicRanges 1.58.0、ggplot2 4.0.3、sctransform 0.4.3
缺（NOT_INSTALLED）：ArchR、Signac、CellChat、monocle3、harmony、ComplexHeatmap、hdWGCNA、DESeq2、clusterProfiler、BSgenome.Hsapiens.UCSC.hg38、pheatmap、SeuratDisk

→ 目前只适合基础操作；做主力需补装（该目录**有写权限**，可装）。

## 按任务推荐（待用户最终拍板）

| 任务 | 环境 |
|---|---|
| 单细胞 RNA：Seurat / 聚类 / DEG / 富集 / monocle3 轨迹 | **R4.41** |
| ATAC / 染色质（ArchR） | **ARCHR**（或 R4.3.3） |
| pySCENIC 调控网络 | **scenic** |
| Python 单细胞（scanpy / squidpy / harmony） | **sc-analysis** |
| 细胞通讯 CellChat | ⚠️ **无现成环境**（`cellchat` env 名不副实）→ 需新建或补装 |
| 邻域富集 milopy | **milopy** |

## 坑（会重复踩）

1. 真实目录名是 `R4.41` / `R4.3.3` / `R4.2.2`，**不是** R441 / R443。
2. `cellchat`、`monocle3` 两个 env **名不副实** —— 找不到对应包，别按名字用。
3. 别人目录只读；装包必须在 `~/envs/` 下自建。
4. 作业里必须 `source .../bin/activate <env>`，系统级 Rscript/python3 不在 PATH。
5. `qstat` 在登录节点曾 3 分钟无响应（SGE 客户端连 master 异常）→ 投递前先手动确认一次。