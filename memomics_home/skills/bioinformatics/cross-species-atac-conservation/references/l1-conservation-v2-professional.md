# L1 保守性专业版 v2 —— 三轨道 + 背景零模型（2026-08-31）

用户要求"更专业更全面的重做 L1，看看别人是怎么做的"——对照领域标准（Pollard 2010 phyloP / Zoonomia Christmas 2023 / Dukler 2020 Phylo-HMM / Siepel phastCons 元件 / Villar 2015 增强子保守性）把初版单轨 mean>0 二值化升级为三轨道 + 背景零模型 + 连续分数统计。

## 脚本与文件

- 脚本：`E:/专利/P3_L1_data/l1_conservation_v2.py`
- 输入：`l1_seq_scores.csv`（40 DA tiles，18 Old + 22 Young，8 基因：DLD/ULK4/TTC29/FAM156A/CAMK1D/MYOM2/GSTM5/SNED1）+ `macaque_da_gene_map.csv`（gene_start/gene_end）
- 输出：`v2/l1_v2_results.csv`（40 行 × 22 列）、`v2/l1_v2_gene_aggregated.csv`（8 行 per-gene）、`v2/figures/l1_fixv2_three_tracks.png`、`l1_fixv2_bg_element.png`
- 轨道（本地 `E:/专利/L1_resources/`，WSL 里 `/mnt/e/专利/L1_resources/`）：
  - `hg38.phyloP100way.bw`（哺乳动物 100 物种全谱）
  - `hg38.phyloP30way.bw`（灵长类专用，**跨物种/衰老信号更敏感**）
  - `hg38.phastCons100way.bw`（保守元件后验概率，0-1）

## v2 五要素升级

1. **三轨道交叉验证**：同一窗口三轨齐打，成熟分工 = phyloP 看碱基级约束速率、phastCons 看元件级保守区块、phyloP30 看最近缘谱系。
2. **连续分数保留**：Mann-Whitney U + Cliff's delta + Cohen's d + Bootstrap 5000 次 95% CI。不做 mean>0 二值化——二值化把近零噪声放大成"保守/不保守"假差异（初版 55.6% vs 81.8% 即此产物，修复版连续分 p=0.14 证明是伪差异）。
3. **背景零模型**：每 tile 同染色体随机 200 个 5kb 窗口 → tile 分数的百分位 + z-score。无 hg38 序列时做不了 GC-match，同染色体随机是可接受的妥协（结果注明局限）。
4. **phastCons 元件判定**：窗口内 posterior>0.5 碱基占比 ≥50% = 保守元件 overlap（金标准判定）。
5. **双口径统计**：per-tile（Wilcoxon，报告非独立警告）+ per-gene（同基因多 tile 取中位数，8 基因探索性）。

## ⛔ 踩坑 1：frac 相对位置映射不可丢（最致命）

- **症状**：同一基因所有 tiles 拿到完全相同 phyloP 分数（DLD 的 Old 5 tiles 和 Young 10 tiles 全是 -0.0254）；per-gene 聚合表 Old/Young 中位数完全相同。
- **根因**：v2 重写时偷懒用基因中心点窗口 `center = (lo+hi)//2`，丢掉了初版 l1_phylop_local.py 的 frac 相对位置映射。
- **后果**："40 tiles"坍缩为 8 个独立窗口 → Old/Young 差异变成基因组成差异，统计完全失真（曾制造"无差异"假结论）。
- **修复**：窗口必须 `frac = (tile_start - 猴gene_start)/(猴gene_end - 猴gene_start)` → `h_pos = hg38_gene_start + frac*(hg38_gene_end-hg38_gene_start)` → `h_pos ± 2500`（BNIP3 铁律的窗口算法）。
- **诊断**：per-gene 聚合表里同基因 Old/Young 中位数相同 = 窗口坍缩 bug；所有调用点都要传 gene_map。

## ⛔ 踩坑 2：bigWig NaN 传播

- **症状**：phyloP30 SNED1 chr2:240602097-240607097 窗口返回 NaN → `vals.mean()` 传播 → Mann-Whitney U 整组 p=NaN；`float('nan')` 不是 'NA' 字符串，`.get(key) not in ('NA', None, '')` 过滤漏掉。
- **修复**：打分函数 `np.isnan(vals).mean() > 0.2 → None`（缺口 <20% 用 `np.nanmean`）；CSV 统计前 `pd.to_numeric(errors='coerce') + dropna()`。

## 结果与解读

```
phyloP100: Old=0.044 vs Young=0.145  p=0.138 Cliff=-0.278 [-0.626, 0.088] Cohen d=-0.566
phyloP30:  Old=0.059 vs Young=0.111  p=0.094 Cliff=-0.313 [-0.652, 0.043] Cohen d=-0.599
phastCons: Old=0.088 vs Young=0.098  p=0.540 Cliff=-0.116 [-0.490, 0.260] Cohen d=-0.173
背景百分位: Old med=28% vs Young med=70%  p=0.138
phastCons 元件: Old 0/18 vs Young 0/22 (0/40)
```

- **方向**：Young DA CREs 序列保守性更高（负 Cliff d = Old 更低），与初版方向一致。
- **显著性**：三个轨道都不显著（p≥0.09），CI 跨 0，n=40 功效不足。
- **轨道梯度生物学解读**：phyloP30（灵长类）p=0.094 < phyloP100（哺乳全谱）p=0.138 < phastCons p=0.54 → 信号越近缘越强，可能是灵长类近期进化事件被哺乳全谱稀释。报告梯度本身是结果。
- **关键对照**：2026-08-09 人侧全量 strict DA（2955 Old + 563 Young）无差异（50.8% vs 51.2%）——同类小样本信号曾被大样本推翻。修复版只允许写"趋势/初步提示"。

## 结论措辞模板（专利/论文）

```
猴龄相关 DA CREs 在 Old vs Young 的序列保守性存在中等效应方向（Young 更高，Cohen's d≈-0.6），
灵长类谱系轨道（phyloP30）最敏感（p=0.094），但 n=40 功效不足未达显著性（CI 跨 0），
且 0/40 落入 phastCons 保守元件——结论定性为"初步趋势"，需正式版全量数据复现后升格。
```

## 平台注意：debate_analysis 参数过大 → 流式超时

- 本会话 debate_analysis 因 context + evidence_cards 合计过大（>~8K tokens）连续 3 次流式超时（system 消息明确提示）。
- 对策：辩论参数精简到极短 context + 单行证据卡重试；L2 完整辩论 judge 角色曾返回占位符失败，重试相同参数不一定成功——浓缩 context 后重试或降级 L1 轻量辩论。