---
name: academic-research
description: "综合学术研究技能：实验方案设计、文献检索、研究规划"
when_to_use: "[academic-research] 综合学术研究技能：实验方案设计、文献检索、研究规划"
version: 1.1.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [research, experiment, design, 实验设计, 方案, 研究设计]
    difficulty: advanced
    language: Python
    category: Literature
prerequisites:
  r_packages: []
  python_packages: []
### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

---

# 学术研究设计

综合学术研究技能：实验方案设计、文献检索、研究规划

适用场景: 实验方案设计, 研究规划, 文献综述

难度: advanced

触发提示: "帮我设计实验方案"

别名: 实验方案, 研究设计, experiment design, 研究方案

## When to Use

适用于: 实验方案设计, 研究规划, 文献综述

## 执行模板 — CNS 级研究方案生成

当用户请求生成研究方案时，必须按以下 10 段模板输出。**禁止省略任何一个段落。**

```
## 研究方案: {species} {tissue} {direction}

### 1. 核心假说 (Core Hypothesis)
- **生物学问题**: 用 1-2 句话描述要回答的生物学问题
- **已发表工作缺口 (Gap)**: 对比 [KB] 中的文献，说明现有知识缺少什么
- **零假说 (H₀)**: 无效应/无差异的陈述
- **备择假说 (H₁)**: 本研究要验证的主张
- **预测链**: 如果 H₁ 成立 → 预期观察 A → 预期观察 B → 预期观察 C
  - 预测 A: {用数据X的方法Y检验}
  - 预测 B: ...
  - 预测 C: ...

### 2. 创新性声明 (Novelty Statement)
- **本研究 vs 已发表工作**: 与 [KB: 论文名] 相比，本研究的独特之处在于:
  - (1) 新数据/新物种/新组织
  - (2) 新方法/新组合
  - (3) 新假说/新角度
- **潜在领域贡献**: 如果假说成立，将改变 __ 的认知

### 3. 文献依据 (Literature Foundation)
| 文献(作者+年份,PMID/DOI) | 关键方法 | 与本方案关系 | 来源 |
|--------------------------|----------|-------------|------|
| ... | Seurat v4.0.2, SCTransform | 方法参考+可复现性 | [KB] |
| ... | ... | ... | [PMID:xxx] |

### 4. 分析方法与论证 (Methods & Rationale)
每个方法必须回答: **为什么选这个方法？它验证假说的哪一部分？**
1. **数据预处理**: [KB] Seurat v4.0.2 → SCTransform
   - 理由: SCTransform 优于 LogNormalize 因为 [具体理由，如 UMI count 异方差性]
   - 验证: 预测 A (细胞类型鉴定)
2. **批次校正**: [KB] Harmony v1.0
   - 理由: 优于 Seurat CCA 因为 [datasets 大小不均/跨物种]
   - 验证: 预测 A (确保 cell type 而非 batch 驱动聚类)
3. ...
每个方法的理由必须有实质性内容，不能只说"常用"/"标准"

### 5. 统计方案 (Statistical Plan)

> **针对多因素干预研究**（如衰老×疾病×运动），统计设计须特别注意：
> - **交互效应检验**：DESeq2/limma 公式 `~ group + time + group:time`，检验 FDR < 0.05 的交互 DEGs
> - **两轮策略**：第一轮做组内配对对比（pre vs post），第二轮比较效应量的组间差异（meta-analytic thinking）
> - **小型样本**（每组 n≤3）：降维为"一阶效应对比 + 效应量比较"而非 full factorial；使用 MCMC 建模
> - **协变量控制**：将额外临床指标（BMI, HbA1c, VO2max）纳入线性模型

- **统计功效**: 基于预期效应量 ___ (Cohen's d/log2FC)，显著性 α=0.05，需≥___ 样本
- **多重检验校正**: BH (FDR < 0.05) 或 Bonferroni (当检验数<10时)
- **效应量度量**: log2FC ≥ 0.5（scRNA-seq）/ ≥ 1.0（bulk RNA-seq）, Cohen's d ≥ 0.8
- **阴性对照**: (如: shuffled labels, permuted genotypes, shuffled cell type labels)
- **阳性对照**: (如: 已知衰老标记基因 SenMayo/CellAge, 已知运动应答基因 PPARGC1A/ESRRG)
- **批次效应评估**: kBET, LISI score

### 6. Figure 策略 (Figure Strategy)

> **多因素干预研究特别指导**：参考 `references/multi-factor-study-design.md` 的 Phase 1-4 框架
> - Phase 1 → Figure 1（基线图谱）
> - Phase 2 → Figure 2（干预效果）
> - Phase 3 → Figure 3（机制深挖）
> - Phase 4 → Figure 4+（整合与模型）
> - 每个 Phase 的 Figure 结构见参考文件中的具体模板

**每张Figure对应假说的一个预测，必须写明预期结果:**
- **Figure 1**: [验证预测A] {标题}
  - 内容: UMAP/标记基因表达
  - 预期结果: 明确cluster分离，已知marker在对应cluster高表达
  - 如预期不符合: [备选] 调整分辨率，手动注释
- **Figure 2**: [验证预测B] {标题}
  - 内容: 差异表达 + 通路富集
  - 预期结果: DEGs富集于衰老通路，SenMayo基因集上调
  - 如预期不符合: [备选] GSEA替代ORA，降低FDR阈值
- **Figure 3**: [验证预测C] {标题}
  - 内容: ...
参见 `references/cns-figure-trinity.md` 获取详细模板和真实案例。

## ⚠️ 知识库引用规则
- **正交验证**: (如 IF 染色验证蛋白水平、RNA-FISH 验证空间定位、qPCR 验证关键基因)
- **公共数据验证**: (如 Tabula Muris Senis, GTEx, Human Cell Atlas)
- **阳性对照基因集**: SenMayo / CellAge / GO:0007568 (aging)
- **如果全部预测被证伪**: 报告 negative result，讨论原因（统计功效不足？假说错误？）

### 8. 备选方案与风险 (Contingency Plan)
| 风险 | 可能性 (高/中/低) | 缓解策略 |
|------|-------------------|----------|
| 细胞数/基因数不足 (QC过滤过严) | 中 | 降低 MT%阈值，用 EmptyDrops 替代 |
| 批次效应无法消除 | 低 | 切换 Seurat CCA+RPCA，分析每个 batch 单独验证 |
| 假说被完全证伪 | 低 | 转向 explorative analysis，报告 negative result |
| [KB] 方法不适合本研究 | 中 | 回退到 [PMID:xxx] 中的备选方法 |

### 9. 可复现性声明 (Reproducibility)
- **代码**: GitHub/Figshare (提交时附URL)
- **数据**: GEO accession / EGA / dbGaP (如有)
- **环境**: Docker/Singularity 容器 + conda env yaml → 提供 container URL
- **随机种子**: set.seed(42) / random_state=42

### 10. 可执行待办
调用 memomics_pipeline(action='todos', selected_modules=[...])

### 11. 交付格式
用户要求"生成完整方案"时，必须以 **可编辑文档（DOCX优先）** 交付，同时生成 PDF。
- 使用 python-docx 生成 Word 文档，路径: `results/research_proposal/{species}_{tissue}_{direction}_CNS方案_v{version}.docx`
- 使用 reportlab 生成 PDF 附件
- 脚本保留在 `results/research_proposal/generate_proposal.py`，可复现修改

## ⚠️ 用户偏好嵌入（2026-07-13 会话）

当用户（尤其是骨骼肌衰老方向）要求CNS级方案时，已纠正过的问题：
| 用户投诉 | 根因 | 必须做到 |
|---------|------|---------|
| "太泛了，深度不够" | 只有方法列表，无论文级phased结构 | Phase 1-5分层 + Figure三一结构 |
| "不分阶段" | 一次性讲所有内容 | 每Phase只答一个生物学问题 |
| "看看人家文章怎么探究的" | 缺论文技术对照表 | 必须有：参考论文 vs 本研究 Figure/方法对应表 |
| "太泛"（再次） | 预测无具体数值 | 必须写"Type II从49%→29%"这类精确数值+文献依据 |
| 无可执行性 | 只讲"做什么"不讲"顺序" | Phase级待办清单 + skill绑定 |
```

