# 跨物种衰老响应「可替代性」量化 — 统计方法论 + 坑位（v3→v4 loop engineering 沉淀）

## 问题定义（专利最终目标）

用双物种海马 ATAC（人 40 个体 / 猴 ~20 个体）评估：**一个基因（或 CRE）的衰老响应在人／猴之间是否「可替代性」一致**，筛出「人猴海马某亚群保守性相似」的基因。这不是 CRECS 四类分类（A/B/C/D 序列+可及性保守），而是**第三层：衰老响应方向/幅度跨物种的一致性量化**。三件事严格分离，不许混为一谈：

| 层 | 定义 | 已做 |
|---|---|---|
| L1 序列保守 | phyloP/PhastCons 纯化选择保持 | ✅ |
| L2 活性/可及性保守 | 同源 CRE 两物种同脑区均有 H3K27ac/ATAC | ✅ CRECS (A/B/C/D) |
| L3 衰老响应守恒 | 两物种衰老时同方向/同幅度变化（本文件） | 🔶 本文件 |

**核心教训（用户连续三轮追问逼出的）**：「方向一致率」**不是**「保守性」。用一个词顶替三层 = 概念偷换，审稿人/老师一眼看穿。

## v3 四处硬伤 → v4 修正

| v3 缺陷 | 后果 | v4 修正 |
|---|---|---|
| `r_mean` = 基因内所有 tile 的 **r 算术平均** | 正负 r 抵消（+0.5 与 −0.5 → 0），真实信号抹平，符号变噪声 | **Stouffer Z 聚合**（见下） |
| 锚定时**丢掉 p 值**，只留 r | 浪费每 tile 的证据强度 | 全程保留 `(r, p)` 进入聚合 |
| 猴 n≈20 人 n=40 样本不对称，直接比 r 幅度 | 猴单基因 SE≈0.23 功效坍塌，不公平 | 面板级**置换检验** + 基因级 **Fisher z 异质性** |
| 没先做序列保守前置过滤 | 「序列保守」与「方向一致」混淆 | 三层分离（上表） |

### Stouffer Z 聚合（替代算术平均，带符号基因级效应）

```python
# 每个 tile 有 (r, p)，p 来自 ageDA 的年龄相关性检验
Z_tile = sign(r) * norm.ppf(1 - p/2)
Z_gene = sum(Z_tiles) / sqrt(n_tiles)     # 带方向 + 用 p 作为证据强度加权
p_gene = 2 * (1 - norm.cdf(abs(Z_gene)))
```

关键：**保留方向（sign）+ 保留证据（p）**，而不是把 r 直接平均。

## 坑位（都实踩过，逐条可复用）

1. **结论符号 bug（高危）**：置换检验只判 `p<0.05` 就打印「正相关→可替代」，**没检查 ρ 的符号**。实测 ρ=−0.1955 是**负相关**，脚本却打成「显著正相关→猴可替代人」。任何「方向一致性/可替代性」结论，**必须同时判符号和显著性**：`if p<0.05 and rho>0` 才写「正/可替代」，`rho<0` 写「显著负相关→分歧」。否则结论与数字自相矛盾。
2. **tile 数 ≠ 样本数（高危）**：保守性表里 `col6/col7` 列常是 **tile 数（n_tiles）**，不是个体数 n。算 Fisher z / 相关显著性时 n 必须用**个体数**，用 tile 数会让 SE 假性极小 → 假显著。样本数硬证据可从 p 值反推：`n = ...`（例：猴 r=0.435/p=0.055 → n=20；人 r=0.117/p=0.471 → n=40）。**拿到任何表先确认列含义，别把 tile 数当样本数。**
3. **ID 类型不匹配导致 0 对 ortholog**：猴 feature_table 的 gid 是 `int`，ortholog 桥的 key 是 `str` → `bridge[m]` 全 miss，pair=0。统一 `str(int(gid))` 再查。**跨文件 ID join 前先打印两侧各一个样例的 type() 对齐。**
4. **弱相关下「方向相反」≈ 抛硬币**：多数 |r|<0.16 时符号随机摆动，方向一致/相反接近 50/50（实测 46.4% vs 53.6%）。靠「数方向」分胜负必然失败 → 必须用**置换检验**定显著性，不能数比例。
5. **大 n 下弱效应也显著**：n=16029 时 ρ=−0.195 置换 p<0.001，但效应量只是「弱」。**报告时必须同时给 ρ（效应量）+ p（显著性）**，不可只报 p 说「强相关」。
6. **两侧统计量类型/分辨率不一致 = 伪相关（本轮定音根因，最高优先级）**：跨物种「可替代性/一致性」比较前，必须先确认两侧算的是**同一种量 + 同一分辨率**，否则比出来的是伪相关。本专利实测撞车：
   - 人侧（官方 `03_age_correlation`）＝**细胞类型特异的、40 donor 连续年龄 Pearson r**（`<celltype>_ATAC_pcc_donor_counts_filt_donors.tsv` 的 `cor` 列，Oligo/CA1/Astro/DG…18 类）。
   - 猴侧（`export_macaque_da.R`）＝`da_tiles.rds[strict/loose][Old/Young]` 的 **bulk 二分类 Old→Young 差异可及性**，无细胞类型拆分、无连续年龄。
   - 两者一个是「连续年龄相关」一个是「二分类 DA」、一个是「细胞类型特异」一个是「bulk」→ v4 跨物种 Spearman 比出 ρ=−0.1955 是**伪相关**，既非生物学也非批次，是量纲错配。
   - **判据**：拿任何跨物种统计量对比前，逐项核对〔统计类型(相关/DA)、年龄编码(连续/分组)、细胞分辨率(cell-type/bulk)、样本量结构〕四者两侧是否一致。不一致 → 先对齐再比，否则结论作废。

