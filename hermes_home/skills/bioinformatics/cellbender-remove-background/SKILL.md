---
name: cellbender-remove-background
description: "CellBender去除环境RNA污染。使用场景：10X raw h5矩阵，怀疑有空滴/环境RNA污染，需GPU环境，输入raw_feature_bc_matrix"
when_to_use: "[cellbender-remove-background] CellBender背景RNA去除：原始UMI矩阵→深度学习去噪→背景RNA去除→纯净表达矩阵"
version: 3.0.0
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

CellBender remove-background 基于深度生成模型(VAE)估计并去除环境RNA污染。内部架构：编码器(Encoder)将 UMI count 嵌入到潜在空间 → 解码器(Decoder)重建"去噪"表达矩阵 + 估计背景/空滴概率。训练时 90%数据用于训练，20%空滴注入每个batch。使用 OneCycle 学习率调度（`max_lr = 10 × learning_rate`）。

适用于10x Chromium数据，特别是高污染组织(骨骼肌/脑)和衰老样本。

## When to Use

10x scRNA-seq数据有环境RNA污染(高线粒体、跨类型标记共表达、组织解离样本)

## Triggers

- `CellBender`
- `去污染`
- `环境RNA`
- `ambient RNA`
- `remove background`

## Pipeline — 完整 4 阶段流水线

```
┌─────────────────────────────────────────────────────────────────┐
│  F:/00.RawData/{sample}/output/raw_matrix/                      │
│  ├── matrix.mtx.gz     ← 稀疏矩阵（基因×细胞）                   │
│  ├── barcodes.tsv.gz   ← 细胞 barcode                           │
│  └── features.tsv.gz   ← 基因名（兼容 BGI 1列 / 10x 2/3列）     │
└─────────────────────────────────────────────────────────────────┘
                              │
             ┌────────────────▼────────────────┐
             │  Stage 1: 读取原始矩阵 → h5ad   │
             │  scripts/stage1_to_h5ad.py      │
             │  • 自动探测 features 列数        │
             │  • float64 → int32 省 50% 内存  │
             │  • 添加样本前缀防 barcode 冲突   │
             │  • 跳过已有的，支持断点续跑       │
             └───────────────┬────────────────┘
                             │ *.h5ad
             ┌───────────────▼────────────────┐
             │  Stage 2: CellBender 去污染     │
             │  scripts/run_pipeline.py        │
             │  • 串行执行，一次一个样本         │
             │  • GPU (--cuda)                │
             │  • 清 PYTHONPATH 防污染          │
             │  • 清旧 ckpt 防 hash 冲突        │
             │  • 验证 filtered.h5 产出才通过   │
             │  • 失败不崩，记录日志继续下一个    │
             └───────────────┬────────────────┘
                             │ *_filtered.h5
             ┌───────────────▼────────────────┐
             │  Stage 3: ptrepack 压缩        │
             │  scripts/ptrepack_all.py       │
             │  • complevel=5 压缩            │
             │  • 输出可直接被 Seurat 读取     │
             └───────────────┬────────────────┘
                             │ *_filtered_seurat.h5
             ┌───────────────▼────────────────┐
             │  Stage 4: 前后对比统计          │
             │  scripts/stats_summary.py      │
             │  • 细胞数 / 基因数 / 稀疏度      │
             │  • 去除比例                     │
             │  • 输出 TSV 到 summary/         │
             └───────────────┬────────────────┘
                             │ cellbender_stats.tsv
```

### 快速启动

```bash
# 完整流水线（从 raw matrix 开始，脱离式后台）
start /B python PROJECT_DATA_DIR/run_pipeline.py ^
  --base_dir F:/00.RawData ^
  --work_dir PROJECT_DATA_DIR

# 从 Stage 2 开始（h5ad 已就绪）
start /B python run_pipeline.py ^
  --h5ad_dir PROJECT_DATA_DIR/h5ad ^
  --work_dir PROJECT_DATA_DIR ^
  --skip_stage1

# 仅跑某个阶段
python run_pipeline.py --work_dir PROJECT_DATA_DIR --only_stage 4
```

### 阶段独立运行

