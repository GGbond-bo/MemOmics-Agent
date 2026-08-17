# CNS Figure "三一结构" 模板与案例

## 什么是"三一结构"？

每张 Figure 必须包含三个强制要素：

1. **内容（What）**：具体的数据可视化结构和数据类型
2. **预期结果（Expected）**：带有具体数值和文献依据的预测
3. **备选方案（Fallback）**：如果结果走相反方向，怎么重新讲

缺少任意一个 → Figure 设计不完整，不可交付。

---

## 模板

```markdown
### Figure N: [验证预测X] [标题]

**内容**：
- a) [数据类型, 如 UMAP/UMAP 着色, n=cells]
- b) [统计图, 如 堆叠柱状图/boxplot/小提琴图]
- c) [机制图, 如 ATAC track / violon / 热图]
- d) [解读图, 如 模型/轨迹/网络]

**预期结果（带具体数值）**：
- 明确预期数值：如 "Type II 比例从 49% ± 3% 降至 29% ± 5% (p < 0.01, Cohen's d = 1.2)"
- 引用文献作为预期基线：[KB/PMID] 文献中报道的具体数值
- 效应方向：明确上调/下降/不变

**如预期不符合（备选方向解读）**：
- 如果结果相反 → 结论调整为："如果 T2D 中运动效果反而更强 → 说明 T2D 保留了肌肉可塑性"
- 如果无差异 → 备选解释："可能是统计功效不足，或生物学等效性"
- 如果反向 → "这提示 T2D 的分子机制与预期完全相反，需要重新考虑假说"

**论文对应**：
- 参考 [KB: 文献名] Figure X：类似的分析结构
- 本研究的维度扩展：[说明你比参考论文多了什么维度/数据]
```

---

## 真实案例：骨骼肌 衰老×T2D×运动

### Figure 1.1: 全局单核图谱与细胞组成重塑

**内容**：
- a) 全局 UMAP (~90,000 cells, 细胞类型着色)
- b) 6组堆叠比例图（Type I/IIa/IIx → FAP → EC → MuSC → Immune）
- c) MiloR 差异丰度热图（Young vs Old; Old vs Old+T2D）
- d) 各细胞亚群 pseudobulk DEG 计数 barplot

**预期结果**：
- 衰老使 Type II 肌核从 ~49% 降至 ~29%（Lexell 1988, J Neurol Sci; Kim 2023, Nat Commun）
- T2D 在衰老基础上进一步减少氧化型肌核(Type I/IIa)，增加 FAP 比例
- 去神经化肌核(MYOG+/CHRNG+)比例：Young(1-2%) < Old(5-8%) << Old+T2D(12-15%)

**如预期不符合**：
- 纤维比例差异不显著 → 改用 NMF 分解连续纤维状态(continuous fiber spectrum)而非离散分型
- FAP 比例不增加 → 说明 T2D 可能不通过纤维化途径损伤，需转向炎症通路
- 去神经化亚群不存在 → 降低 sub-clustering 分辨率，改用整体肌纤维差异分析

---

### Figure 3.3: MAF 调控网络的跨组学验证

**内容**：
- a) MAF motif 偏差评分(chromVAR) 6组 boxplot
- b) 关键位点 (MYH2/1 启动子, MAF 结合位点) 的 ATAC-tracks
- c) SCENIC GRN 网络图: MAF→MYH1/2/4, RUNX1→MYOG, MYOG→NCAM1
- d) Footprinting: MAF 结合位点占用情况

**预期结果**：
- 衰老+T2D 中 MAF motif 可及性显著低于 Young（FDR < 0.01, |log2FC| > 0.5）
- 运动后 Young 的 MAF 活性恢复，但 T2D 几乎不变 → "表观遗传锁死"证据
- 参考 [KB: Dos Santos 2025 Cell Rep]: MAF 过表达可逆转萎缩

**如预期不符合**：
- MAF 活性在所有组无差异 → 去神经化可能不通过 MAF 轴，需重新挖掘 (改为 FOXO/MEF2/MyoD)
- 运动后 T2D 的 MAF 活性也恢复 → 这是一个重要的正向发现：T2D 的表观可塑性比预期高 → 调整结论为"运动在疾病早期仍然有效"

---

## 常见错误

| 错误 | 坏例子 | 好例子 |
|------|--------|--------|
| 数值不具体 | "Type II 比例下降" | "Type II 从 49% 降至 29% (p<0.01)" |
| 无备选 | "如果不符合就调整参数" | "如果结果相反→说明T2D保留了肌肉可塑性" |
| 无文献引用 | "预期运动基因上调" | "PPARGC1A 预期上调 2-3 倍 [PMID:40413649]" |
| 备选是技术修复而非重新解读 | "如果不好看就换种图" | "如果无差异→重新考虑去神经化假说" |

## 与 Phase 框架的对应关系

```
Phase 1 (基线)  →  Figure 1.x (细胞组成图谱)
Phase 2 (响应)  →  Figure 2.x (差异分析+钝化)
Phase 3 (机制)  →  Figure 3.x (轨迹+GRN+ATAC) — 2-3张
Phase 4 (整合)  →  Figure 4.x (MOFA+概念模型)
Phase 5 (模型)  →  Figure 5 (单张概念图)
```