## 实操脚本 / 产物

- 脚本：`results/<sid>/scripts/v4_conservation_surrogacy.py`（tile 锚定 ±2kb → Stouffer → ortholog 桥 → 加权 Spearman + 2000 置换 + 高置信 panel `双侧 |Z|≥1.96 且同向`）
- 产物：`v4_gene_conservation.csv`（16029 基因 symbol/Z_m/Z_h/双侧 p/n_tiles/方向）、`v4_conservation_stats.txt`
- 加权 Spearman：`wspearman` 用 `scipy.stats.rankdata` 加权；

## 正向对照方法论（检测算法假阴性）

用一个**文献确证**的基因做正向对照，看算法会不会把它错漏：

- **BNIP3**（线粒体自噬受体，BCL2 家族，HIF-1α 诱导）：文献支持人海马 CA1 随龄**下降**（人 r=−0.157 与文献同向）。但猴 r=+0.112 反向 → 被 v3「方向一致」规则筛掉 → 揭穿算法漏检真阳性。
- 教训：**「方向相反」不是垃圾，反而是专利亮点**（保守基因的人猴衰老反应分歧 = 人谱系特异衰老脆弱性）。必须单独成 panel（含 Fisher z 显著性），不能一刀切当噪声丢弃。
- 每次改算法都用这类已知基因验一次，看是否还漏。

## 关键发现（引导下一步，非最终结论）

v4 实测：加权 Spearman **ρ(Z_h, Z_m) = −0.1955，置换 p<0.001**（显著**负**相关）。含义：16029 基因层面人猴衰老响应**反向**，「猴可替代人」在海马整体层面**不成立**。但 ρ 只有 −0.195（弱），且方向接近五五 → 这个负相关待消歧：

- **真实生物学**？人谱系特异衰老脆弱性（呼应 BNIP3「人降猴升」反向模式）
- **技术假象**？人 40 / 猴 20 跨数据集未消除的批次/深度/mappability 偏倚

消歧下一步：按染色体（用户已确认「按染色体分层背景比全基因组统一背景更合理，避免 GC/重组率系统偏差」）拆 ρ，看负相关是否由特定染色体/GC 极端区的基因驱动；若集中在少数染色体 → 技术偏倚，需先各自物种内做技术因子回归再比。

## 负相关根因定音（后续轮次，比「染色体/批次」更根本）

诊断顺序升级：**在怀疑「真实生物学 vs 技术批次」之前，先怀疑「两侧量纲不一致」**（见坑位 6）。本轮坐实：ρ=−0.1955 的直接来源是人侧「细胞类型特异连续年龄 r」与猴侧「bulk 二分类 DA」错配，不是数据集批次。因此消歧优先级重排为：① 对齐统计量（猴侧也用连续年龄重算 cell-type 级 r）→ ② 才轮到染色体/GC 分层、物种内技术因子回归。

