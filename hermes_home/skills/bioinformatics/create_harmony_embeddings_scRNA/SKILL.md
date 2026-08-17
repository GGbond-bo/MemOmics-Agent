---
name: create_harmony_embeddings_scRNA
description: "Harmony批次校正整合。使用场景：多样本scRNA-seq需去批次效应，快速高效，适合中等数据量（<100万细胞），R/Seurat生态"
when_to_use: "[create_harmony_embeddings_scRNA] Harmony批次校正整合。使用场景：多样本scRNA-seq需去批次效应，快速高效，适合中等数据量（<100万细胞），R/Seurat生态"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: []
    difficulty: basic
    language: Python
    category: scRNA
prerequisites:
  r_packages: []
  python_packages: []
---


## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。使用本 skill 前，必须先通过 skill_view 加载本文件。以下规则覆盖所有默认行为。

### 规则1: 写代码前 → 必须先 search_knowledge + skill_view
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则1a: batch_key 预检查（写代码前必须执行）
- **使用 `batch_key` 前**，必须先用 Python 检查唯一条目数：
  ```python
  n_unique = adata.obs['<batch_key>'].nunique()
  print(f"batch_key 唯一条目数: {n_unique}")
  if n_unique > 100:
      print("⚠️ 警告：batch_key 有 {n_unique} 个唯一值，可能误用了 cells/barcode 列！")
      print("  预期：sample/donor ID（通常 2-20 个）")
      print("  如果不是 → 阻断，检查数据，修正 batch_key")
  ```
- 如果 `n_unique > 100` 且不是预期的样本数 → **阻断执行**，提示用户在 `adata.obs.columns` 中找正确的分组列
- 参考 Common Issues → 已有 `sample_id (16,003 unique)` 先例

### 规则2: 8步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. skill_view 加载本 SKILL.md（获取脚本模板+审查规则+参数范围）
3. check_env 检查环境（缺包自动安装）
4. rail_review(pre) 前置审查（参数合理吗？包齐了吗？数据准备好了吗？）
5. 写这一步的代码（基于 skill 模板，只写这一步，不写后续步骤）
6. terminal 执行（分步执行，禁止 && 连接多步骤）
7. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
8. rail_review(post) 后置审查（图有没有？结果合理吗？跟知识库对应吗？）
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时（如 resolution, n_pcs, min_features, FDR threshold 等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式（多角色对抗 v3）：
  - 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
  - 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
  - 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
  - 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
  - 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
  - 辩论结果自动归档到 results/.../log/debate_*.json
- **不确定的参数就辩论**，不要自己拍脑袋
- **辩论最多 3 轮**：3 轮后选最优参数结果

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
  ├── figures/     # PNG + SVG 图表
  ├── data/        # RDS/H5AD 中间数据
  └── results/     # CSV/TSV 结果表
```

### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）

| 时机 | action | 调 | 不调 |
|------|--------|----|------|
| 脚本报错+你分析根因+修复后 | record_error | ✅ R/Python 脚本报错，你找到根因并修复 | ❌ trivial 错误（打字错误、路径不存在） |
| 脚本成功+结果通过 rail_review | record_success | ✅ 分析步骤完成，图生成，审查通过 | ❌ 闲聊/方法咨询/非分析任务 |
| 修复后脚本验证稳定有效 | update_script | ✅ 同一错误修复了，重跑成功 | ❌ 只改参数没改脚本；未验证就更新 |

---

# Create Harmony Embeddings Scrna

Performs batch integration on single-cell RNA-seq data using Harmony and saves the integrated embeddings.

## When to Use

When you need create harmony embeddings scRNA analysis

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `adata_filename` | [Required] Filename of the AnnData object to load (str) | |
| `batch_key` | [Required] Column name in adata.obs that defines the batch variable for integration (str) | |
| `data_dir` | [Required] Directory path where the input file is located and output will be saved (str) | |

> **Parameter Adaptation**: Adjust parameters based on tissue quality, species, and condition. Literature values take priority, then official defaults, then tissue-specific adjustments.

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| RunHarmony with sample_id (16,003 unique) → 1 iter | sample_id had 16,003 unique values (indi | Switch batch variable from sample_id to donor_id ( |
| *(accumulated from runs)* | | |

## References

- Source: Biomni
- Category: genomics
- Language: Python

## 📊 集成质量评估（必输出）

> **铁轨规则**：Harmony 批次校正后，**必须**运行 4 项评估并输出图表。未输出 → rail_review(post) 阻断。

### 必输出指标（4 项铁轨）

| # | 指标 | 通过 | 警告 | 阻断 |
|---|------|------|------|------|
| 1 | **LISI** | > N_batch×0.8 | 0.5-0.8 | < 0.5 |
| 2 | **ASW(batch)** | < 0.1 | 0.1-0.15 | > 0.15 |
| 3 | **kBET** | rejection < 0.05 | 0.05-0.15 | > 0.15 |
| 4 | **PC方差贡献** | PC1 < 50% | PC1 50-70% | PC1 > 70% |

### 必须输出的图（≥3 张）
1. **LISI 分布** — 小提琴图，分 batch（校正前后对比更佳）
2. **ASW 条形图** — 每个 cluster 的 ASW，标注批次基线
3. **PCA Scree plot** — 前 50 PC 方差贡献率 + 累积线

### 不通过处理
- 警告（1-2 指标在警告区）→ `debate_analysis` 辩论是否接受
- 阻断（≥1 指标在阻断区）→ 切换方法（scVI/Scanorama/BBKNN）重跑

### Python 模板 (scanpy + scib)
```python
import scib
lisi = scib.metrics.lisi(adata, batch_key)
asw = scib.metrics.silhouette_batch(adata, batch_key, 'leiden')
kbet = scib.metrics.kBET(adata, batch_key, 'leiden')
sc.pl.pca_variance_ratio(adata, n_pcs=50, save="_scree.png")
```

### R 模板 (Seurat + lisi + kBET)
```r
library(lisi); library(kBET)
lisi_res <- compute_lisi(Embeddings(obj, "harmony"), obj@meta.data, "batch")
kbet_res <- kBET(Embeddings(obj, "harmony"), obj$batch, k0=25)
ElbowPlot(obj, ndims = 50)
```
---

## ⛔ Terminal 完成后强制协议（铁律 26）

```
1. rail_review(phase='post')
2. debate_analysis(
     topic="{当前分析} 参数与结果 —— {样本}",
     context="参数: {实际参数} | 结果: {输出摘要}",
     knowledge_base_info=<KB内容>,
   )
3. save_conclusions(module="{模块}", topic="{分析名}", ...)
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。
⛔ debate confidence=low → 调整参数重跑。
