---
name: overlapping-gene-read-assignment
description: >-
  重叠基因（反义 lncRNA / head-to-head / 嵌套）的 read 归属判定：用 GTF 把「gene span 重叠」与「exon 级重叠」拆开量化，
  叠加链方向规则与自身定量结果的交叉一致性反证，回答「UMI 会不会把两个基因混在一起」，并产出位点图与可直发的英文答复。
  触发：反义 / 重叠基因 / 能不能区分 / read 归到哪个基因 / overlapping gene / antisense lncRNA / head-to-head / 查 GTF 坐标 / 这个基因是不是被另一个污染。
when_to_use: >-
  合作者或审稿人质疑「两个基因坐标重叠 → 你的 counts 分不开」，或你自己要判断某个反义/重叠基因（MEF2C-AS1、XIST 类、
  读穿转录本）的定量与 DEG 结论是否可信时。只做 DEG 流程 → skill `deg-analysis`；只做位点/热图版式 → skill `matrix-heatmap-geometry`。
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [annotation, gtf, antisense, lncRNA, UMI, read-assignment, GENCODE, scRNA]
    difficulty: intermediate
    language: Python
    category: bioinformatics
---

# 重叠基因的 read 归属判定

合作者看到两个基因的 `start-end` 区间相交就会问「**overlapping region 里你怎么区分 A 和 B**」。
这是一个**可以当场用 GTF 关掉**的质疑 —— 因为 UMI 计数根本不看 gene span。

## 何时用

- 合作者/审稿人/自己问：「reads 映射到哪？落在重叠区怎么区分 A vs B？」
- 反义 lncRNA（`gene_type "lncRNA"`，与正义基因反向）的定量结果被质疑受污染
- 需要判断某个 DEG 结论是否可能是 read 归属串扰产生的假信号
- 要给合作者/审稿人的回信里提供**坐标级**证据

## Step 0：先分清对方在问什么（这条排在技术之前）

| 用户的问法 | 你要做的 | 禁止 |
|---|---|---|
| 「**他这句话是什么意思？**」 | 逐句解读 + 把其中涉及的生物学/方法学事实核实后解释 | ❌ 顺势开跑图 / 量化 / 辩论 / 改图长链 |
| 「我们要给他展示 GTF 还是去做 ATAC？」 | 直接给判断：GTF 够 / ATAC 答不了这个问题 | ❌ 两个都做一遍 |
| 「帮我把这条整理成回他的英文」 | 出可直接发送的英文稿，数字全部已核实 | ❌ 只复述不产出 |

**2026-10-01 实测教训**：用户问「合作方说的是什么意思」，我转去把另一张图做了十几轮（补丁→重跑→像素审计→辩论→量化），
被直接打断「关桑基图什么事情？」。**解读类问题 = 只解读 + 核实事实，交付完再问下一步。**

术语对齐：对方说的 "overlapping region" 几乎总是指 **gene span 重叠**（GTF 里两行 `start/end` 相交），
而这**不是** UMI 计数看到的重叠 —— 抓住这个错位，问题就解决了一半。

## Step 1：量化重叠 —— span 级 vs exon 级（决定性一步）

**UMI 流程只在外显子上计数**（内含子/基因间不产生计数）。所以要把重叠拆成两层：

```python
span_overlap  = intersect(merged_span(A), merged_span(B))          # 基因跨度相交（对方看到的那段）
exon_overlap  = intersect(merged_exons(A), merged_exons(B))        # 真正能被计数的重叠
pct = sum(exon_overlap) / sum(span_overlap) * 100
```

可直接复跑（读 GENCODE 风格 GTF，输出上面三行 + 每基因 span/合并外显子）：

```bash
python scripts/overlap_decomposition.py gencode.v32.primary_assembly.annotation.gtf.gz MEF2C MEF2C-AS1
```

**实测（MEF2C / MEF2C-AS1，GENCODE v32，GRCh38）**：span 重叠 **20,930 bp** →
exon 级只剩 **422 bp / 3 小段**（**2.02%**），其余 20,508 bp 全在内含子/基因间。
**这一段数字就是回信的核心。**

## Step 2：链方向（辅助论据，不要当唯一论据）

- 两基因**反向**（head-to-head，5′ 端相向）时，反义读段在链特异性建库下不属于正义基因。
- ⚠️ **不要把「10x 是链特异性的」当唯一论据**：追问下去会落到具体版本 Cell Ranger 对 ambiguous UMI 的处理规则，
  需要查官方文档实证（用户规矩：函数/工具行为必须看原文，禁止凭记忆描述）。