## 猴侧连续年龄数据位置（「拿 20 只猴真实年龄」的落点）

- **连续年龄数值本地就有**：`results/<sid>/task2/results/monkey_cellColData_anno8.rds` 的 `Age` 列（161497 细胞），取值 `5/10/11/12/22/23/28/29/31`；21 只猴按 `Sample` 前缀分四组：`Y3-Y7`(Young=5)、`M1-M5`(Middle=10/11/12)、`O1-O6`(Old=22/23)、`V1-V6`(Very old=28/29/31)。
- 张潇/2026 macaque atlas 正文只给年龄组范围（young 5-6/ middle 10-12 / old 22-23 / exceptionally-old 28-31），**精确个体年龄在 Supplementary Table S2A**（NHPABC https://db.cngb.org/stomics/nhpabc/ 或 Zenodo 10.5281/zenodo.20482872）；但本项目猴 Age 列已直接落在 cellColData，不必再下载。
- **缺的是重算连续年龄 r 的必需输入**：猴侧 `每个 500bp tile × 21 猴` 的可及性矩阵。本地只有集群已算好的 `monkey_ageDA_all.csv`（530万行 r/p/q 产物），其产生脚本**不在本地**（搜 E:/专利 全部 .R/.py 0 命中），矩阵与产生脚本都在远端集群。→ 要重算猴侧连续年龄 r，需用户从集群导出「tile×个体 可及性矩阵 + 连续年龄」。
- **两物种集群路径已坐实（task_plan 45 行）**：人 40/40 Arrow 指向 `/hwfssz3/PS_JLU/zhangbo/jupyter_zb/Patent/`；**猴 63/63 Arrow 指向 `/hwfssz3/PS_JLU/zhangxiao6/`**（区别于人的 zhangbo 路径，别写错用户目录）。
- **导出脚本已就绪**：`scripts/export_per_sample_tile_matrix_continuous.R`（本 skill）——从猴侧 ArchR project 提取 21 sample × tiles 稀疏矩阵 + tile 坐标 + 连续年龄，含 ArchR API 已实证签名（getMatrixFromProject 有 binarize 参数、addTileMatrix 默认 tileSize=500/excludeChr=chrM&chrY、getCellColData 用 select）。跑完 3 产物下载回本地即可算连续年龄 tile 级 Pearson r。
- 人侧官方方法口径（对照基准）：`Human_Hippocampus_ATAC/official_scripts/aging_human_hippocampus-main/03_age_correlation/` 下 `ATAC_age_correlation/` 逐 celltype 的 `_ATAC_pcc_donor_counts_filt_donors.tsv`（`cor`=连续年龄 Pearson r，40 donor）。

## ✅ 口径对齐定音（2026-09-03 完成：猴侧连续年龄重算，ρ 定量变化）

坑位 6 的量纲诊断被定量证实。用户从集群导出后本地重算完成：

- 3 输入文件：`monkey_tile_matrix_samples_x_tiles.rds`（**20 个体** × 608万 tile dgCMatrix，值域 6e-5~0.999 即 0~1 可及比例）+ `monkey_sample_age.csv`（20 猴连续年龄 5/10-12/22-23/28-31）+ `monkey_tile_coords.csv`（608万 tile 坐标，0-based）
- 本地 R 向量化 Pearson（见下）重算 → `monkey_ageDA_continuous.csv`（567万 tile，r∈[−0.851, 0.857]，过滤 6.8% 全0 tile；与人侧 human_ageDA_all.csv 555万行同量级）
- v4b 重跑（输入 monkey_ageDA_all.csv → monkey_ageDA_continuous.csv）：**ρ 从 −0.1955 缩到 −0.0810**（掉约 60%），置换 p 仍 <0.001
- **定音结论**：二分类口径伪影占约 60%；但对齐后 ρ 仍显著负相关 → 整体「猴可替代人」依然不成立（方向相反 58.4% 主导）
- **真实信号在基因级**：1904 基因双侧同向显著（|Z|≥1.96），几乎全是「衰老可及性下降」（SLC1A2/NRXN1/GRIA1/GRIA2/CELF2 等神经元/突触基因，Z=−12~−34）→ 跨物种保守衰老脆弱性真实存在，只是被多数反向基因淹没在面板级 ρ
- **下一步转向**：放弃「整体可替代」，转「保守衰老脆弱基因集」机制分析（这 1904 基因是什么通路、为何跨物种保守下降）

