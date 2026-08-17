---
name: atac-seq-memomics
description: "ArchR scATAC-seq 全流程: 环境搭建→Arrow文件→QC→降维→聚类→Peak calling→Motif→Footprinting→差异可及性→共可及性→导出"
when_to_use: "[atac-seq] ArchR scATAC-seq 全流程: 环境搭建→Arrow文件→QC→降维→聚类→Peak calling→Motif→Footprinting→差异可及性→共可及性→导出"
version: 2.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [atac-seq, archr, chromatin, peak-calling, scATAC, epigenomics, 05_表观组学]
    difficulty: advanced
    language: R
    category: scATAC
prerequisites:
  r_packages: ["ArchR", "Signac", "Seurat", "chromVAR", "motifmatchr", "ChIPseeker", "BSgenome.Hsapiens.UCSC.hg38"]
  python_packages: ["MACS2"]
  system_requirements: "R >=4.3, Java >=8, >=16GB RAM for >50K cells"
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。以下规则覆盖所有默认行为。

### 规则1: 拿到数据 → 必须调 search_knowledge
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 7步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. check_env 检查环境
3. rail_review(pre) 前置审查
4. source/import 预写脚本（禁止 inline 代码）
5. terminal 执行（分步执行，禁止 && 连接多步骤）
6. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
7. rail_review(post) 后置审查
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时（如 resolution, n_lsi_components, min_tss, q_value等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论
- 辩论格式：正方（支持当前参数）vs 反方（质疑+替代方案）→ 裁判决断
- 辩论最多 3 轮，选择最优结果

### 规则5: 执行后审查

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

  - **图片检查**：
    - 图有没有生成？没生成 → **强制重新执行**
    - 图片是否空白（全白/全黑/全单一色）？空白 → **强制重新出图**
    - 图片是否有 NA/缺失值（>10% 像素是 NA）？有 NA → **强制重新出图**
    - 图片大小是否过小（<5KB）？过小 → **强制重新出图**
    - 图片数量是否足够？（每步至少 1 张图，关键步骤至少 2-3 张）
  - **代码质量检查**：
    - 代码行数是否合理？（过短可能偷懒，过长可能未分段）
    - 代码是否有注释？
    - 代码是否分段执行（禁止 && 连接多步骤）？
  - **结果合理性**：
    - 数值范围是否合理？
    - 跟知识库对应吗？
  - **参数和结论辩论**：
    - 有参数的选择 → **必须调 debate_analysis 辩论**
    - 有结论输出 → **必须调 debate_analysis 辩论**
    - 不通过 → 修复重跑
    - 通过 → **必须调 skill_evolution(action="record_run")** 记录成功经验（skill_name/script_name/species/tissue/direction/params_used/result_summary/quality_score/notes） → 创建目录存储(figures/results/scripts/data) → 下一步
    - **不通过 → 修复后重跑 → 成功后调 skill_evolution(action="record_run")**；如果是脚本报错 → **调 skill_evolution(action="record_error")** 记录根因+修复方案

### 规则6: 结果存储结构
```
results/<模块>/<方法>/
  ├── scripts/     # 分析脚本
  ├── figures/     # PNG + PDF 图表
  ├── data/        # Arrow/RDS 中间数据
  └── results/     # CSV/TSV 结果表
```


### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）

| 时机 | action | 调 | 不调 |
|------|--------|----|------|
| 脚本报错+你分析根因+修复后 | record_error | ✅ R/Python 脚本报错，你找到根因并修复 | ❌ trivial 错误（打字错误、路径不存在） |
| 脚本成功+结果通过 rail_review | record_success | ✅ 分析步骤完成，图生成，审查通过 | ❌ 闲聊/方法咨询/非分析任务 |
| 修复后脚本验证稳定有效 | update_script | ✅ 同一错误修复了，重跑成功 | ❌ 只改参数没改脚本；未验证就更新 |

---

# ATAC-seq 分析 (ArchR) — Biomni 风格模块化

## When to Use

- scATAC-seq / snATAC-seq 数据分析
- 需要染色质可及性、peak calling、motif 分析
- 多模态整合（RNA + ATAC）的前置 ATAC 处理
- 物种: human / mouse | 组织: 任何 | 方向: 任何

