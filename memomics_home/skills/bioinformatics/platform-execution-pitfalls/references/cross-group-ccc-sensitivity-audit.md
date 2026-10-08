# 跨组细胞通讯比较（CellChat 等）——敏感性审计与结论口径

> 适用：任何「两组及以上条件」（aging / disease / timepoint / treatment）的配体-受体通讯对比。
> 实测来源（2026-09-24，人骨骼肌 MF young vs old，CellChat 1.6.1，1502 cells / 10 亚群）：
> 原始结论「Young 通讯强度是 Old 的 2.58×、PTPRM 为 Young 独有通路」**经审计整体撤回**。

## 0. 三条硬事实（为什么必须审计）

| 事实 | 实测值 |
|------|--------|
| 组间测序深度常不匹配 | Young 中位 nCount 6302 / nFeature 2857 vs Old 4414 / 2192 → **深度 1.43×、检出基因 1.30×** |
| 深度匹配后结论反转 | 大组 counts 二项稀释到小组中位深度：通路 **14→3**、总权重 0.12282→0.03162、每细胞强度 1.36e-4→**3.51e-5**、vs Old 由 2.58× 变 **0.67×**、PTPRM 消失 |
| **指标方差极大（最致命）** | 目标深度 **4411 vs 4414（差 3 UMI = 0.07%）**、同 seed、同脚本、同 nboot → **7 vs 3 通路、8.19e-5 vs 3.51e-5（2.3 倍差）** |
| 剂量反应非单调 | 100/85/70/55/40% 深度梯度下 vs-Old 比 = 2.33 / 0.87 / 1.55 / 1.13 / 0.50× → 无干净单调剂量关系 |

⇒ 判据：**组间深度差 >1.2× 或单组细胞数 <1000 时，CellChat 的总权重 / 通路数 / top 通路排序不能直接支撑方向性生物学论断。**

## 1. 审计清单（A–G）——每项一个独立 Rscript 进程

| 项 | 做什么 | 判读 |
|----|--------|------|
| **A** 深度/检出量 | 两组 median nCount / nFeature + 逐亚群中位深度表 | 比 >1.2× 即标记混杂 |
| **B** 去 top 通路重算 | `relflow(cc, exclude="PTPRM")` 比较去前后相对信息流 | 单通路占比 >50% ⇒ 分母效应风险 |
| **C** 等细胞下采样 ×5 | 大组随机下采样到与小组等细胞数，**每次独立进程 + 独立 seed** | 优势仍在 ⇒ 细胞数不是主因 |
| **D** 小群去半 | 小群（<60 cells）随机去一半后重跑 | 核心通路消失 ⇒ 小群驱动（可疑） |
| **E** 深度匹配（关键） | 大组 counts **二项稀释**到小组中位深度后重跑 | 结论反转 ⇒ 深度是主因 |
| **F** 剂量反应 | 多梯度稀释（1.0/0.85/0.70/0.55/0.40×） | 非单调/跳变 ⇒ 指标不可靠 |
| **G** 样本级 pseudobulk | 按 **samplename**（供体×条件）聚合 → log2CPM → `lm(y ~ grp + PrePost + log10(depth))` | **正确推断单位**；FDR 全不过 ⇒ 无支持 |

### E/F 的二项稀释（比"取子集"更干净）

```r
thin_to <- function(yng, target, seed = 20260924L) {
  cnt <- as(GetAssayData(yng, assay = "RNA", layer = "counts"), "CsparseMatrix")
  n_i <- Matrix::colSums(cnt); p_i <- pmin(1, target / n_i)   # 低于目标深度的细胞保留 100%
  colidx <- rep(seq_len(ncol(cnt)), diff(cnt@p))
  x <- cnt@x; stopifnot(max(abs(x - round(x))) < 1e-6)        # 必须整数 counts
  set.seed(seed)
  cnt@x <- as.numeric(rbinom(length(x), size = as.integer(round(x)), prob = p_i[colidx]))
  meta_keep <- data.frame(annotation_L3 = yng$annotation_L3, row.names = colnames(yng))
  CreateSeuratObject(counts = cnt, meta.data = meta_keep)
}
```