## ⚠️ ArchR TileMatrix 从 Arrow 导出三连坑（本轮实测）

7. `binarize=FALSE` → 报 `Sparse Matrix in Arrow is Binarized! Set binarize = TRUE`：TileMatrix 在 Arrow **存的是二值化矩阵**，必须 `binarize=TRUE`；聚合到个体后是 0~1 可及比例，正是做连续年龄 Pearson 的正确量。
8. `binarize=TRUE` 时 `rowRanges(se)` 返回 `NULL`（SE 对象没附 GRanges，报 `unable to find an inherited method for 'seqnames' for signature '"NULL"'`）→ tile 坐标（seqnames/start/end）必须从 `getFeatures(proj, useMatrix="TileMatrix")` 取，不能走 rowRanges。
9. cellColData 里 `Sample`（61 个建库/批次标签）≠ `Individual`（20 只猴个体）。统计单位必须用 `Individual`，用 `Sample` 会把 20 猴拆成 61 伪样本，年龄相关全盘错。

## R 稀疏矩阵向量化 Pearson 相关（百万 tile 级，禁止 dense 化）

20 样本 × 608万 tile 的 dgCMatrix `M`，逐 tile 算 age-Pearson r，dense 化会 970MB：

```r
age_c <- age - mean(age); ss_age <- sum(age_c^2)      # age_c 中心化和=0，故无需显式中心化 M
num <- as.vector(t(age_c) %*% M)                       # 分子（协方差，1×p）
cs <- as.vector(Matrix::colSums(M)); cs2 <- as.vector(Matrix::colSums(M * M))
ss_col <- cs2 - cs^2 / n                               # 列方差×n
r <- num / sqrt(ss_age * ss_col); r[!is.finite(r)] <- NA   # 全0 tile 方差0→NA
t_val <- r * sqrt((n-2) / pmax(1 - r^2, 1e-12)); p <- 2 * pt(-abs(t_val), n-2)
```

O(nnz)=1.02 亿非零值，R 几秒跑完。脚本：`results/<sid>/scripts/compute_monkey_continuous_age_r.R`。输出 CSV 列须与人侧同格式 `chr,start,end,r,p,q`（q=p.adjust BH），v4 anchor 只读前 5 列、忽略 q。

## ✅ 逐基因「可替代性标注表」方法 + 定音结果（2026-09-04 完成）

**方法学定音**：整体加权 Spearman ρ 是「错的问法」——把所有基因打包成一个数判「能不能替代」是死胡同（呼应坑位 4/5/6）。**真正交付物是逐基因方向性标注表**，每基因四分类：

| 标注 | 判据 | 含义 |
|---|---|---|
| 保守·可替代(down/up) | `same_direction=True` 且双侧 p<0.05 | 跨物种同向显著，衰老方向一致 |
| 分歧·不可替代 | `same_direction=False` 且双侧 p<0.05 | 一侧上调一侧下调，方向相反 |
| 单侧特异 | 仅一侧 p<0.05 | 物种特异衰老响应 |
| 不显著 | 双 p≥0.05 | 无跨物种信号 |

生成代码（pandas apply，输入 = v4b 的 16031 基因结果 CSV）：

```python
def label(r):
    both_sig = (r['p_monkey']<0.05) and (r['p_human']<0.05)
    if r['same_direction'] and both_sig:
        d = 'down' if (r['Z_monkey']<0 and r['Z_human']<0) else 'up'
        return f'保守·可替代({d})'
    if not r['same_direction'] and both_sig: return '分歧·不可替代'
    if r['p_monkey']<0.05 or r['p_human']<0.05: return '单侧特异'
    return '不显著'
# 产物 v4b_gene_substitutability_table.csv（16031 行 × symbol/effect/substitutability/Z_m/Z_h/p_m/p_h/n_tiles_m/n_tiles_h）
```

**定音分布**：保守·可替代 1904（下调 1680 + 上调 224）/ 分歧·不可替代 3487 / 单侧特异 7562 / 不显著 3078。

