---
name: doublet-detection
description: "双细胞（doublet）检测与判定：scDblFinder / DoubletFinder（R）与 scrublet（Python）选型与执行，含多样本·每样本细胞数少的数据策略决策、双细胞率判读区间、'要不要剔除'的判定准则与交付口径。触发：'检测双细胞' / '双细胞比例高不高' / '要不要剔除 doublet' / 'doublet rate' / '去双胞'。"
when_to_use: "用户对某个 Seurat/h5ad 对象问'有没有双细胞 / 双细胞多不多 / 要不要去双胞'时；或 scRNA 流程走到 QC 的 doublet 步骤但样本数多、每样本细胞数少（<100）时。与 scrna-qc（质控总流程）配套：本 skill 专管 doublet 这一步的选型·执行·判读。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [doublet, scDblFinder, DoubletFinder, scrublet, qc, scRNA-seq]
    difficulty: basic
    language: R+Python
    category: scRNA
prerequisites:
  r_packages: ["Seurat", "SingleCellExperiment", "scDblFinder"]
  python_packages: ["scanpy", "scrublet"]
---

# 双细胞检测与判定

用户的问题通常是三件套：**「有没有双细胞 / 比例高不高 / 要不要剔除」**。
回答必须给到：① 数字（总体 + 按组 + 按样本）② 图 ③ **明确建议**。只丢一个「X%」不算答完。

## Step 0：开工前三个事实核查（不许跳、不许猜）

| 要查什么 | 为什么 | 怎么查 |
|---------|--------|--------|
| 每样本细胞数分布 | **决定检测策略**（能否按样本单独跑） | `table(obj$samplename)` → median / min / max |
| counts 是否还在（整数、未归一化） | scDblFinder / DoubletFinder / scrublet **全部要求 raw counts** | `all(m@x == round(m@x))` + `range(Matrix::colSums(m))` |
| 流程走到哪一步（已注释？已去过双胞？） | 已去过双胞的数据重跑会二次剔除 | metadata 列 + 是否存在 `doublet` / `predicted_doublet` 列 |

**实测案例**：某 Seurat 对象 2132 cells × 51227 genes、**48 个样本**、6 组 → **≈44 细胞/样本**。
这个数字直接判死「按样本单独检测」（见下）。

## Step 1：策略决策表（按每样本细胞数选）

| 每样本细胞数 | 策略 | 说明 |
|-------------|------|------|
| ≥ 200 | **按样本单独检测**（`samples=` / `batch_key=`） | 最准，每样本各得一个双细胞率 |
| 100–200 | 按样本单独检测 **+ 整体检测对照** | 模拟双细胞数偏少，估计噪声大 |
| **< 100**（最常见） | ⛔ **不要按样本单独跑**。改：① 整体合并检测（推荐）② 按组（如 6 组）合并检测 | 交付口径改成「总数 + 按样本/组的分布」；**不要报「每样本双细胞率」**——分母 44 的比率没有意义 |

合并检测的**已知代价**：样本间异质性会被当成类间差异 → 可能把跨样本边界误判为双细胞。
所以**必须**同时看「双细胞是否集中在少数样本」——富集于单样本 = 该样本的技术问题，不是普遍污染。

## Step 2：方法与可用性（先探再写）

| 方法 | 本机实测位置（2026-09-24） | 结论 |
|------|--------------------------|------|
| `scDblFinder` | `C:/Users/<u>/AppData/Local/R/R-4.4.2/library` | 不在 R-4.5.3 库 ⇒ 要用 **R-4.4.2 的 Rscript 绝对路径**直调 |
| `DoubletFinder` | 同上（R-4.4.2 用户库） | 依赖 Seurat，跨版本更麻烦；优先 scDblFinder |
| `Seurat` | `E:/R-libs/R-4.5.3` | 读 `.rds` 用 **R-4.5.3 内核**（execute_r） |
| `scanpy` + `scrublet` | Python（`check_env` 实测 installed） | ✅ **推荐路线：Python scrublet，免跨版本桥接** |

