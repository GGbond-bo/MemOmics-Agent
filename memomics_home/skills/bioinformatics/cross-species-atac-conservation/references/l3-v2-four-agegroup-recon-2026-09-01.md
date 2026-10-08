# L3 新版规划侦察（2026-09-01 · 四年龄组 + 同一数据底 + 序列保守层进独权）

用户三点指示：① 加跨物种序列保守一层（保守性打分进独权，工作量更大）；② L3 用最新四年龄组数据，保证 L1/L2/L3 同一数据底；③ `archive_old_da_v1/` 旧结果确认废弃。
本文件 = 本轮只读侦察的权威事实（供 L3 重启时直接复用，勿重复探测）。

## 1. 数据底定义（L1/L2/L3 同一数据底的唯一权威）

- **个体集 = 40 人 + 20 猴（M4 剔除）= 60 个体**；基因集 = **14,927 RBH 基因**（reciprocal best hit ortholog）
- 载体：`E:/专利/P3_L2_data/l2_gene_individual_matrix.rds` —— 注意是 **list 不是矩阵**：
  - `mat_m_gene`: 14,927 × 20（猴基因表达/活性矩阵）
  - `mat_h_gene`: 14,927 × 40（人）
  - `meta60`: 60 × 3（个体元数据表，40 人 + 20 猴）
  - `gene_names`: character（14,927）
  - `log_m`/`log_h`: 13,6654 × 20/40（峰级）
  - `gene_map`: 13,6654 × 3（峰→基因映射）
  - `rbh`: 13,6654 × 3（RBH 峰对表）
- 复用 L3 时直接 `gm <- readRDS(path); mat_h <- gm$mat_h_gene; ...`；⛔ 同一 43MB rds 重复 readRDS 3 次会偶发 Windows 文件锁 `cannot open the connection` —— 读一次赋变量再拆。

## 2. 四年龄组覆盖不对称（关键输入约束）

人猴 meta 的年龄组**术语完全一致**：Young / Middle / Old / Exceptionally old（EO）。

| 物种 | Young | Middle | Old | EO | 有组别个体 | 总个体 |
|------|-------|--------|-----|-----|-----------|--------|
| human | 20–38 (7) | 41–55 (8) | 65–79 (7) | 82–89 (5) | **27 / 40** | 40 |
| monkey | 5 (1) | 10–12 (3) | 22–23 (2) | 28–31 (3) | **9 / 21** | 21 |

- ⚠️ **human 有 13 个个体、monkey 有 12 个个体没有 age_group 标签**（meta 列缺失）——四年龄组分析只能用**带组别标签的个体**（人 27 / 猴 9）；M4 剔除后猴 20 个体里仍有 11 个无组别。L3 重启时先与用户确认这些无标签个体是补标还是排除。
- monkey Age 分组与张潇原稿一致（Young 5-6 / Middle 10-12 / Old 22-23 / EO 28-31），meta 实际值完全落在组内。

## 3. archive_old_da_v1/ 废弃清单（新管线零引用）

位置：`E:/专利/P3_L1_data/archive_old_da_v1/`（不是 E:/专利 根目录）。废弃文件：
- `l1_phylop_results.csv` / `l1_phylop_local_results.csv` / `human_da_Young_phylop.tsv` / `human_da_Old_phylop.tsv` / `test5_phylop.tsv`（旧 UCSC API 版 phyloP）
- `l1_seq_scores.csv`（旧序列打分）
- `l2_accessibility_scores.csv`（旧基因级 DA）—— P4 CRECS 旧版读它，**必须换新版 L2 RBH 输出**
- `p4_crecs_scores.csv`（旧 CRECS，26 tiles 测试版）
- `l3_motif_topTF.csv`（旧 L3 topTF）

新版权威产物在 P3_L1_data 根目录：`l1_full_human_v4` / `l1_full_monkey_v4`（三轨道 + NBG=1000 + BH-FDR）、`p4_crecs_scores.py`（脚本新版，但**仍引用废弃输入**——重跑前必须改输入路径）。