## ⚠️ 知识库引用规则（Iron Law #7）

1. **必须**调 `search_knowledge(species, tissue, direction)` 加载本地KB论文
2. KB中的论文推荐**优先级最高**：版本号 → KB版本，方法链 → KB已验证流程
3. KB来源标注 **[KB]**，PubMed来源标注 **[PMID:xxx]**
4. 方案中推荐的工具如果与KB冲突 → 优先KB中的版本号
5. 如果KB中某篇论文的方法链与用户研究高度相关 → 在方案中引用并说明"可复现性"

## Loop Gate — CNS 方案质量检查

交付前必须通过以下 **11 项**检查。**任一项缺失 = 方案不可交付。**

- [ ] ① 核心假说: H₀/H₁ 是否明确？是否有 ≥3 条预测链，每条对应具体检验方法？
- [ ] ② 创新性: 是否与 [KB] 文献做了明确对比？是否写明本研究填什么 gap？
- [ ] ③ 方法论证: 每个分析方法是否附 ≥1 句实质理由（禁止"常用"/"标准"/"参考已有研究"等空话）？
- [ ] ④ 统计方案: 是否包含功效分析 + 多重检验校正 + 效应量阈值 + 阴阳对照？
- [ ] ⑤ 多因素设计检查: 如果是 ≥2 条件 × 干预设计，是否包含交互效应检验 + 分阶段策略（Phase 1-4 框架）？
- [ ] ⑥ Figure 策略: 是否 ≥3 张 Figure，每张对应一条预测 + 写明预期结果 + 备选方案 + 与已发表论文的"技术对应表"？
- [ ] ⑦ 实验验证: 是否包含 ≥1 种正交验证方法 (IF/qPCR/RNA-FISH) + ≥1 个公共数据验证？
- [ ] ⑧ 备选方案: 是否列出 ≥3 个风险 + 对应的缓解策略 + 决策分支？
- [ ] ⑨ KB 注入: search_knowledge 是否已调用？≥2 个方法来自 [KB] 论文？来源标注是否完整？
- [ ] ⑩ 论文结构学习: 是否引用了 ≥1 篇已发表论文的分析阶段/Figure 结构作为参考（如 Lai 2024 Nature 的 Phase→Figure 对应）？是否包含"论文三一结构"（内容-预期数值-备选解读）？
- [ ] ⑪ 可复现: 是否声明代码/数据/环境/随机种子？
- [ ] ⑫ 交付形式: 用户要求"生成方案"时是否包含 DOCX/PDF 可编辑交付件？