⚠️ **禁混库**：把 4.4.2 编译的包挂进 4.5.3 内核会在 `loadNamespace` 阶段炸 DLL（`svglite.dll: LoadLibrary failure`）。
跨版本一律用**该版本的 Rscript 绝对路径**直调，不改 `.libPaths()` 硬挂。
⚠️ **先扫盘再断言"包没装"**：`search_files(target='files', path=<库目录>, pattern='*Dbl*')` 逐库扫，
比 `requireNamespace` 可靠（内核只看自己那套 libPaths，报 not found ≠ 机器上没有）。

## Step 3：判定区间（答「比例高不高」）

| 双细胞率 | 判读 | 动作 |
|---------|------|------|
| < 5% | 低 | 可保留，记入报告 |
| 5–10% | **正常区间**（10x 常规） | 建议剔除，影响也小 |
| 10–15% | 偏高 | **建议剔除**，同时查是否集中在某样本/某簇 |
| > 15–20% | 很高 | 先查根因（多核/解离过度/`nExp`·`pK` 设错），再剔 |

**必须一起看的三个分布**（只看总率会误判）：① 按样本（是否少数样本贡献大部分）② 按组（组间差异大会让剔除**引入组间细胞数不平衡**）③ 按簇（双 marker 共表达的假簇，注释要单独复核）。

## Step 4：剔除准则（答「要不要剔除」）

- 率 ≥5% 或明显富集于特定样本/簇 ⇒ **剔除**（保留 `predicted_doublet == FALSE`）
- <5% 且分布均匀 ⇒ 保留，但**必须把 `doublet_score` + `predicted_doublet` 写进 metadata** 供下游使用
- ⛔ **先写标记列再 subset**——直接 subset 掉无法回溯，也做不了敏感性对比
- 剔除后**按组分别**列剔除前后细胞数（暴露组间不平衡），别只报总数

## Step 5：交付物清单

1. 双细胞率**表**（Markdown 管道表格，见 SOUL 铁律 29）：总体 + 按组 + 按样本（前 N 高值）
2. **图**：① 双细胞分数直方图（含阈值线）② 降维图叠加双细胞标记 ③ 分数 vs `nFeature_RNA` 散点 ④ 按组/样本柱状
3. `doublet_scores.csv`（barcode 级：`doublet_score` / `predicted_doublet`）
4. 若剔除：`*_doubletRemoved.rds` + 剔除前后对照
5. **明确建议**（剔除 / 保留 / 先查某样本）

## 坑（实测）

| 坑 | 处置 |
|----|------|
| 按 < 100 细胞/样本硬跑 scDblFinder/scrublet | 会报错或给出不稳定估计；改合并检测（Step 1） |
| 用 `requireNamespace` 断言包缺失 | 内核只看自己那套库；先扫盘（Step 2） |
| 跨 R 小版本挂载编译包 | loadNamespace 炸 DLL；用对应版本 Rscript 绝对路径 |
| `rail_review(pre)` 报 `Missing packages`（含 Matrix/SingleCellExperiment 这类 base/常规包） | 属探测误报；**不传 `required_packages`** 或只列 rail 环境确实能解析的包（详见 `platform-execution-pitfalls`） |
| `rail_review(post)` 的 `output_dir` 传成 `results/` 或 `figures/` 子目录 | 扫描器只数一层 → `figure_count=0` 硬判 failed；一律传**会话根目录** `results/<sid>/` |
| 高代价任务开工前未对齐目标 | 先弹意图确认表单（策略/方法/交付物三问），问完结束回合等答复（详见 `platform-execution-pitfalls` 第 11 条） |

## 参考

- `references/doublet-detection-multisample.md` — 完整配方：导出 counts 的 R 片段、Python scrublet 与 R-4.4.2 scDblFinder 两条可跑脚本模板、按样本/组/簇的判读细节、交付与报告口径
- 配套：`scrna-qc`（质控总流程，其 Pipeline 第 4 步即本步骤）、`platform-execution-pitfalls`（门禁/包探测/审查口径）