## Pipeline (10 步)

### Step 1: 环境搭建
```r
source("scripts/setup_archr.R")
setup_archr(genome = "hg38")
```
- 检查 ArchR / MACS2 / BSgenome
- 设置基因组和线程

### Step 2: 创建 Arrow 文件 + ArchRProject
```r
source("scripts/create_archr_project.R")
ArrowFiles <- create_arrow_files(frag_files, sample_names, output_dir, min_frags=1000, min_tss=4)
proj <- create_archr_project(ArrowFiles, output_dir)
```

### Step 3: QC
```r
source("scripts/qc_atac.R")
plot_atac_qc(proj, output_dir)
proj <- filter_atac_cells(proj, min_tss=8, min_frip=0.15, max_blacklist=0.05)
proj <- remove_doublets_atac(proj, doublet_rate=0.08)
```
- 知识库参数: TSS>8, FRiP>0.15, blacklist<0.05, doublet_rate=0.08

### Step 4: 降维 (IterativeLSI)
```r
source("scripts/dimensionality_reduction.R")
proj <- run_iterative_lsi(proj, features=25000, n_components=30)
proj <- add_harmony(proj, batch_key="Sample")
proj <- add_umap_atac(proj, reduced_dims="Harmony")
```
- 辩论点: n_components 20 vs 30 vs 40

### Step 5: 聚类
```r
source("scripts/cluster_atac.R")
# 多分辨率比较
res_results <- compare_resolutions_atac(proj, resolutions=c(0.4, 0.6, 0.8, 1.0, 1.2))
# 辩论后选择最优
proj <- add_clusters_atac(proj, resolution=0.8, reduced_dims="Harmony")
```
- 知识库: 骨骼肌 resolution 0.8-1.2
- 辩论点: res=0.4(大类) vs 0.8(亚型) vs 1.2(精细)

### Step 6: Peak Calling (MACS2)
```r
source("scripts/peak_calling.R")
proj <- call_peaks(proj, group_by="Clusters", genome="hg38", q_value=0.05)
proj <- add_peak_matrix(proj)
```
- 知识库: qvalue=0.05, shift=-100, extsize=200

### Step 7: Gene Activity + Motif
```r
source("scripts/gene_activity.R")
proj <- add_gene_activity(proj)

source("scripts/motif_analysis.R")
proj <- add_motif_annotations(proj, motif_db="JASPAR2022")
proj <- run_chromvar(proj)
plot_motif_heatmap(proj, output_dir, top_n=20)
```
- 关键 TF (骨骼肌衰老): MAF, MYOD1, MYOG, RUNX1, FOXO, HSF1, YY1

### Step 8: TF Footprinting
```r
source("scripts/tf_footprinting.R")
proj <- add_footprinting(proj)
plot_footprint(proj, tf_names=c("MAF", "MYOD1", "FOXO1"), output_dir)
```

### Step 9: 差异可及性 + 共可及性
```r
source("scripts/diff_accessibility.R")
diff_peaks <- find_diff_peaks(proj, use_matrix="PeakMatrix", log2fc=0.5, fdr=0.05)
diff_motifs <- find_diff_motifs(proj)
peak_annot <- annotate_peaks(proj, genome="hg38")

source("scripts/co_accessibility.R")
proj <- add_co_accessibility(proj, max_dist=250000)
proj <- add_peak2gene(proj, cor_cutoff=0.45, fdr=0.01)
plot_peak2gene(proj, output_dir)
```

### Step 10: 导出结果
```r
source("scripts/export_results.R")
export_atac_results(proj, output_dir)
save_archr_project(proj, output_dir)
```

## Key Parameters (from knowledge base)