- 目标深度取小组 **counts 列和**（`Matrix::colSums(GetAssayData(old, layer="counts"))`），**不要读 meta 的 nCount_RNA**（瘦身文件可能没这列）。
- ⚠️ 别传 `meta.data = old@meta.data`——旧 `nCount_RNA/nFeature_RNA` 会带进新对象，**掩盖真实稀释效果**（实测打印出原值 6302 而非 4414）。只传分组列，让 Seurat 从 counts 重算。

### G 样本级检验（最容易漏、却是正确推断单位）

```r
pb <- sapply(keep_sm, function(x) Matrix::rowSums(cnt[, colnames(s)[s$samplename == x], drop = FALSE]))
lg <- log2(t(t(pb) / colSums(pb) * 1e6) + 1)
fit <- lm(lg[g, ] ~ factor(grp, levels = c("Old","Young")) + factor(pp) + log10(med_depth))
```
实测（n=33 样本）：**30 个 LR 基因 FDR<0.05 者 0 个**；PTPRM β=+0.251, p=0.091, FDR=0.273（**样本级不显著**）；深度协变量 7/30 显著（COL3A1 p=6e-4、FN1 p=5e-3、LAMA2 p=6e-3、DON p=0.011）。

### 深度分层置换（泛表达同源 LR 专用）

按深度五分位分层，在**层内**置换组标签 1000 次：PTPRM+ 率未分层差 7.67 百分点 → **同层内仅 3.25 百分点**（深度解释 58%），分层置换 p=0.033；内皮 marker PECAM1 各层内两组几乎一致（23.25% vs 23.29%）⇒ 深度依赖属**检出门限效应**，非组间生物学。

## 2. 结论口径（claim calibration）

| 允许写 | 禁止写 |
|--------|--------|
| 本数据规模 / nboot=100 下指标不可靠 | 衰老增强 / 减弱 |
| 非方向性探索性通道清单（须标注不可与深度分离） | 组 A 独有 / 组 B 特异 |
| 差异与测序深度及阳性检出门限不可分离 | 某通路驱动 / 衰老通路 |
| 重开条件（补什么才能升级结论） | 「纯伪像 / 假信号」（证据不足，不能定罪） |
| | 深度已校正 / 供体级显著 / 最终结论 |

**泛表达同源互作（如 PTPRM-PTPRM）推荐措辞**：
「其出现/占比与测序深度及阳性检出门限不可分离，且该基因泛表达；本数据中暂不解读为组 X 独有通路；不能判为纯伪像。」
佐证：PTPRM 阳性率 93.2%(Young)/85.6%(Old)（非细胞类型特异），**阳性率随深度五分位 69.8→86.7→97.0→98.0→99.3% 单调上升**；5 次等细胞下采样仅 3 次出现；去 PTPRM 后首位变 EGF(51.1%)。

## 3. 预注册稳健性阈值（升级为方向性结论的必要条件）

| 指标 | 阈值 |
|------|------|
| 通路跨 seed/深度出现频率 | ≥ 80% |
| top 通路排名波动 | < 10% |
| 每细胞强度 CV | < 20% |
| 效应量 95% CI | 不含 0 且方向一致 |
| 样本级检验 | FDR < 0.05 且方向与细胞级一致 |

**复跑结果出来前不得挑选最优 seed/深度**（事后挑选会使阈值失效）。

## 4. 工程写法

- 一脚本 + 模式分发：`Rscript audit.R <A|B|C <rep>|MERGE|D|E|DR|NB <seed>>`，**每个模式一个全新 Rscript 进程**（进程退出即释放内存，规避单进程累积多 CellChat 对象导致的 OOM）。
- 驱动用 bash 顺序调用 + 单 rep 失败重试 1 次（间隔 20s）+ 模式间 sleep 3–5s。
- 产物：`10_downs*.csv / 11_drop*.csv / 12_depth*.csv / 13_small*.csv / 14_depthMatched*.csv / 17_dose_response.csv / 19c_*_permutation.csv / 21_sample_level_LR_lm.csv`；图 `20_audit_dashboard`、`21_*_depth_dependence`、`22_sample_level`。
- 出图含中文标签时**不要用 R 的 png()/pdf()**（见 SKILL.md「R 设备 CJK 编码失败」行）——改 Python matplotlib + `msyh.ttc`。