```bash
# Stage 1: 只转换 h5ad
python scripts/stage1_to_h5ad.py --base_dir F:/00.RawData --out_dir PROJECT_DATA_DIR/h5ad

# Stage 2: 只跑 CellBender
python scripts/run_pipeline.py --work_dir PROJECT_DATA_DIR --skip_stage1 --only_stage 2

# Stage 3: 只压缩
python scripts/ptrepack_all.py --cb_dir PROJECT_DATA_DIR/cellbender_output --out_dir PROJECT_DATA_DIR/seurat_h5

# Stage 4: 只统计
python scripts/stats_summary.py --h5ad_dir PROJECT_DATA_DIR/h5ad --cb_dir PROJECT_DATA_DIR/cellbender_output --out_dir PROJECT_DATA_DIR/summary
```

---

## 核心参数（来源：官方源码 `remove_background/argparser.py`）

| 参数 | 官方默认值 | 官方 Help 注释 | 版本 |
|------|----------|---------------|------|
| `--fpr` | `[0.01]` | 假阳性率阈值。可多值（如 `0.01 0.05 0.1`），每个值生成一个 filtered 输出 | v0.3+ |
| `--epochs` | `150` | 训练总轮数 | v0.3+ |
| **`--learning-rate`** | **`1e-4` (0.0001)** | 🔑 基学习率。OneCycle 调度下 `max_lr = 10× 此值`，即峰值 `1e-3`。官方注释："**probably do not exceed 1e-3**" | v0.3+ |
| `--expected-cells` | `None` (auto) | 期望细胞数，不传则自动估计 | v0.3+ |
| `--total-droplets` | `25000` | 用于分析的液滴总数（含空滴），从排序后的 UMI barcode 中取 top N | v0.3+ |
| `--model` | `"full"` | 模型架构变体。`"full"`(默认, 2000 latent dims) / `"simple"`(100 dims) / `"ambient"`(无隐变量) | v0.3+ |

### 引用
- 官方仓库: `https://github.com/broadinstitute/CellBender`
- `argparser.py` (v0.3+): `cellbender/remove_background/argparser.py` 第 ~180-220 行
- `consts.py` (v0.3+): `cellbender/remove_background/consts.py`

---

## 内部常量（来源：官方源码 `remove_background/consts.py`）

| 常量 | 值 | 含义 |
|------|-----|------|
| `TRAINING_FRACTION` | **0.9** | 90% 数据用于训练，10% 验证集 |
| `FRACTION_EMPTIES` | **0.2** | 每个 batch 中 20% 的液滴是空滴（空滴=纯噪声，用于模型学习噪声分布） |
| `DEFAULT_BATCH_SIZE` | **128** | 默认 batch size |
| `CELL_PROB_CUTOFF` | **0.5** | 细胞概率 > 0.5 判定为真实细胞 |
| `LOW_UMI_CUTOFF` | **5** | UMI < 5 的液滴直接移除，不参与分析 |
| `LOW_UMI_FRACTION_CUTOFF` | 0.01 | 低 UMI 液滴比例上限 |
| `MAX_STDDEV` | 10.0 | 背景基因表达的标准差上限（超出截断） |
| `MIN_STDDEV` | 0.001 | 背景基因表达的标准差下限（计算数值稳定性） |

---

## 学习率详解（OneCycle 调度机制）

```
Step 1: 线性预热 → 学习率从 learning_rate/10 升至 max_lr
Step 2: 余弦退火 → 学习率从 max_lr 降至 learning_rate/10
```

| 官方默认 `learning_rate = 1e-4` | 值 |
|---------------------------------|-----|
| 起始 LR | 1e-5 |
| 峰值 LR (max_lr = 10×) | **1e-3** |
| 结束 LR | 1e-5 |

> ⚠️ **之前 Skill v1.0 的 `learning_rate=0.001` 是错误的** —— 它把峰值 LR 当成了基学习率，导致实际峰值达到 `0.01` (10×)，超出官方上限 "do not exceed 1e-3" 10 倍。v2.0 修正为官方默认 `1e-4`。

---

## 场景自适配参数（领域知识叠加，非官方默认）

| 场景 | 调整 | 调整幅度 | 理由 |
|------|------|---------|------|
| **衰老样本** | `--fpr 0.02` | +0.01 | 衰老组织 RNA 渗漏更多，适度放宽 |
| **大数据 (>50K cells)** | `--epochs 250` | +100 | 更多细胞需要更多训练轮次 |
| **小数据 (<5K cells)** | `--epochs 100` | -50 | 防过拟合 |
| **稀缺细胞类型** | `--fpr 0.005` | -0.005 | 收紧 FPR 保护稀有群体 |
| **低质量样本 (高 mt%)** | `--learning-rate 5e-5` | 减半 | 更慢学习，避免过拟合噪声 |
| **高质量样本 (低 mt%)** | `--learning-rate 1e-4` | 默认 | 标准即可 |