| Parameter | Default | KB Value | Source |
|-----------|---------|----------|--------|
| min_tss | 8 | >8 | ArchR default |
| min_frip | 0.15 | >0.15 | ArchR default |
| max_blacklist | 0.05 | <0.05 | ArchR default |
| doublet_rate | 0.08 | 0.08 | KB: muscle |
| n_lsi_components | 30 | 30 | KB: standard |
| resolution | 0.8 | 0.8-1.2 | KB: muscle |
| peak_qvalue | 0.05 | 0.05 | KB: MACS2 |
| max_dist_coaccess | 250000 | 250000 | ArchR default |
| peak2gene_cor | 0.45 | 0.45 | ArchR default |
| diff_log2fc | 0.5 | 0.5 | KB: consensus |
| diff_fdr | 0.05 | 0.05 | KB: consensus |

## Proven Scripts

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |


## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|


## References

- ArchR: https://www.archrproject.com/ (Granja et al., 2021, Nature Genetics)
- Signac: https://signac.readthedocs.io/ (Stuart et al., 2021, Nature Methods)
- MACS2: https://macs3-project.github.io/MACS/ (Zhang et al., 2008, Genome Biology)
- chromVAR: https://greenleaflab.github.io/chromVAR/ (Schep et al., 2017, Nature Methods)
- JASPAR: https://jaspar.genereg.net/ (Castro-Mondragon et al., 2022, NAR)
- ChIPseeker: https://github.com/YuLab-SMU/ChIPseeker (Yu et al., 2015, Bioinformatics)
- Muscle snATAC: Dos Santos et al., 2025, Cell Rep (PMID: 40632651)


## 🔒 审查机制（rail_review）

本 skill 执行代码前**必须**调用  进行前置审查，执行后**必须**调用  进行后置审查。

### 审查内容
- **pre 审查**：环境检查（包是否安装）→ 参数校验（参数是否合理）→ 代码审查（语法/逻辑）→ 硬件检查（内存/GPU是否够）
- **post 审查**：结果质量评估（输出是否合理）→ 图表检查（图是否生成）→ 数值检查（细胞数/基因数是否异常）→ 错误检查（有无 warning/error）

### 审查不通过
- pre 不通过 → **阻断执行**，修正后重新审查
- post 不通过 → **阻断下一步**，修正后重跑，直到通过
- 失败时调用  记录错误
- 修复成功后调用  +  替换脚本


---

## 🔒 审查与辩论机制（分析 skill 必须执行）

### 执行前审查 (rail_review pre)
使用此 skill 的分析步骤前，**必须**调用 ：
- 检查环境：R/Python 版本、必需包是否安装
- 检查参数：参数来源（知识库/文献/辩论/经验），不能凭空设值
- 检查数据：输入数据格式、细胞数、维度是否合理
- 不通过则阻断，修正后重试

### 执行后审查 (rail_review post)
分析步骤完成后，**必须**调用 ：
- 检查输出：文件是否生成、大小是否合理
- 检查质量：QC 指标、聚类质量、注释置信度
- 检查图表：是否生成了预期图表、图表是否合理
- 不通过则阻断，修正后重试
- **失败时**：调用  记录错误
- **修复成功后**：调用  +  替换脚本

### 多角色辩论 (debate_analysis)
当遇到**不确定的参数选择或结果判断**时，**必须**调用 ：
- 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
- 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
- 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
- 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
- 辩论结果自动归档到 results/.../log/debate_*.json

### 辩论触发场景
- 聚类分辨率选择（0.3 vs 0.5 vs 0.8 vs 1.2）
- QC 阈值设定（MT% 10% vs 15% vs 20%）
- 细胞类型注释争议（marker 不明显时）
- 归一化方法选择（SCT vs LogNormalize）
- 降维参数选择（PC 数量 10 vs 20 vs 30）
- 差异表达阈值（p<0.05 vs p<0.01, logFC 阈值）
- 任何需要多方审视的分析决策


---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="{当前分析} 参数与结果 —— {样本}",
     context="参数: {实际参数} | 结果: {输出摘要}",
     knowledge_base_info=<预查的 KB 内容>,
   )
   辩论维度：参数合理性、方法选择正确性、与KB生物学知识一致性、统计方法正确性
3. save_conclusions(module="{模块}", topic="{分析名}", debate_json=<debate返回JSON>, output_dir=<session results_dir>)
   → 写入 {module}/conclusions.md + conclusions.json
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。
⛔ debate confidence=low → 调整参数重跑。
