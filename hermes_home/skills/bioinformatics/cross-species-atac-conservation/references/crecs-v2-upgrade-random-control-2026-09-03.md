# CRECS v2.2 升级：真实 L3 Jaccard + 网格偏移随机对照 QA（2026-09-03）

## 背景

L3-B 跨物种 motif 富集（Top500 按 r 口径，用户拍板 B）产出真实跨物种 Jaccard
（`l3_topN_jaccard.csv` top30：up_up=0.213 / dn_dn=0.034）。任务 = 用真值替换
CRECS 旧固定代理值（`p4_crecs_scores.py` 硬编码 `jacc={'Old':0.020,'Young':0.070}`），
重算 A/B/C/D 分类。

## 步骤 1：v2.1 首跑 → 99.4% D 假象

```python
# p4_crecs_v2_1.py 要点（错误版）
# 分析对象 = human_ageDA_all 按 |r| top500 up + top500 down（B 口径，与 L3-B 对齐）
# L1 = v4/l1_full_human.csv 精确 start 匹配（容差 ±500/±1000/±2000）
# L2 = 人侧 0.5 + monkey_peaks_hg38_map 反查猴 DA 命中 0.5
# L3 = 真实 Jaccard × 5 归一
# 结果：A=3 / B=3 / C=0 / D=994（99.4% D），L1 命中仅 6/1000，猴命中 0/1000
```

症状：99.4% D + L1 命中 6/1000 + 猴命中 0/1000 → 几乎全在 D 类 = 退化分类。

## 步骤 2：随机对照诊断（决定性）

辩论裁判 missing 第 1 条点名"随机对照"：把 1000 tile 置换为随机基因组 tile，
若随机也 ≈99.4% D → 分类是覆盖方法产物而非生物学信号。

```python
# 随机对照脚本要点
# phyloP 表覆盖 524,256 tiles ≈ 8.5% 基因组 → 随机 tile 期望 ~85/1000 命中
# 实测：DA top1000 精确命中 6/1000；随机 1000 tile 精确命中 0/1000 ← 指数级不可能巧合！
# → 结论：phyloP v4 表与 ageDA 的 tile 网格根本不重叠
```

进一步诊断：
- `phylo_by_chr` 打印前 2000 行全是 chr1，start 范围 10,151–248,929,922 → bin=500bp
- 用 ±20kb 区间查询（bisect 最近 tile 的 p100_mean）后：
  - DA top1000 命中 **99.1%**
  - 随机 1000 tile 命中 **85.6%**
- → phyloP 覆盖本体完整（fill 脚本按 DA 区域扩展覆盖），**唯一问题是两表 500bp bin 网格存在 ~57bp 非 500 倍数偏移**，精确匹配与 500 倍数容差全部落空。

**根因**：phyloP v4 表与 ageDA 的 bin 起点错位（约 57bp），`start+500` 之类的容差永远对不上（差 57 而不差 500 的倍数）。

## 步骤 3：v2.2 修复（区间查询）

```python
# p4_crecs_v2_2.py 关键修复
def nearest_phylo(chrom, start):
    cands = phylo_by_chr.get(chrom, [])   # chr → sorted[(start,end,p100)]
    if not cands: return None
    starts = [x[0] for x in cands]
    i = bisect.bisect_left(starts, start)
    best, best_d = None, 20000            # ±20kb 窗口
    for j in (i-1, i):
        if 0 <= j < len(cands):
            d = abs(cands[j][0] - start)
            if d < best_d: best_d, best = d, cands[j][2]
    return best if best_d < 20000 else None
# L2 猴侧同理：hg38_to_monkey 映射表按 (hg38_chr, hg38_start±off) 查找，off 含 500/1000/2000/5000/15000
```

**v2.2 权威结果（1000 tiles = top500 up + top500 down）**：

| 类别 | tile 数 | 占比 | 含义 |
|---|---|---|---|
| A | 182 | 18.2% | 三层全保守 |
| B | 364 | 36.4% | 序列保守但 TF 结合分歧（专利核心） |
| C | 0 | 0% | 阈值下无落点 |
| D | 454 | 45.4% | 序列不保守 |

- L1>0 = 546/1000；猴 DA 命中 = 0/1000（同源增强子活性分歧，方向自洽）
- 评分：CRECS = 0.4*L1 + 0.3*L2 + 0.3*L3；分类 A=CRECS≥0.8 / B=L1=1 & L2≥0.5 & L3<0.5 / D=L1=0 / 其余 C

产物：`p4_crecs_v2_scores.csv` + `p4_crecs_v2_class_heatmap.png`（分类×方向矩阵 + 三层分数箱线）。

## 辩论裁决（L1，need_more_info/low）

- 裁判认可修复有效性（rubrics 从 v2.1 的 4/3/3 升到 5/5/4；随机对照 6/1000→99.1% 即证据）
- 但仍列 missing：① L3<0.5 阈值与 ×5 缩放因子为人为设定 ② C=0 缺中间态分类 ③ 缺 ChIP/footprint 外部验证 ④ 无随机对照的保守性基线（同 shuffle）
- **专利措辞铁律**：B 类 364 tiles 可写入实施例作为"候选区清单"，只能写"候选/提示/方法学框架"，**禁止写"已证实 TF 结合分歧"**。

## 通用教训（跨表 tile 坐标 join）

1. **不同管线产出的 500bp tile 表不能假设网格对齐**（phyloP/ageDA/motif 表可能有几十 bp 的 bin 起点偏移）
2. 分类结果出现"某类 >95% 单极大"→ 先跑随机对照（同数量随机位置套同一评分管线），随机也退化 = 覆盖/对齐问题，不是信号
3. 精确 start 匹配前先做随机对照或抽样核对命中率；稳妥做法直接用 ±20kb 区间查询（bisect 最近 tile），不要依赖"容差 500 的倍数"
4. 修复后必须重跑随机对照确认命中率恢复（6/1000 → 99.1%）才算闭环