**11/11 ✅ → 交付。有任何 ❌ → 补充后重新走 Loop Gate。**
**连续 2 次不通过 → 报告用户"方案复杂度超出自动生成能力，建议人工审核"。**

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| *(accumulated from runs)* | | |

## References

- `references/multi-factor-study-design.md` — 多因素干预研究的四阶段深度分析策略（Phase 1-4 框架 + Figure 结构 + 论文学习）
- Source: MemOmics built-in
- Category: literature
- Language: Python


---

## 🗣️ 辩论机制（debate_analysis）

本 skill 在执行后，如果涉及**参数选择、方法决策、结果判断**等不确定环节，**必须**调用  工具进行多角色辩论。

### 辩论规则
- **正方 3 位专业编辑**（各自独立，互相看不到）：生物学编辑 / 统计学编辑 / 生信编辑
- **反方 4 位专业编辑**（各自独立，互相看不到，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- **裁判**：看到所有 7 方论点后给出裁决 + 置信度（高/中/低）
- **上下文隔离**：每个编辑是独立的 LLM API 调用，messages 只包含自己的 prompt
- **分科知识库**：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
- **辩论结果自动归档**到 results/.../log/debate_*.json

### 触发场景
- 参数选择有多个合理选项时（如分辨率 0.4 vs 0.6 vs 0.8）
- 结果可能受方法选择影响时（如不同注释方法给出不同结果）
- 生物结论需要验证可靠性时
- QC 阈值不确定时（如 MT% 阈值 10% vs 15% vs 20%）

### 不触发场景
- 参数有明确知识库推荐且无争议时
- 纯计算步骤（如保存文件、读取数据）