> **自适应优先级**: 文献参数 > 官方默认 > 领域经验。领域经验值遵循官方注释的边界约束（如 learning_rate 不超过 1e-3）。

---

## 完整命令行示例

```bash
# 标准运行（官方默认参数）
cellbender remove-background \
  --input raw_feature_bc_matrix.h5 \
  --output cellbender_output.h5 \
  --fpr 0.01 \
  --epochs 150 \
  --learning-rate 1e-4 \
  --total-droplets-included 25000

# 衰老肌肉样本（领域自适应）
cellbender remove-background \
  --input raw_feature_bc_matrix.h5 \
  --output cellbender_output.h5 \
  --fpr 0.02 \
  --epochs 150 \
  --learning-rate 1e-4 \
  --total-droplets-included 25000

# 大数据 (100K+ cells)
cellbender remove-background \
  --input raw_feature_bc_matrix.h5 \
  --output cellbender_output.h5 \
  --fpr 0.01 \
  --epochs 250 \
  --learning-rate 1e-4

# 多 FPR 输出（一个 FPR 一个 filtered 文件）
cellbender remove-background \
  --input raw_feature_bc_matrix.h5 \
  --output cellbender_output.h5 \
  --fpr 0.01 0.05 0.1 \
  --epochs 150
```

---

## Dependencies

- `cellbender`
- `torch`
- `h5py`

## Outputs

- `cellbender_output_filtered.h5` (去污染后的 count 矩阵)
- `cellbender_output.h5` (完整输出: latent 编码 + 细胞概率 + 背景估计 + 报告数据)
- `cellbender_output.pdf` / `.html` (训练报告, 可选)

## Quality Check

| 检查项 | 正常范围 | 异常处理 |
|--------|---------|---------|
| 去除细胞比例 | 5-30% | >50% → 怀疑 overkill, 调低 fpr 或用 --model simple |
| 剩余细胞数 | 接近 --expected-cells | 偏差大 → 检查 --total-droplets-included |
| 平均 UMI/细胞 变化 | 减少 5-20% | >50% → 去污染过猛 |
| 训练 loss 曲线 | 持续下降 | 震荡 → 降 learning-rate 或加 epochs |

---

## Proven Scripts

> Scripts that have been successfully executed and passed analysis review.
> These are automatically saved after successful runs.

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| Macaca mulatta | skeletal_muscle | aging | 2025-06-15 | 9.0 |
| Macaca mulatta | brain | aging | 2026-07-04 | 8.0 |

### Script Reference

| # | Script | 职能 | 输入 | 输出 |
|---|--------|------|------|------|
| 1 | `scripts/stage1_to_h5ad.py` | 原始 matrix → h5ad | F:/00.RawData/{s}/output/raw_matrix/ | {work_dir}/h5ad/{s}.h5ad |
| 2 | `scripts/run_pipeline.py` | 完整流水线（Stage 1-4） | raw / h5ad | cellbender_output/ + seurat_h5/ + summary/ |
| 3 | `scripts/ptrepack_all.py` | 批量 ptrepack 压缩 | cellbender_output/{s}/_filtered.h5 | seurat_h5/{s}_filtered_seurat.h5 |
| 4 | `scripts/stats_summary.py` | 前后对比统计表 | h5ad/ + cellbender_output/ | summary/cellbender_stats.tsv |
| 5 | `scripts/reference_script.py` | v1 参考（用户验证 15 样本） | — | — |

### Pipeline 数据流

```
raw matrix (三件套)          Stage 1           h5ad (int32)
    │                        stage1_to_h5ad.py     │
    │                        ───────────────       │
    │  features.tsv.gz (1/2/3列自动识别)            │
    │  barcodes.tsv.gz                             │
    │  matrix.mtx.gz                               │
    │                        ← float64→int32 省50% │
    │                        ← 添加样本前缀        │
    └───────────────────────────────────────────────┘
                                                   │
    ┌───────────────────────────────────────────────┘
    │  h5ad/                           Stage 2
    │                                  run_pipeline.py (--skip_stage1)
    │                                  ─────────────
    │                                  串行 GPU, 清 PYTHONPATH
    │                                  清 ckpt, 验证 .h5
    │                                  失败→继续下一个
    └──────────────────► cellbender_output/{s}/
                            ├── cellbender_output.h5
                            ├── cellbender_output_filtered.h5
                            └── cellbender_output.pdf
                                                    │
                         Stage 3                    │
                         ptrepack_all.py            │
                         ─────────────              │
                         complevel=5                 │
                         PYTHONPATH clean            │
                                                    │
                         seurat_h5/{s}_filtered_seurat.h5
                                                    │
                         Stage 4                    │
                         stats_summary.py           │
                         ─────────────              │
                         前后对比                    │
                                                    │
                         summary/cellbender_stats.tsv
```

