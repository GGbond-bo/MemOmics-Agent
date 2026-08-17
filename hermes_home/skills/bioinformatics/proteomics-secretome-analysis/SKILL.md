---
name: proteomics-secretome-analysis
description: >
  分泌蛋白组/条件培养基蛋白质组学全流程分析。
  从 LC-MS/MS Excel 报告出发，完成：数据加载→技术重复QC→UniProt蛋白分类(游离/EV/背景)→
  抗衰老/功能证据链分级→GO/KEGG富集→STRING PPI网络→综合HTML报告。
  适用场景：conditioned medium secretome, supernatant proteomics,
  total conditioned medium proteome, 上清蛋白组, 分泌组。
triggers:
  - keyword: ["分泌蛋白组", "secretome", "条件培养基", "上清蛋白", "conditioned medium",
              "supernatant proteomics", "LC-MS/MS上清", "蛋白存在形式"]
  - domain: 05_蛋白
when_to_use: >
  用户提供 LC-MS/MS 蛋白质组学 Excel 报告（含蛋白ID、丰度列），需要按存在形式分类蛋白、
  筛选功能候选、建立衰老/功能证据链时触发。
metadata:
  hermes:
    category: Proteomics
---

# Proteomics Secretome Analysis — 分泌蛋白组全流程

## ⚠️ 铁律：技术重复 ≠ 生物条件

**最常见的致命错误**：数据中有两列数值（如 test1/test2），默认当作两组独立条件跑差异分析。

```
判定规则：
  用户说"两个重复"/"technical replicates"/"n=2 replicates" → 取均值排名，禁差异分析
  用户说"test vs control"/"young vs old"/两组不同处理 → 才可以做差异分析
```

**不确定时主动问用户**："test1 和 test2 是两个技术重复还是两组不同条件？"

## 分析流程（7 步）

### Step 1: 数据加载与重复性评估

```python
# 加载 Excel，保留双列均有值的蛋白
df = pd.read_excel(xls_path)
df = df[df['test1'].notna() & df['test2'].notna()].copy()

# Log2 变换 + 均值 + CV
df['log2_test1'] = np.log2(df['test1'])
df['log2_test2'] = np.log2(df['test2'])
df['mean_abundance'] = (df['test1'] + df['test2']) / 2
df['CV'] = np.abs(df['test1'] - df['test2']) / (df['mean_abundance'] * np.sqrt(2))
df['abundance_rank'] = df['mean_abundance'].rank(ascending=False).astype(int)

# Spearman 相关性
r, p = stats.spearmanr(df['log2_test1'], df['log2_test2'])
# 报告: Spearman r, CV 中位数, CV>0.3 占比
```

### Step 2: UniProt 查询 + 蛋白分类

对每个蛋白查询 UniProt REST API (`https://rest.uniprot.org/uniprotkb/search`)：
- `fields=accession,gene_names,ft_signal,cc_subcellular_location`
- 速率限制 0.2s/请求

分类逻辑（详见 `references/classification-logic.md`）：

| 分类 | 条件 | 验证策略 |
|------|------|----------|
| **Class I: Free Soluble** | signal peptide + extracellular + not EV | ELISA + 重组蛋白 add-back |
| **Class II: Dual (Free+EV)** | signal peptide + EV 数据库双证据 | EV 分离后分别定量 |
| **Class III: EV/Exosome Cargo** | cytoplasmic/mitochondrial + no signal peptide + EV detected | EV add-back + cargo 阻断 |
| **Class IV: Background** | Keratins/Histones/Ribosomal/ALB/INS/TF | 排除 |

归类后显式校正：KRT 基因 → Class IV，Histone → Class IV，RPS/RPL → Class IV。

### Step 3: 抗衰老/功能蛋白筛选（三级证据体系）

详见 `references/anti-aging-evidence-tiers.md`。

**Tier 1 (强证据)**: UniProt 官方"aging"注释 + KB 衰老基因集 + ≥2篇 PubMed
**Tier 2 (良好证据)**: KB 衰老基因集确认 + 已知衰老通路（抗氧化/分子伴侣/自噬）
**Tier 3 (潜在)**: ECM/代谢/补体等间接关联

