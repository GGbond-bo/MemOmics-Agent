---
name: cellbender-remove-background
description: "CellBender去除环境RNA污染。使用场景：10X raw h5矩阵，怀疑有空滴/环境RNA污染，需GPU环境，输入raw_feature_bc_matrix"
when_to_use: "[cellbender-remove-background] CellBender背景RNA去除：原始UMI矩阵→深度学习去噪→背景RNA去除→纯净表达矩阵"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: []
    difficulty: basic
    language: Python
    category: decontamination
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

# CellBender 去污染

CellBender remove-background 基于深度生成模型(VAE)估计并去除环境RNA污染。适用于10x Chromium数据，特别是高污染组织(骨骼肌/脑)和衰老样本。参数自适应: 衰老→fpr=0.02/epochs=200; 大数据>50K→epochs=250; 稀缺细胞→fpr=0.005

## When to Use

10x scRNA-seq数据有环境RNA污染(高线粒体、跨类型标记共表达、组织解离样本)

## Triggers

- `CellBender`
- `去污染`
- `环境RNA`
- `ambient RNA`
- `remove background`

## Pipeline

1. 检查raw h5输入
2. GPU检测+模式选择
3. cellbender remove-background运行
4. 质量对比: 前后细胞数/基因数/mt%
5. 保存到cellbender/目录

## Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `fpr` | 0.01(衰老→0.02,稀缺→0.005) | |
| `epochs` | 150(大>50K→250,小<5K→100) | |
| `learning_rate` | 0.001(小数据→0.0005) | |
| `expected_cells` | auto | |

> **Parameter Adaptation**: Adjust parameters based on tissue quality, species, and condition. Literature values take priority, then official defaults, then tissue-specific adjustments.

## Dependencies

- `cellbender`
- `torch`
- `h5py`

## Outputs

- filtered.h5
- 质量对比报告
- 污染比例估计

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| Macaca mulatta | skeletal_muscle | aging | 2025-06-15 | 1.0 |
| Macaca mulatta | brain | aging | 2026-07-04 | 8.0 |
### Proven Scripts

- **Path**: `scripts/reference_script.py` (Stage 1+2+4: Python pipeline)
- **Path**: `scripts/run_cellbender.ps1` (Stage 3: PowerShell batch runner)
- **Path**: `scripts/run_ptrepack.ps1` (Stage 4: Seurat compression)
- **Review Score**: N/A (user-verified, manually imported)
- **Success Count**: 15 samples

### Complete 4-Stage Pipeline

1. **Stage 1** (`reference_script.py:read_raw_to_h5ad`): Read DNB rawmatrix -> h5ad
   - Input: `{sample}/rawmatrix/` (matrix.mtx + barcodes.tsv + features.tsv)
   - Output: `h5ad/{sample}.h5ad`
   - Adds sample prefix to barcodes to prevent cross-sample collisions

2. **Stage 2** (`reference_script.py:convert_h5ad_to_mtx`): h5ad -> CellRanger mtx
   - Optional: CellBender can read h5ad directly
   - Output: `cellbender/{sample}/input_mtx/` (matrix.mtx + barcodes.tsv + features.tsv)

3. **Stage 3** (`run_cellbender.ps1`): CellBender remove-background
   - CRITICAL: Must `Remove-Item Env:PYTHONPATH` before each run
   - Clean `ckpt.tar.gz` before fresh runs (avoid hash mismatch)
   - Verify success by output file existence, NOT exit code
   - Serial execution only (12GB VRAM = 1 sample at a time)
   - Output: `cellbender/{sample}/cellbender_output.h5` + `_filtered.h5`

4. **Stage 4** (`run_ptrepack.ps1`): ptrepack compress for Seurat
   - Input: `cellbender/{sample}/cellbender_output_filtered.h5`
   - Output: `cellbender_seurat/{sample}_filtered_seurat.h5`
   - `ptrepack --complevel 5 "{input}:/matrix" "{output}:/matrix"`

### Known Issues (7 patches, all applied to conda env)

1. **PYTHONPATH pollution**: Unset before every CellBender/ptrepack call
2. **Checkpoint hash mismatch**: Delete ckpt.tar.gz before fresh runs
3. **HTML report failure**: Does NOT affect core output; judge by file existence
4. **Cross-drive os.replace**: Patched to shutil.move (Windows C:->E: issue)
5. **torch.save weakref**: Patched with dill fallback (PyTorch 2.12)
6. **GPU memory**: 12GB VRAM = serial execution only (1 sample at a time)
7. **pandas Series.nonzero()**: Patched with .to_numpy() (14 call sites)

For full patch details: `E:/cellbender/wiki/patches.md`