### Known Issues (7 patches, all applied to conda env)

1. **PYTHONPATH pollution**: Unset before every CellBender/ptrepack call
2. **Checkpoint hash mismatch**: Delete ckpt.tar.gz before fresh runs
3. **HTML report failure**: Does NOT affect core output; judge by file existence
4. **Cross-drive os.replace**: Patched to shutil.move (Windows C:->E: issue)
5. **torch.save weakref**: Patched with dill fallback (PyTorch 2.12)
6. **GPU memory**: 12GB VRAM = serial execution only (1 sample at a time)
7. **pandas Series.nonzero()**: Patched with .to_numpy() (14 call sites)

For full patch details: `E:/cellbender/wiki/patches.md`

---

## Changelog

| 版本 | 日期 | 改动 |
|------|------|------|
| v3.1 | 2026-07-29 | 新增 Terminal 完成后强制协议（铁律 26）：辩论→结论→记录→更新主线 |
| v3.0 | 2026-07-26 | **4 脚本大重构**：新增 `stage1_to_h5ad.py`（BGI 1列兼容+int32转换+argparse）、`run_pipeline.py`（完整 watchdog 流水线）、`ptrepack_all.py`（批量压缩）、`stats_summary.py`（前后对比统计表）。SKILL.md 重写 Pipeline 节为完整数据流图+快速启动+独立运行示例 |
| v2.0 | 2026-07-24 | 修正 `learning_rate` 从 `0.001` → `1e-4`（与官方源码对齐）；新增 `--model`/`--total-droplets`/`--low-count-threshold` 等缺失参数；新增 OneCycle 调度说明 + 内部常量表 + 源码引用；新增 Quality Check 表 + Changelog |
| v1.0 | 2025-06 | 初始版本，含场景自适应参数和 4-Stage Pipeline |

---

## ⛔ Terminal 完成后强制协议（铁律 26 · 读完本 skill 即生效）

**本 skill 只执行一个分析步骤。terminal 返回后，你必须立即按以下顺序完成 5 件事，缺一不可：**

```
1. rail_review(phase='post', code_executed=<用 read_file 读脚本文件，传入完整代码>)
   审查：输出文件存在？大小正常？参数与 skill 文档一致？

2. debate_analysis(
     topic="CellBender 去污染参数与收敛 —— {样本信息}",
     context="数据: {物种} {组织} {细胞数} | 参数: fpr={x} epochs={y} lr={z} | 结果: 去除{比例}%细胞, 训练loss从{start}→{end}",
     knowledge_base_info=<预查的 KB 内容>,
   )
   辩论维度：
   - 参数: fpr 选得合理吗？learning_rate 对吗？epochs 够吗？
   - 收敛: loss 曲线是否收敛？有震荡吗？
   - 效果: 去除比例在正常范围吗？（5-30%）残留噪声多吗？
   - 场景适配: 衰老样本用 fpr=0.02 了吗？大数据加 epochs 了吗？

3. save_conclusions(
     module="01_decontamination",
     topic="CellBender 去污染",
     debate_json=<debate_analysis 返回的完整 JSON>,
     output_dir=<session results_dir>
   )
   → 写入 01_decontamination/conclusions.md + conclusions.json

4. skill_evolution(action="record_run",
     skill="cellbender-remove-background",
     script=<脚本路径>,
     params_json=<实际使用的参数 JSON>,
     result_summary=<去除比例 + 收敛状态 + 辩论结论摘要>,
     quality_score=<1-10>
   )

5. 更新 task_plan.md: Phase 1 标记完成, Current Phase 指向 Phase 2
```

**⛔ 未完成以上 5 步 = 禁止启动下一个分析步骤。**
**⛔ 禁止一次性撰写多个步骤的代码。每次只跑一个分析。**
**⛔ 如果 debate 裁判给出 confidence=low 或 verdict=modify，必须先修改参数重跑，再 record_run。**
