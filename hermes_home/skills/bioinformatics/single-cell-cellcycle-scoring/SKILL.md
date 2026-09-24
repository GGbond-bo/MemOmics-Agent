---
name: single-cell-cellcycle-scoring
description: "单细胞/单核细胞周期打分的判读与验证（Seurat CellCycleScoring / cc.genes.updated.2019）：先做真实增殖 marker 阴性对照，再决定能否解读相位标签；含推断单位（ICC/设计效应）、供体级置换、n 核重抽样 bootstrap、BH 校正与结论口径。触发：细胞周期打分 / CellCycleScoring / cc.genes / S.Score / G2M.Score / Phase / 相位比例 / cycling 比例 / 细胞增殖打分 / 各组细胞周期有没有差别。"
when_to_use: "用户要求给细胞做细胞周期打分、比较不同组/亚群之间的相位分布或 S/G2M 打分差异，或在 QC 流程里用相位去除分裂期细胞时，先加载本 skill。终末分化组织（骨骼肌肌核、心肌、神经元、肝细胞）尤其必读：那里打出来的相位标签极可能是噪声。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [cell-cycle, scrna, snrna, seurat, statistics, validity-control]
    difficulty: intermediate
    language: R
    category: bioinformatics
---

# 单细胞/单核细胞周期打分：判读、验证与统计

## 何时用
- 用户要"给细胞做细胞周期打分，看看不同组有没有差别"
- QC 流程里要用相位标签剔除/标记分裂期细胞
- 想把 S.Score / G2M.Score 当作表型做组间、亚群、轨迹比较

## 0. 🔴 判据速查（先读这一条，能省掉整套假结论）
`CellCycleScoring()` 只负责**相对比较**（`S.Score > G2M.Score` ⇒ 判为 S），**不判定细胞是否真的在增殖**。
因此：

| 观察 | 解读 | 处置 |
|------|------|------|
| **MKI67 检出率 ≈ 0 而 S+G2M 占比 > 50%** | 相位标签由噪声 / 基因集基线表达驱动 | ⛔ 不做组间生物学解读；结论写"该数据无增殖细胞，细胞周期打分不适用" |
| MKI67/PCNA/TOP2A 与相位一致升高，S+G2M 为个位数 | 可能有真实增殖群 | 可做组间比较，并按细胞类型分层（增殖信号常来自特定亚群，如 PAX7+/MYF5+ MuSC） |
| 报告写"X% 的细胞正在增殖" | 措辞错误 | 只能写"被打分判为 S 相的比例" |

**终末分化组织**（骨骼肌 / 心肌 / 神经元 / 肝细胞）默认按"不可解读"起步，除非阴性对照给出阳性证据。

## 1. 打分（正确姿势）
```r
suppressPackageStartupMessages(library(Seurat))
if (!exists("obj")) obj <- readRDS("<path>.rds")
DefaultAssay(obj) <- "RNA"                       # ⛔ 不要用 SCT：其 data 层是皮尔逊残差
s_genes   <- cc.genes.updated.2019$s.genes       # 人 S 43 基因
g2m_genes <- cc.genes.updated.2019$g2m.genes     # 人 G2M 54 基因
cat(sum(s_genes %in% rownames(obj)), "/", length(s_genes))     # 覆盖检查：必须全中
set.seed(1)
obj <- CellCycleScoring(obj, s.features = s_genes, g2m.features = g2m_genes, set.ident = FALSE)
obj$Phase <- factor(obj$Phase, levels = c("G1", "S", "G2M"))
```
- 输入必须是 **log-normalized 的 `data` 层**；`set.ident = FALSE` 别覆盖聚类 identity
- 打分前打印 `table(obj$Phase)` 与 `range(obj$S.Score)`：**分值范围极小（如 0.1 量级）= 分类阈值落在噪声带里**

## 2. 阴性对照（必做，判读的前提）
统计真实增殖 marker 的**可检出率（>0 表达核占比）**，按 **相位 / 组 / 供体**各算一遍：
`MKI67, PCNA, TOP2A, HIST1H4C, CCNB1, CDK1, MCM2`（+ `PAX7/MYOD1` 看有无可增殖卫星细胞）。
> **MKI67 是首选判据**：真正的增殖细胞必然可检出；全部核 0% ⇒ 该数据不存在增殖细胞。
> 再做**特异性检查**：cc 基因集基线表达若失衡（如 S 集均值 0.0623 vs G2M 集 0.0427），
> 连朴素均值比较都会凭空给出 >50% 的 S 相位。

## 3. 统计（多组比较，别只报细胞级卡方）
### 3.1 先算 ICC / 设计效应，再决定推断单位
```r
x <- agg$nCyc; n <- agg$n; k <- length(n); N <- sum(n); m0 <- N/k; pbar <- sum(x)/N
MSB <- sum(n*(x/n - pbar)^2)/(k-1); MSW <- sum(n*(x/n)*(1-x/n))/(N-k)
ICC <- (MSB - MSW)/(MSB + (m0-1)*MSW); DEFF <- 1 + (m0-1)*ICC      # 有效 n = N/DEFF
```
**别反射性把细胞级 p 值一律判为伪重复**：实测有 ICC = 0.0175（deff = 1.76，有效 n 1212）的情形，
此时细胞级结果并非 44 倍膨胀，应如实报告 ICC 并同时给样本级结果。