- **优先用不依赖任何建库假设的两条**：Step 1 的 exon 级重叠 + Step 3 的数据反证。

## Step 3：最强证据 —— 自身数据的交叉一致性反证（常被忽略）

不需要额外测任何数据。**如果两个基因的 read 真的混在一起，它们的 counts 会被同一批 UMI 共同拉高 →
DEG 结果应当同向同幅度。**

```python
# 在自己已有的 DEG 表里直接搜两个基因（一轮只读查询，秒级）
hit = df[df[gene_col].str.upper().isin(["MEF2C", "MEF2C-AS1"])][["gene","celltype","coef","fdr","direction"]]
```

**实测（同一张 DEG 表）**：MEF2C-AS1 在多个亚群/对比中**显著上调**（coef 0.27–0.72，FDR 从 1.9e-38 到 ~0），
而 MEF2C 全部未过阈（|coef| < 0.25、FDR 不显著）。
→ **一个显著、一个纹丝不动 = 反证计数流程把两者干净分开**。这是最能让合作者闭嘴的一条，因为它用的是**他的数据**。

⚠️ 前提：两个基因都要在**同一张表**里可查；若被过滤阈值剔掉了，去未过滤的原始表或 raw counts 里查（别用过滤后表缺席当"没表达"的证据）。

## Step 4：交付物

1. **位点图**（GTF 解析，不需要 FASTA）：两基因模型 + 链箭头 + 重叠区高亮 + 坐标轴（`44_MEF2C_locus_from_GTF.*`）
2. **重叠拆解图/表**：span 20,930 bp vs exon 422 bp 的条形或分层展示（`44b_MEF2C_AS1_overlap_decomposition.*` + `44b_overlap_decomposition.csv`）
3. **英文回信**：三段式 —— ①重叠在哪（坐标+链+head-to-head，3′ 端相距多远）②为什么不混（exon 只 2% + 链反向）③数据反证（两基因结果不同）+ 附图
   → 骨架与已核数字见 `references/mef2c-mef2c-as1-case.md`

**不要为了回答这个问题去跑 ATAC。** ATAC 测染色质可及性（哪个调控区开放），**不产生 read→基因的归属信息**，
答不了「你怎么区分 A 和 B」。ATAC 是**另一个问题**（该位点运动后是否变开放、两基因是否共享调控区），可作加分项，不是必需项。
若用户问「要不要去 ATAC 看」→ 明确回答「这个问题 GTF 就够，ATAC 答不了」。

## 坑表

| 现象 | 根因 | 处置 |
|---|---|---|
| 合作者说「重叠区分不开」 | 他量的是 **gene span** 重叠（含大量内含子） | 拆到 exon 级量化（Step 1）；实测 2.02% |
| 只答「建库是链特异性的」被继续追问 | 建库假设要落到具体版本 Cell Ranger 的 ambiguous 规则 | 改用 Step 1 + Step 3 两条不依赖假设的论据；要用链论据先查官方文档 |
| 想去跑 ATAC 来「证明能区分」 | ATAC 无 read→基因归属信息 | 明确否掉，说明 ATAC 回答的是另一个问题 |
| 用过滤后的 DEG 表查不到某基因 → 判定「没表达」 | 过滤阈值（FDR/coef）把低表达或非显著基因剔除了 | 去未过滤表 / raw counts 查；过滤后缺席 ≠ 未检出 |
| 用户问「他什么意思」而你开始跑分析 | 把解读请求当执行请求 | Step 0：只解读 + 核实事实，禁止开长链 |
| 结论里只有「我们能区分」没有数字 | 合作者要的是坐标与百分比 | 回信必带：span bp / exon bp / 段数 / 百分比 / 坐标区间 |

## 配套文件

- `scripts/overlap_decomposition.py` — 可直接复跑：读 GTF(GZ) 输出两基因 span、合并外显子块与 bp、span 重叠、exon 级重叠段与占比（纯标准库）
- `references/mef2c-mef2c-as1-case.md` — MEF2C / MEF2C-AS1 全案实测数字（坐标、20,930/422 bp、链方向与 3′ 距离）、合作方质疑的完整对话脉络、可直发的英文回信骨架

## 交叉参考

- 反义/重叠基因的 DEG 结论如何写进报告与阈值口径 → skill `deg-analysis`
- 位点图/矩阵热图的版式与对齐核验 → skill `matrix-heatmap-geometry`
- 引用文献前先核验 PMID/DOI → skill `bioinformatics-fact-retrieval`