**保守基因生物学身份定音**：1904 保守基因 88% 是「衰老下调」，几乎全部集中在**谷氨酸能突触、钙信号、轴突导向**三条通路 = 海马兴奋性神经元（ExN）核心功能基因。代表下调：SLC1A2(EAAT2 谷氨酸转运体)、NRXN1(neurexin)、GRIA1/GRIA2(AMPA 受体)、NELL2、RYR2(兰尼碱受体钙释放)、ROBO1/EPHA6/CTNNA2/FAT3(轴突导向)、NRG1(neuregulin)；上调 224：RBFOX3(=NeuN 神经元核标志)、SHANK2(突触后支架)、SORCS2、KCNQ1/KCNT1(钾通道)。

**专利卖点落点**：真实跨物种保守衰老信号 = 「兴奋性神经元突触功能相关染色质可及性一致下降」。整体 ρ 被 3487 分歧 + 7562 单侧特异基因淹没，但逐基因标注把保守基因精准捞出。下一步 = 对 1680 下调保守基因做 GO/KEGG 富集，把「谷氨酸能突触/钙信号」升级成有 p 值的通路统计硬证据。

## ⚠️ 坑位 10：基因级 Z 符号翻转 — Stouffer 加权固有特性（2026-09-04 实踩，高危）

Stouffer 聚合 `Z_tile = sign(r) × norm.ppf(1−p/2)` **对每一个 tile 都加权**——p≈0.5 的不显著 tile 贡献 `norm.ppf(0.75)=0.674`（**不是 0**），p<0.05 的显著 tile 才贡献 ~2~3。副作用：**基因级 Z 的符号由 ~94% 不显著 tile 累积主导，可能与 ~6% 显著 tile 的方向相反**。

实测撞车：人侧 `human_ageDA_all.csv` 全量 tile r<0 占 58.8%、p<0.05 显著 tile r<0 占 65.4%（显著负主导），但基因级 `Z_human` 却 ~41% 负（翻成正主导）——违反「显著 tile 负为主 → 基因 Z 应偏负」的直觉，一度被误判为数据 bug。

> ⚠️ **根因已再定音（2026-09-04 深挖）**：坑位10 最初判「Stouffer 加权固有特性」是**次因**，**主因是 Simpson 悖论**——人海马「基因本体区域」可及性随衰老**上升**（基因内负 tile 仅 46.5%），基因间区下降（~68.5% 负），所以「全基因组 tile 58.8% 负」与「基因锚定后 40.6% 负」方向分叉是**真实生物学结构，不是 bug**。详见文末「坑位 11」。

**诊断三步（先查再报 bug）**：① 全量 tile r 符号分布（两侧都应 ~57% 负，人猴一致）→ ② `p<0.05` 显著 tile 的 r 符号分布（「显著方向」）→ ③ 基因级 Z 符号分布。若 ② 与 ③ 方向相反 → **先按坑位 11 查「基因本体区域 tile vs 基因间区 tile 方向是否分叉」（Simpson 悖论），排除后再考虑 Stouffer 加权特性**。解法二选一：
- 要「显著方向主导」→ 改**显著 tile 加权聚合**（只对 p<0.05 tile 做 sign 投票，或权重截断 `max(0, |Z_tile|−0.674)`）；
- 维持 Stouffer → 但**明确报告「基因级 Z 方向」与「显著 tile 方向」是两个不同口径**，方向迁移结论必须以基因级 Z 的符号为准（预测公式用的就是 Z 符号）。

## 坑位 11：基因级 Z 符号翻转的**真正根因 = Simpson 悖论**（2026-09-04 定音，纠正坑位10）

坑位10 把「基因级 Z 符号 ≠ tile 级显著方向」归咎于 Stouffer 对所有 tile 约等权加权的固有特性。**深挖后主因不是加权，而是基因锚定窗口带来的区域选择性偏倚**：

人侧实测（逐层交叉验证，诊断顺序：按染色体→按 tile 数分箱→基因内负 tile 占比→ΣZ 符号）：

| 层级 | 人侧 | 猴侧 | 判定 |
|---|---|---|---|
| 全量 tile 负占比 | 58.8% | 57.3% | 一致偏负 |
| 显著 tile(p<0.05) 负占比 | 65.4% | 60.2% | 一致偏负 |
| **基因内 tile 负占比** | **46.5%** | **60.8%** | **分叉点** |
| 基因级 Z 负占比 | 40.6% | 80.4% | 分叉 |
| 基因级 ΣZ | +20115 | −31011 | 方向相反 |