### 3.2 供体级置换（比渐近 KW 更敏感）
把"样本→组"标签打乱 2000 次重算统计量（细胞级卡方按每样本相位计数求和后重算；标量指标用 `kruskal.test(v ~ sample(lab))`）。

### 3.3 固定 n 的平衡设计 → n 核重抽样 bootstrap
每样本重抽 n 个核（如 45）500 次，看样本级 KW p 的分布：若大量重抽样 p>0.05 ⇒ **显著性不稳**，不可结论。

### 3.4 多重比较与配对
- ≥3 个指标一律 `p.adjust(..., "BH")`；**名义显著 ≠ 可结论**（实测 6 指标里 p=0.0145 → q≈0.09）
- 配对设计（同供体 pre/post）：`wilcox.test(pre, post, paired = TRUE, exact = FALSE)`，
  配对键 `donor <- sub("_(Pre|Post)$", "", samplename)`

## 4. 结论口径
- 阴性对照不过 ⇒ 结论 = "无增殖细胞 / 打分不适用"，并**明确写出不得作表型解读的理由（MKI67 检出率）**
- 统计上只拿到名义显著 ⇒ 结论 = "仅假设生成"，逐条列出待补证据（BH 后、置换、分层、效应量）
- 辩论（debate_analysis，场景 `stats_design`）给 `need_more_info` / low ⇒ 按裁决的 `next_actions` 逐条补齐后再定稿

## 5. 图集与交付（7 张，PNG 300dpi + PDF 矢量）
相位构成堆叠图 / 样本级指标箱线图（含 KW p）/ Pre-Post 配对连线 / UMAP（Phase + S.Score + G2M.Score）/
**真实增殖 marker 组间检出率（阴性对照图，最关键）** / marker 按相位分组 / 稳健性（置换 + bootstrap）。
> `rail_review(post)` 的 `output_dir` 一律传**会话根目录**（能一眼看到 figures/ 与 results/ 的那层）。
> 不用 ggpubr/ggrepel：p 值用 `annotate()` 手写，避免依赖门禁。

## 6. 代码坑
- `AddModuleScore()`（`CellCycleScoring` 内部也用）在 Windows 持久内核里**连续多次调用**会整进程崩
  （exit `0xC0000142`，stdout 全丢）→ 随机基因集对照改**独立 Rscript + `Matrix::colMeans`**；
  每个脚本开头 `sink()` 落日志，崩溃也保住已算结果。详见
  `platform-execution-pitfalls` 的 `references/persistent-kernel-crash-and-standalone-rscript.md`
- 按表达分位匹配随机基因时 `which(binid == x)` 可能取到空集 → `sample.int(length=0, ...)` 报"第一个参数无效"；采样函数需兜底
- 汇总表（比例类）要给全 6 组或声明子集口径；效应列注明计算口径（同族规范见平台铁律 29）

## 实测案例（可复现基准）
**MF_2000**（人骨骼肌 snRNA-seq，2132 肌核 / 48 样本 × 45 核 / 6 组 Y·O·OD × Pre·Post）
- 相位：G1 43.8% / S 31.0% / G2M 25.2%（S+G2M = 56.2%，与终末分化矛盾）
- 阴性对照：**MKI67 = 0.00%（全部核/组/供体）**；PCNA 1.07/5.45/1.30% (G1/S/G2M)；TOP2A ≤2.23%；CCNB1 ≤0.44%；CDK1 ≤0.37%
- 基线表达：S 集 0.0623 vs G2M 集 0.0427 → 朴素均值比较 %S = 64.5%
- 样本级 KW（6 组）：G2M.Score 0.018、pct_Cyc 0.052、S.Score 0.067，**两两 BH 无显著对**；配对运动效应 BH 全部 ≥0.69
- ICC 0.0175 / deff 1.76 / 有效 n 1212；供体级置换 p = 0.0145–0.040（名义显著，BH 后 q≈0.09）
- 45 核 bootstrap：pct_Cyc KW p 中位 0.147（20% <0.05）、G2M.Score 0.069（43% <0.05）⇒ 不稳
- 裁决：`need_more_info` / low ⇒ 仅假设生成

## 支持文件
- `scripts/cellcycle_validity_controls.R` — 一键跑阴性对照（marker 检出率 by 相位/组/供体）+ ICC/设计效应 +
  供体级置换 + n 核 bootstrap，输出 CSV 与控制台判定行（可直接改路径复用）
- `references/mf2000-cellcycle-case.md` — 上述 MF_2000 案例的完整数值、命令与产物路径