## 4. P4 CRECS 旧版已知缺陷（升级 = 进独权必改）

`p4_crecs_scores.py`（测试版，脚本注释自认"简化"）：
- `CRECS = 0.4*L1 + 0.3*L2 + 0.3*L3`（手工权重，测试版占位）
- 分类：A=CRECS≥0.8 / **B=序列保守但 TF 结合分歧（专利核心）** / C=中间 / D=L1=0
- ⛔ **L3_score 用固定 Jaccard 代理**（`jacc = {'Old': 0.020, 'Young': 0.070}.get(group, 0.05); l3_score = min(1.0, jacc*5)`）——这是 08-09 测试版的 group 级 Jaccard，**不是逐 tile 真实 motif 命中**；正式版必须用 L3 新版（四年龄组真实 motif 富集 Jaccard）替换
- ⛔ **L2_score 用 `l2_accessibility_scores.csv`（已废弃）**；正式版换 `mat_h_gene/mat_m_gene`（40+20 个体 RBH 基因活性）的 DA 密度
- L1_score 目前是 `phylop_mean > 0` 二值化 → 正式版按用户已确认原则改**逐染色体背景零模型**（phyloP 相对背景百分位/z-score，见 SKILL.md L1 v2 专业版）

## 5. L3 新版执行方向（重启时按此走）

旧版 L3（`l3_human_motif.R` + `l3_motif_compare.R`，P3_L1_data）只有 **Old/Young 两组** DA tiles（`da_tiles_strict_Old.bed` / `da_tiles_strict_Young.bed`，0-based）→ JASPAR2020 + matchMotifs(out="scores") + GC 匹配背景 → fc ranking → topN Jaccard 对比。

新版 = **4 年龄组 × 2 物种 = 8 组 DA tiles**：
1. **集群重跑四年龄组 DA tiles**（人 40 样本 / 猴 20 个体，M4 剔除）——唯一必须用户/集群做的事（本地 Arrow 全指向远端集群读不了）；8 个 bed 传回 `E:/专利/P3_L1_data/`
2. 本地 R motif 富集（R 4.5.3 + JASPAR2020/motifmatchr 已有）→ 8 组 rank CSV → **真实 topN Jaccard**（替换 CRECS 固定代理）
3. CRECS 升级：L1(染色体背景 phyloP) + L2(新版 RBH DA 密度) + L3(真实 Jaccard) → 打分 + A/B/C/D → B 类作为独权技术特征
4. 需要用户决策：CRECS 权重（保持 0.4/0.3/0.3 + 敏感性分析 vs 逻辑回归校准）；猴侧序列保守来源（沿用 ortholog 映射查 hg38 phyloP，不需要 MFA8 自重 track）；四年龄组比较设计（建议沿用 L2 的 age_group 序贯/无序 factor，与主模型一致）

## 6. L3 旧版脚本要点（复用注意事项）

- `l3_human_motif.R`：读 da_tiles_strict bed（0-based → start+1）→ BSgenome.Hsapiens.UCSC.hg38（seqnames 带 chr，**保留前缀**否则报 `sequence 8 not found`）→ matchMotifs(out="scores") → 背景 = 2000 随机 GC 匹配 tile → fc = fg_mean/bg_mean 排序
- `l3_motif_compare.R`：JASPAR MA ID → TF 名（`sapply(motifs, function(m) m@name)`，**禁止 `subset(motifs, name==m)`**）→ simplify `sub("::.*$","",tf)` → Jaccard 四对（人Old-猴Old / 人Young-猴Young / 对角交叉）
- 猴侧 rank CSV 在 `E:/专利/ArchR_Output/motif_rank_{old,young}.csv`（列名待确认，脚本用 `ifelse("tf" %in% colnames...)` 自适应）