证据来源：
- UniProt 官方注释（如 CLU = "Aging-associated gene 4 protein"）
- MemOmics KB (liver_aging_up/down 基因集)
- PubMed 文献交叉验证
- ExoCarta/Vesiclepedia EV 定位

### Step 4: GO + KEGG 富集（R: clusterProfiler）

```r
gene_ids <- bitr(genes, fromType="SYMBOL", toType="ENTREZID", OrgDb="org.Hs.eg.db")
ego_bp <- enrichGO(gene_ids$ENTREZID, OrgDb="org.Hs.eg.db", ont="BP", ...)
ego_cc <- enrichGO(...)  # blood microparticle 是分泌蛋白组标志性信号
ekegg <- enrichKEGG(gene_ids$ENTREZID, organism="hsa", ...)
```

重点关注的衰老相关 terms：
- KEGG: Longevity regulating pathway (hsa04213), Cellular senescence (hsa04218)
- GO BP: protein refolding, protein stabilization, response to oxidative stress

### Step 5: STRING PPI 网络

```python
STRING_API = "https://string-db.org/api/json"
# network endpoint → edges (score ≥ 400)
# annotation endpoint → node annotations
# MCODE 模块检测 → 功能模块识别
```

### Step 6: 综合可视化

- 饼图：四类蛋白分布
- 柱状图：Top 40 丰度排名（按分类着色）
- 抗衰老候选蛋白：bar chart（按 Tier 分级着色）
- GO/KEGG dotplot

### Step 7: HTML 报告

使用 `bioinformatics-html-report` skill 生成综合报告。推荐结构：
1. 项目概览（统计数字卡片）
2. 数据质量（Spearman r + CV 分布）
3. 蛋白分类（四类表格 + 饼图）
4. **衰老证据链（核心章节）**：Tier 1/2/3 表格 + 功能网络 + 关键轴线
5. 功能富集（GO CC/BP + KEGG）
6. PPI 网络（模块表）
7. 验证策略（PPT 框架对照 + 实验路径）
8. 附录：全部脚本（可折叠）

深色主题（GitHub-dark 风格），sticky 导航，统计卡片，折叠脚本块。

## 关键输出文件

```
results/{session_dir}/
├── data/
│   ├── protein_abundance_corrected.csv    # 丰度 + CV + 排名
│   ├── protein_classification.csv         # 分类结果
│   ├── anti_aging_proteins.csv            # 抗衰老候选
│   └── ppi_*.csv                          # PPI 网络数据
├── results/
│   ├── GO_BP/CC/MF_CORRECTED.csv          # GO 富集
│   └── KEGG_CORRECTED.csv                 # KEGG 富集
├── figures/
│   ├── Fig1_pie_CORRECTED.png             # 分类饼图
│   ├── Fig2_replicate_correlation.png     # 重复性散点图
│   ├── Fig4_top40_abundance.png           # 丰度排名
│   └── Fig6_anti_aging_candidates.png     # 抗衰老候选
└── *_Complete_Report.html                 # 综合报告
```

## 陷阱

1. **test1/test2 是重复还是条件？** — 未确认前禁止差异分析
2. **角蛋白污染** — KRT 家族在上清中常见，不一定是角质化分化产物
3. **ALB/INS/TF 高丰度** — 通常是培养基添加，归为 Class IV
4. **CV > 0.3 的蛋白** — 报告中必须标注，丰度估计不可靠
5. **UniProt API 速率限制** — 必须加 0.2s delay，否则 IP 被封

## 参考文献

- 本 skill 创建于 hES-4CL-EB 上清分泌蛋白组分析
- 抗衰老证据体系参考 `references/anti-aging-evidence-tiers.md`
- 分类逻辑细节参考 `references/classification-logic.md`
---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="蛋白组学分析 —— {样本}",
     context="方法: {limma/DEP/MSstats} | 参数: FDR<{x} | 结果: {n}差异蛋白",
     knowledge_base_info=<KB内容>,
   )
   辩论: 方法选对了吗？阈值合理？差异蛋白跟RNA一致吗？富集通路合理？
3. save_conclusions(module="03_advanced", topic="Proteomics", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```