**根因定位**：人海马衰老时，**基因本体区域**（外显子/内含子周边 ±2kb）的可及性**上升**（基因内负 tile 仅 46.5%），而**基因间区**（intergenic，占全基因组 tile 大头）可及性**下降**（~68.5% 负）→ 全基因组 tile 的「负主导」是由基因间区贡献，基因锚定后只保留「基因本体附近 tile」，方向翻正。猴侧无此区域分叉（基因本体+基因间区一起下降），故基因级 Z 正常「放大负向」。

**教训（通用方法论）**：跨物种「tile 级方向」与「基因级方向」不一致时，**第一嫌疑不是统计聚合方式（Stouffer），而是锚定窗口导致的区域选择性偏倚（gene body vs intergenic 方向本来就不同）**。先做「基因内 tile vs 非基因区 tile 方向对比」这一层验证，再归咎算法。这本身是**生物学发现**（人谱系特异：基因本体随龄激活、调控区关闭），可写进专利，不是要修的 bug。

## 专利独权最终定音（2026-09-04 用户拍板 + 置换检验）

**方向迁移预测公式**与「整体 ρ 判可替代」彻底分离，专利保护的是后者抽象出的方法：

```python
S(g) = min(|Z_monkey(g)|, |Z_human(g)|) * sign(Z_monkey(g) * Z_human(g))  # 可替代性评分
tau = 1.96   # 自动导出双侧 p<0.05，非拍脑袋
分级: S>τ且同向=A可替代 / S<-τ且反向=B不可替代 / 单侧显著=C物种特异 / 双不显著=D证据不足
```

**置换检验定音（双向）**：真实 ortholog 桥接下 A级（同向保守）1904 < 随机 2274（p=1.000 显著低于随机）、B级（反向）3487 > 随机 3117（p=1.000 显著高于随机）→ 真实一对一 ortholog 关系下同向反而比随机更少。**结论：海马衰老方向跨物种系统性反向，「猴可预测人」被数据否定**，不是「待消歧」。这摧毁了「1904 保守基因=专利卖点」的乐观叙事，专利重心从「找保守基因」转到「方向迁移预测方法 + 可替代性评分公式本身」——**方法本身（可复现、逐位点、分级方向标注）才是可授权客体，而非某个具体正向结论**。

## 专利三件套交付框架（用户验收标准）

用户对「做出来」的定义 = **能被验证 + 有创新 + 逻辑没有错误 + 可复现**。交付必须四件齐全：① 交底书（独权重心=方向迁移预测+可替代性评分，Phan2025引为背景、增量声明=「系统性检出+分类+评分」）② 权利要求书（独权+从权，LMM 作替代实施方式）③ 实施例（逐基因标注表数据）④ 可复现脚本 + 置换检验。评分公式是独权灵魂，必须先定公式（方案B=方向一致性×效应量）再写独权。

## 方向迁移预测公式（预测器代码，配合上面评分公式使用）

用户最终要的不是「整体 ρ 判可替代」，而是一个**可被置换检验验证的「预测方向」公式**：

```python
predict_human_direction(g) = sign(Z_monkey(g))      # 用猴侧衰老方向预测人侧
accuracy = mean(sign(Z_human) == sign(Z_monkey))    # 方向一致率
```

**关键设计：置换检验要和 null 分布比，不能和 50% 比**——d_m/d_h 都偏负，随机配对的同向率期望 ≠50% 而是依赖边际分布（实测 ~44%）。脚本 `predict_direction_transferability.py` 用 `perm_two_sided` 双侧偏离检验。首次实测：全量方向一致率 41.55% < 随机期望 44.29%（p=0.001）→ 不支持「猴预测人」，反而显著反向；「双侧显著」基因同向率更低（35.32%）→ 衰老效应越强、人猴方向越反向。最终定音（双向置换检验）：真实 ortholog 桥接 A级 1904 < 随机 2274、B级 3487 > 随机 3117，同向反而比随机更少 → 「猴可预测人」被数据否定。方法本身（逐基因方向标注 + 置换检验 + 方向迁移预测 + 可替代性评分公式）是稳定可授权客体，具体结论是反向分歧。