---
name: sctour-trajectory-inference
description: "scTour VAE 深度潜在时间推断 + 向量场 + 跨数据集预测。无需指定起点，无监督学习细胞动力学。"
when_to_use: "[sctour-trajectory-inference] scTour VAE 深度潜在时间推断 + 向量场 + 跨数据集预测。无需指定起点，无监督学习细胞动力学。"
version: 1.5.1
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [trajectory, pseudotime, sctour, VAE, vector-field, latent-space, 03_高级分析]
    difficulty: advanced
    language: Python
    category: scRNA
prerequisites:
  python_packages:
    - sctour
    - scanpy
    - torch
    - torchdiffeq
    - numpy
    - pandas
    - matplotlib
    - scipy
    - anndata
    - scikit-misc
---

## 🚨 执行前强制检查清单（加载此 skill 后必须逐条确认，不可跳过）

> **此 skill 的 SKILL.md 已加载成功。在写任何代码之前，必须完成以下 10 步检查。**
> 跳过任何一项 = 分析不完整，用户会不满。**历史教训：此 skill 曾被跳过，导致 log/ 缺失、结果路径错误、record_run 未记录。**

| # | 步骤 | 工具调用 | 状态 |
|:-:|:----|:---------|:----:|
| 1 | search_knowledge | `search_knowledge(species, tissue, direction, "scTour 参数")` | ⬜ |
| 2 | skill_view | ✅ 当前已加载 `sctour-trajectory-inference` | ✅ |
| 3 | check_env | `check_env(["sctour", "scanpy", "torch", "scikit-misc"], language="Python")` | ⬜ |
| 4 | rail_review(pre) | `rail_review(phase="pre", module_id="sctour", ...)` | ⬜ |
| 5 | write_file | 写脚本到 `results/.../scTour/scripts/` | ⬜ |
| 6 | terminal | 分步执行，禁止 && 连接 | ⬜ |
| 7 | debate_analysis | `debate_analysis(topic="scTour 参数/结果", ...)` | ⬜ |
| 8 | rail_review(post) | `rail_review(phase="post", module_id="sctour", ...)` | ⬜ |
| 9 | skill_evolution | `record_run` 或 `record_error` → **⚠️ 验证文件已落盘** | ⬜ |
| 10 | log/ 目录 | 确认 `log/analysis.log` + `debate_*.json` + `run_record_*.json` 存在 | ⬜ |
| 11 | **结果路径验证** | 确认结果在 `{MEMOMICS_ROOT}/results/` 下，**不是** `{MEMOMICS_ROOT}/hermes-agent/results/` | ⬜ |
| 12 | **报告完整性验证** | 生成 HTML 报告后执行：检查图片引用数、辩论段数、裁判裁决数、参数来源章节皆完整 | ⬜ |

> **⚠️ 常见错误**：Agent 经常跳过步骤 1（search_knowledge）和步骤 9（skill_evolution），直接凭记忆或 web 搜索就写代码。**这违反铁律。** 即使你觉得自己会写 scTour，也必须先查知识库和加载此 skill。此 checklist 的存在就是为了防止这种跳过。
>
> **⚠️ Step 9 落盘验证**：`skill_evolution(action="record_run")` 可能返回 `{"success": true}` 但实际**未写入文件**（2026-07-08 会话中发现：6 次调用中 2 次静默不写）。强制预防措施——每次 `record_run` 后立即执行：
> ```python
> import os
> log_dir = "results/.../log/"
> expected = f"run_record_{timestamp}_{seq}.json"
> if not os.path.isfile(os.path.join(log_dir, expected)):
>     # skill_evolution 未落盘，手动写入
>     with open(os.path.join(log_dir, expected), "w") as f:
>         json.dump(record_data, f, indent=2)
> ```
> 此验证步骤**不可跳过**。宁可多检查一次，不可漏一份记录。
>
> **⚠️ 结果路径**：所有输出必须放在 `results/` 下（项目根目录下的 `results/`，如 `MEMOMICS_HOME/results/`），**绝对不放桌面，不放 `hermes-agent/results/`。** 2026-07-08 会话教训：memory 误写为 `hermes-agent/results/` 导致日志放错位置，用户指出后才修正。基路径统一为 `{MEMOMICS_ROOT}/results/`（读取 `hermes_home/.install_path` 获取真实路径）。`generate_report` 的 `output_path` 必须指定，不依赖默认桌面路径。
>
> ⚠️ **目录结构**：每步执行后必须创建 `figures/` `results/` `scripts/` `data/` `log/` 五个子目录。`log/` 目录是强制保留的，包含 `analysis.log`、`debate_*.json`、`run_record_*.json`。

---

## Proven Scripts

> 以下为经实际运行验证成功的脚本记录。下次同类分析可在 `skill_evolution(action="query_logs")` 中查阅。

| 物种 | 组织 | 方向 | 日期 | 评分 |
|:----|:----|:----|:----:|:----:|
| 人类 | 骨骼肌 | 衰老 | 2026-07-08 | 9.0 |

---

# scTour — 深度潜在时间轨迹推断

基于 VAE + 神经 ODE 的无监督细胞动力学推断工具。不需要指定起始细胞，不区分 spliced/unspliced mRNA，同时学习伪时间、向量场和潜在空间。

## 触发场景

**✅ 应该使用 scTour 的场景：**
- 需要对 scRNA-seq 数据做**无监督伪时间推断**（不需要指定起点）
- 想要同时获得**伪时间 + 转录组向量场 + 潜在空间嵌入**三种输出
- 数据有**批次效应**，需要批次不敏感的推断
- 需要**跨数据集预测**（用训练好的模型预测新数据的伪时间/向量场/潜在空间）
- 需要**预测未观测时间点的转录组状态**
- 想用深度学习方法替代传统轨迹推断（Monocle3、Slingshot 等）

**❌ 不应该使用 scTour 的场景：**
- 需要 RNA velocity（spliced/unspliced 区分）→ 用 scVelo / CellRank
- 需要基于图的伪时间（Monocle3 风格）→ 用 Monocle3 / Slingshot
- 需要命运概率映射 → 用 CellRank
- 细胞数 < 500 → 数据量不足以训练 VAE
- 细胞数 < 500 → 数据量不足以训练 VAE

> **GPU 策略**：scTour 优先使用 GPU（CUDA），如果没有 GPU 则自动回退到 CPU。CPU 也能完整跑通，只是训练较慢。**不因无 GPU 而阻断执行**。\n>\n> **⚠️ CPU 可能比 GPU 更快（小模型场景）**：当细胞数 < 10,000 且 VAE 模型较小时（n_latent=5, n_vae_hidden=128），GPU 的显存搬运开销（~3-4s/epoch）可能超过 CPU 直接计算（~1.8s/epoch）。实测 9,568 细胞 × 1,500 HVGs 时 CPU 快 2×。**策略**：细胞数 < 10,000 时使用 `use_gpu=False`；细胞数 > 50,000 时使用 `use_gpu=True`；中间范围自由选择。\n>\n> **Blackwell GPU (RTX 50 系列)**：NVIDIA RTX 5070 Ti / 5080 / 5090 使用 Blackwell 架构 (compute capability sm_120)。PyTorch 官方 cu124 索引仅提供 ≤2.6.0 版本（只支持到 sm_90 Hopper）。要使用 CUDA 加速，必须安装 PyTorch ≥2.8.0 从 cu128 测试通道：
> ```bash
> pip install "torch>=2.8.0" --index-url https://download.pytorch.org/whl/test/cu128
> ```
> （这会下载 ~2.7GB，因包含完整的 CUDA 12.8 运行时。安装后验证：`python -c "import torch; print(torch.cuda.is_available())"`）

**关键词触发**：scTour、深度伪时间、VAE 轨迹、无监督伪时间、潜在时间推断、向量场、神经ODE轨迹

---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

### 规则1: 拿到数据 → 必须调 search_knowledge
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 8步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. skill_view 加载对应 skill 的 SKILL.md
3. check_env 检查环境
4. rail_review(pre) 前置审查
5. write_file 写这一步的代码（只写这一步！）
6. terminal 执行（分步执行，禁止 && 连接多步骤）
7. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
8. rail_review(post) 后置审查
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时（如 alpha_recon_lec, alpha_recon_lode, alpha_z, alpha_predz, n_latent, nepoch 等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式：正方（支持当前参数）vs 反方（质疑+替代方案）→ 裁判决断
- **不确定的参数就辩论**，不要自己拍脑袋

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
  ├── data/        # H5AD 中间数据
  └── results/     # CSV/TSV 结果表
```

### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）

| 时机 | action | 调 | 不调 |
|------|--------|----|------|
| 跑脚本前 | query_logs | ✅ 每次执行分析脚本前，查同类运行日志 | ❌ 非分析任务 |
| 脚本报错+你分析根因+修复后 | record_error | ✅ R/Python 脚本报错，你找到根因并修复 | ❌ trivial 错误（打字错误、路径不存在） |
| 脚本成功+结果通过 rail_review | record_run | ✅ 分析步骤完成，图生成，审查通过 | ❌ 闲聊/方法咨询/非分析任务 |

---

## 执行方式

| 方式 | 文件 | 适用场景 |
|------|------|---------|
| **命令行脚本** | `scripts/run.py` → `run_sctour_inference.py` → `run_sctour_visualization.py` | Agent 自动化执行，8 步循环 + 审查 + 辩论 |\n| **双路线脚本** | `scripts/dual_route_sctour.py` | 两条独立生物学过程的 scTour 分析（如去神经化 vs 应激→成熟），含 Zone1 内部梯度 + 年龄梯度锚点 |
| **Jupyter Notebook** | `scripts/sctour_notebook.py` | 手动交互式探索，逐 Cell 运行，参数调优只需重跑 Cell 3 |

> **Notebook 版**：13 个 Cell（环境→加载→预处理→训练→伪时间→潜在空间→向量场→4 种可视化→保存→统计→调参参考），适合在 Jupyter 中逐步调试。训练 Cell 独立，改参数后只重跑它即可。
>
> **📋 交付规则**：当用户说"给我脚本""我要拿去跑"时，直接把 `sctour_notebook.py` 的完整代码贴到对话中，不要只保存到 skill 目录。用户要的是可操作的交付物，不是文件路径。

## Quick Start

**最快测试流程（~15-30分钟，取决于数据大小）：**

```python
# Step 1: 加载数据
import sctour as sct
import scanpy as sc

adata = sc.read("your_data.h5ad")

# Step 2: 预处理（必须计算 QC metrics + 选择高变基因）
sc.pp.calculate_qc_metrics(adata, percent_top=None, log1p=False, inplace=True)
sc.pp.highly_variable_genes(adata, flavor='seurat_v3', n_top_genes=1000, subset=True)

# Step 3: 训练 scTour 模型
tnode = sct.train.Trainer(adata, loss_mode='nb', alpha_recon_lec=0.5, alpha_recon_lode=0.5)
tnode.train()

# Step 4: 推断伪时间
adata.obs['ptime'] = tnode.get_time()

# Step 5: 推断潜在空间
mix_zs, zs, pred_zs = tnode.get_latentsp(alpha_z=0.5, alpha_predz=0.5)
adata.obsm['X_TNODE'] = mix_zs

# Step 6: 推断向量场
adata.obsm['X_VF'] = tnode.get_vector_field(adata.obs['ptime'].values, adata.obsm['X_TNODE'])

# Step 7: 可视化
adata = adata[np.argsort(adata.obs['ptime'].values), :]
sc.pp.neighbors(adata, use_rep='X_TNODE', n_neighbors=15)
sc.tl.umap(adata, min_dist=0.1)
sct.vf.plot_vector_field(adata, zs_key='X_TNODE', vf_key='X_VF', use_rep_neigh='X_TNODE', 
                         color='celltype', show=True, save='sctour_vector_field.png')
```

---

## Installation

### 必需软件

| 软件 | 版本 | 安装 |
|------|------|------|
| Python | ≥ 3.7 | — |
| scTour | ≥ 1.0.0 | `pip install sctour` 或 `conda install -c conda-forge sctour` |
| scanpy | ≥ 1.9 | `pip install scanpy` |
| torch | ≥ 1.10 | `pip install torch` |
| torchdiffeq | — | 随 scTour 自动安装 |
| numpy | ≥ 1.20 | 随 scTour 自动安装 |
| pandas | ≥ 1.3 | 随 scTour 自动安装 |
| matplotlib | ≥ 3.4 | 随 scTour 自动安装 |
| scipy | ≥ 1.7 | 随 scTour 自动安装 |
| anndata | ≥ 0.8 | 随 scTour 自动安装 |
| scikit-misc | ≥ 0.1.4 | `pip install scikit-misc`（`flavor='seurat_v3'` 需要） |

**快速安装：**
```bash
pip install sctour scanpy scikit-misc

# 或 conda
conda install -c conda-forge sctour scanpy scikit-misc
```

**GPU/CPU 策略（自动检测）：**
- `use_gpu=None`（默认）：自动检测 CUDA，有 GPU 用 GPU，无 GPU 自动回退 CPU
- `use_gpu=True`：强制使用 GPU（无 GPU 时会报错）
- `use_gpu=False`：强制使用 CPU
- **不因无 GPU 而阻断执行**——CPU 也能完整跑通，只是训练较慢

---

## Inputs

### 必需输入

1. **AnnData 对象**（.h5ad），包含：
   - `.X`：原始 UMI counts（`loss_mode='nb'` 或 `'zinb'`）或 log1p 归一化表达（`loss_mode='mse'`）
   - **若 counts 在 `.layers['counts']` 中**：先复制到 `.X`：
     ```python
     adata.X = adata.layers['counts'].copy()
     # 然后 scTour 用 loss_mode='nb'
     ```
   - `.obs`：必须包含 `n_genes_by_counts`（通过 `scanpy.pp.calculate_qc_metrics` 计算）
   - 预处理：建议先跑 `scanpy.pp.highly_variable_genes` 选择 1000-2000 个高变基因

### 数据要求

- **最小细胞数**：500（推荐 1000+）
- **推荐高变基因数**：1000（scTour 官方推荐，平衡速度和精度）
- **GPU**：自动检测（有 GPU 用 GPU，无 GPU 自动回退 CPU，不阻断）
- **内存**：8GB+ RAM（大数据集需要更多）
- **运行时间**：取决于数据大小，通常 10-60 分钟

---

## Outputs

### 推断输出

| 输出 | 存储位置 | 说明 |
|------|---------|------|
| 伪时间 (pseudotime) | `adata.obs['ptime']` | 每个细胞的发育伪时间，值范围 [0, 1] |
| 潜在空间 (latent space) | `adata.obsm['X_TNODE']` | mix_zs，加权组合的潜在表示 |
| 向量场 (vector field) | `adata.obsm['X_VF']` | 转录组向量场，用于 streamplot 可视化 |
| 模型权重 | `*.pth` | 训练好的模型，可用于跨数据集预测 |

### 可视化输出

- 伪时间 UMAP 图
- 向量场 streamplot 图
- 潜在空间 UMAP 图

---

## 标准工作流

### Step 1: 预处理

```python
# 必须：计算 QC metrics
sc.pp.calculate_qc_metrics(adata, percent_top=None, log1p=False, inplace=True)

# 选择高变基因
sc.pp.highly_variable_genes(adata, flavor='seurat_v3', n_top_genes=1000, subset=True)
```

**⚠️ 注意：`n_genes_by_counts` 必须存在于 `adata.obs` 中，否则 scTour 会报错！**

### Step 2: 训练模型

```python
tnode = sct.train.Trainer(
    adata,
    loss_mode='nb',           # 推荐 'nb'（负二项分布），适合 UMI counts
    alpha_recon_lec=0.5,      # encoder 重建误差权重
    alpha_recon_lode=0.5,     # ODE 重建误差权重
    percent=None,              # 训练细胞比例，>10000 细胞默认 0.2，否则 0.9
    n_latent=5,                # 潜在空间维度
    n_ode_hidden=25,           # ODE 隐藏层维度
    n_vae_hidden=128,          # VAE 隐藏层维度
    nepoch=None,               # 自动计算：min(round(10000/ncells*400), 400)
    batch_size=1024,
    lr=1e-3,
    random_state=0,
    use_gpu=None,              # None=自动检测（有GPU用GPU，无GPU用CPU）
)
tnode.train()
```

### Step 3: 推断伪时间

```python
adata.obs['ptime'] = tnode.get_time()

# 如果伪时间方向反了，用 post-inference adjustment
# from sctour.train import reverse_time
# adata.obs['ptime'] = reverse_time(adata.obs['ptime'].values)
```

### Step 4: 推断潜在空间

```python
# alpha_z 越大 → 更偏向内在转录组结构
# alpha_predz 越大 → 更偏向外源伪时间排序
mix_zs, zs, pred_zs = tnode.get_latentsp(alpha_z=0.5, alpha_predz=0.5)
adata.obsm['X_TNODE'] = mix_zs
```

### Step 5: 推断向量场

```python
adata.obsm['X_VF'] = tnode.get_vector_field(
    adata.obs['ptime'].values, 
    adata.obsm['X_TNODE']
)
```

### Step 6: 可视化

```python
# 按伪时间排序细胞（可选，有时能改善轨迹）
adata = adata[np.argsort(adata.obs['ptime'].values), :]

# 基于潜在空间计算 UMAP
sc.pp.neighbors(adata, use_rep='X_TNODE', n_neighbors=15)
sc.tl.umap(adata, min_dist=0.1)

# 画伪时间
sc.pl.umap(adata, color='ptime', cmap='viridis', save='_sctour_ptime.png')

# 画向量场
sct.vf.plot_vector_field(
    adata, 
    zs_key='X_TNODE', 
    vf_key='X_VF',
    use_rep_neigh='X_TNODE',
    t_key='ptime',              # 可选：结合伪时间信息
    color='celltype',
    save='sctour_vector_field.png'
)
```

---

## API 参考

### `sct.train.Trainer` — 模型训练

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `adata` | — | AnnData 对象（必需） |
| `percent` | None | 训练细胞比例。>10000 细胞默认 0.2，否则 0.9 |
| `n_latent` | 5 | 潜在空间维度 |
| `n_ode_hidden` | 25 | ODE 隐藏层维度 |
| `n_vae_hidden` | 128 | VAE 隐藏层维度 |
| `batch_norm` | False | 是否使用 BatchNorm |
| `ode_method` | 'euler' | ODE solver（参考 torchdiffeq） |
| `step_size` | None | ODE 积分步长 |
| `alpha_recon_lec` | 0.5 | encoder 重建误差权重 |
| `alpha_recon_lode` | 0.5 | ODE 重建误差权重 |
| `alpha_kl` | 1.0 | KL 散度权重 |
| `loss_mode` | 'nb' | 损失函数：'mse'/'nb'/'zinb' |
| `nepoch` | None | epoch 数，自动计算 |
| `batch_size` | 1024 | 批次大小 |
| `lr` | 1e-3 | 学习率 |
| `wt_decay` | 1e-6 | 权重衰减 |
| `random_state` | 0 | 随机种子 |
| `val_frac` | 0.1 | 验证集比例 |
| `use_gpu` | None (auto) | None=自动检测 / True=强制GPU / False=强制CPU |

**核心方法：**
- `train()` — 训练模型
- `get_time()` — 获取伪时间
- `get_latentsp(alpha_z, alpha_predz)` — 获取潜在空间
- `get_vector_field(t, z)` — 获取向量场
- `save_model(save_dir, save_prefix)` — 保存模型
- `load_model(save_dir, save_prefix)` — 加载模型（静态方法）

### `sct.vf.plot_vector_field` — 向量场可视化

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `adata` | — | AnnData 对象 |
| `zs_key` | — | `.obsm` 中潜在空间的 key |
| `reverse` | False | 是否反转向量场方向 |
| `vf_key` | 'X_VF' | `.obsm` 中向量场的 key |
| `use_rep_neigh` | None | 邻居检测使用的表示 |
| `t_key` | None | `.obs` 中伪时间的 key |
| `n_neigh` | 20 | 邻居数 |
| `stream` | True | 是否用 streamplot |
| `stream_density` | 2 | streamplot 密度 |
| `save` | None | 保存路径（True = 'sctour_vector_field.png'） |

### `sct.train.reverse_time` — 伪时间反转

```python
from sctour.train import reverse_time
reversed_t = reverse_time(adata.obs['ptime'].values)
```

### `sct.predict` — 跨数据集预测

| 函数 | 说明 |
|------|------|
| `load_model(save_dir, save_prefix)` | 加载训练好的模型 |
| `predict_time(new_data)` | 预测新数据的伪时间 |
| `predict_latentsp(new_data)` | 预测新数据的潜在空间 |
| `predict_vector_field(new_data)` | 预测新数据的向量场 |
| `predict_ltsp_from_time(t)` | 预测未观测时间点的转录组潜在空间 |

---

## 🔄 多配置对比工作流（Multi-Configuration Comparison）

> 本会话经验：scTour 对参数敏感，建议每次分析至少跑 3 个对比配置，再通过统计比较 + debate 选出最优结果。

### 推荐配置方案

| 配置 | 命名 | `alpha_recon_lec` | `alpha_recon_lode` | `n_latent` | 目标 |
|:----:|:----:|:---:|:---:|:---:|------|
| 🟢 平衡 | `run1_balanced` | 0.5 | 0.5 | 5 | scTour 默认，通用基线 |
| 🔵 编码器偏重 | `run2_encoder` | 0.8 | 0.2 | 8 | 保留更多细胞类型结构 |
| 🟠 ODE 偏重 | `run3_ode` | 0.3 | 0.7 | 3 | 强调伪时间排序 |
| 🟣 大潜在空间 | `run4_large` | 0.5 | 0.5 | 10 | 高维生物信号捕获 |

### 对比分析 Pipeline

```python
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

# 1. 收集各配置的伪时间统计
runs = {}
for run_name in ['run1_balanced', 'run2_encoder', 'run3_ode']:
    ptime = pd.read_csv(f'{run_name}/results/pseudotime.csv', index_col=0)
    runs[run_name] = ptime

# 2. 合并统计
stats = []
for run_name, ptime_df in runs.items():
    for group in ptime_df['type'].unique():
        subset = ptime_df[ptime_df['type'] == group]['ptime']
        stats.append({
            'run': run_name, 'group': group,
            'mean': subset.mean(), 'std': subset.std(),
            'median': subset.median(), 'n_cells': len(subset)
        })
stats_df = pd.DataFrame(stats)
stats_df.to_csv('comparison/parameter_comparison.csv', index=False)

# 3. KS 检验（年轻 vs 老年伪时间分离度）
results = []
for run_name, ptime_df in runs.items():
    young = ptime_df[ptime_df['type'].str.contains('Young', case=False)]['ptime']
    old = ptime_df[ptime_df['type'].str.contains('Old|diabete', case=False)]['ptime']
    ks_stat, ks_pval = ks_2samp(young, old)
    results.append({
        'run': run_name,
        'young_mean': young.mean(), 'old_mean': old.mean(),
        'delta': old.mean() - young.mean(),
        'KS_stat': ks_stat, 'KS_pval': ks_pval,
        'separability': 'good' if ks_pval < 0.05 and abs(old.mean() - young.mean()) > 0.1 else 'poor'
    })
comparison_df = pd.DataFrame(results)
```

### 选择最佳配置的辩论标准

| 标准 | 权重 | 说明 |
|:----|:---:|------|
| **生物学一致性** | ⭐⭐⭐ | 伪时间排序是否与已知生物学方向一致（如 Young→Old） |
| **组间分离度** | ⭐⭐ | KS 检验 p-value + 均值差的绝对值 |
| **组内方差** | ⭐⭐ | 每组内标准差尽量小（组内均质） |
| **细胞类型连续性** | ⭐ | 同细胞类型是否连续分布在伪时间轴上 |

> **辩论要求**：多配置结果对比后，**必须调用 `debate_analysis` 辩论**，让正方/反方/裁判从生物学+统计+生信角度选出最优配置。辩论记录归档到 `results/.../log/debate_comparison_*.json`。

### 目录结构

```
results/<species>_<tissue>_<direction>_<date>/03_advanced/scTour/
├── run1_balanced/          # 平衡配置
│   ├── figures/            # 伪时间UMAP、向量场图
│   ├── results/            # pseudotime.csv, 潜在空间坐标
│   ├── data/               # 中间adata对象
│   └── scripts/            # 单配置脚本
├── run2_encoder/           # 编码器偏重配置
├── run3_ode/               # ODE偏重配置
├── comparison/             # 多配置对比
│   ├── figures/            # 对比箱线图、KS检验表
│   └── parameter_comparison.csv
├── data/                   # 共享预处理数据
├── scripts/                # 全局脚本
└── scTour_Trajectory_Report.html  # 综合HTML报告
```

> **重要**：结果基路径为 `results/`（如 `MEMOMICS_HOME/results/`）。HTML 报告生成到结果目录下，**不放桌面**。

---

## 🔀 双路线独立 scTour 工作流（Dual-Route scTour）

> **⚠️ 后台进程中断恢复**：双路线分析耗时较长（4 配置 × 200 epoch），**必须实现 checkpoint 恢复机制**，否则进程意外中断后需从头重跑。2026-07-08 会话经验：4 配置中仅完成 1 个（run1_balanced），其余因进程中断丢失。同一会话中 checkpoint resume 策略**被验证有效**：`run_single_config` 顶部检查 `pseudotime.csv` 是否存在且非空，发现 run2_encoder 已在前一次中断前完成，自动跳过该配置，仅跑 run3_ode 和路线B 的 3 个配置。**关键设计**：每个配置写入独立子目录，pseudotime.csv 是单一原子性完成标志。

### 中断恢复策略（Checkpoint Resume）

当后台进程意外中断时（OOM/超时/网络），使用以下策略恢复：

```python
import os, json

# 1. 检查哪些配置已完成
output_root = "results/scTour/routeA"
completed = []
for cfg_name in ['run1_balanced', 'run2_encoder', 'run3_ode']:
    csv_path = f"{output_root}/{cfg_name}/results/pseudotime.csv"
    if os.path.isfile(csv_path) and os.path.getsize(csv_path) > 100:
        completed.append(cfg_name)

# 2. 只跑未完成的配置
pending = [cfg for cfg in all_configs if cfg['name'] not in completed]
print(f"已完成: {completed}，待跑: {[c['name'] for c in pending]}")
for cfg in pending:
    run_single_config(adata, cfg, output_root, ...)  # 单配置执行
```

**最佳实践**：
- 每个配置的结果写入**独立子目录**（`run1_balanced/` → `results/`）：单个配置完成后，即使其他配置中断，已完成的结果不会丢失
- 在 `run_sctour_route()` 顶部先检查 `pseudotime.csv` 是否存在且非空 → 存在则跳过该配置（幂等设计）
- 后台进程使用 `background=true` + `notify_on_complete=true`，定期 `process(action="poll")` 检查进度

> **问题场景**：当数据中包含**两条方向完全不同的独立生物学过程**时（如去神经化路线 vs 应激→成熟路线），scTour 的**单伪时间轴会混淆两条路线**，导致伪时间失去生物学意义。
>
> **解决方案**：不要用一条 scTour 跑所有亚群。拆成多条独立路线，各自训练 scTour 模型。

### 何时触发

- 用户已做亚聚类，发现多个亚群存在**两种以上不同的生物学过程方向**
- scTour 的全数据运行时，Zone4（成熟度最高）和 NMJ（修复端点）被拉到同一伪时间末端
- 两条路线的基因信号在潜在空间上互相抵消
- 用户的核心问题是"谁转换谁"但 scTour 无法给出明确方向

### 混淆机制

当 scTour 的 VAE 同时看到两条路线时：

| 过程 | 伪时间方向 | 成熟度曲线 | 端点 |
|:----|:----------|:----------|:----|
| 路线A（损伤→恢复） | 非单调：先降再升 | ⬇Then⬆ | NMJ（高成熟） |
| 路线B（应激→成熟） | 单调上升 | ⬆ | Zone4（最高成熟） |

**VAE 行为**：把两个"高成熟端点"拉到同一伪时间轴末端 → 中间的低成熟细胞（如去神经化 Zone1）被两条线同时拉扯 → 伪时间失去生物学意义。

### 双路线工作流

```python
# ─── 路线A：去神经化→再神经支配路线 ───
route_a = adata[adata.obs['subcluster'].isin(
    ['Zone1', 'Zone2', 'NMJ', 'Zone5', 'Zone6']).copy()

# 预处理
sc.pp.calculate_qc_metrics(route_a, percent_top=None, log1p=False, inplace=True)
sc.pp.highly_variable_genes(route_a, flavor='seurat_v3', n_top_genes=1000, subset=True)

# 训练 scTour
tnode_a = sct.train.Trainer(route_a, loss_mode='nb', 
                             alpha_recon_lec=0.5, alpha_recon_lode=0.5)
tnode_a.train()
route_a.obs['ptime'] = tnode_a.get_time()

# 验证方向：用已知基因作为"锚点"
# 如果 COL19A1 高表达细胞在伪时间末端 → 方向正确

# ─── 路线B：应激→成熟发育路线 ───
route_b = adata[adata.obs['subcluster'].isin(
    ['Zone3', 'Zone4', 'Zone5']).copy()

# 预处理+训练（同上）
tnode_b = sct.train.Trainer(route_b, loss_mode='nb', ...)
tnode_b.train()
route_b.obs['ptime'] = tnode_b.get_time()
```

## 双路线验证策略

| 方法 | 验证内容 | 预期 |
|:----|:--------|:----|
| **分组统计** | 各亚群伪时间均值 | 路线A：Zone5/6→Zone1→Zone2→NMJ |
| **KS 检验** | 路线内亚群间分离度 | 所有相邻亚群间 p < 0.05 |
| **基因锚点法** | 用已知基因表达验证方向 | COL19A1 高表达细胞在伪时间末端 |
| **内部梯度** | Zone1 内部基因表达变化 | 底部MYH7→中部去神经→顶部COL19A1 |
| **🧭 年龄梯度锚点法** | 用 obs 中 age/condition 列的**年龄均值**作为伪时间方向的独立验证 | 伪时间低→高 应与 年龄低→高 一致（如果生物学过程是病理加重的方向时） |

### 🧭 年龄梯度锚点法（Age Gradient Anchoring）

> **🧭 条件锚点验证（Condition Anchoring）**：当数据包含多个实验条件/分组（如 Young_normal、Old_normal、Old_diabete、Old_diabete_Post）时，可以用**条件严重程度**作为伪时间方向的独立验证锚点。
>
> **原理**：如果伪时间低 = 病理状态重，则最恶劣条件下（如老年糖尿病运动后）的 Zone1 细胞应具有最低的伪时间均值。
>
> **实际验证流程**：
> ```python
> # 跑完 scTour 后，按条件分组统计伪时间
> for condition in ['Young_normal', 'Old_normal', 'Old_diabete', 'Old_diabete_Post']:
>     mask = result_df['type'] == condition
>     pt = result_df.loc[mask & (result_df['subcluster']=='zone1'), 'ptime']
>     print(f"{condition} Zone1: mean_ptime={pt.mean():.3f}")
> ```
>
> **实际案例（人类骨骼肌衰老，11,630 cells，2026-07-08 验证结果）**：
>
> | 条件 | Zone1 伪时间均值 | 解读 |
> |:----|:--------------:|:----:|
> | Young_normal | **0.684** | 年轻人 Zone1 最靠近健康端（伪时间高） |
> | Old_normal | **0.318** | 老年人 Zone1 进入去神经状态（伪时间降） |
> | Old_diabete | **0.393** | 糖尿病不运动，病理程度中 |
> | Old_diabete_Post | **0.163** ⚠️ 最低 | 糖尿病+运动，Zone1 伪时间最低 = **病理最重** |
> | 结论 | 条件严重度和伪时间完全负相关 | ✅ **病理加重方向得到验证** |
>
> 这种条件锚点法与年龄梯度锚点法**双交叉验证**，只要两条线指向同一方向，结果极可靠。

> **核心逻辑**：当数据包含**连续年龄段**（如年轻～老年）时，年龄可以作为伪时间方向的独立验证锚点。不依赖任何分子标记，纯靠样本元数据。

**原理**：
- 如果生物学过程是**病理加重**（变性、去神经化、衰老相关转变），伪时间从低到高的方向应与**年龄从低到高**一致
- 如果生物学过程是**再生/恢复**，伪时间方向应与年龄方向**相反或无关**

**使用场景**：
- 数据包含 `age` 列（数值型）或 `type/condition` 列（如 Young vs Old）
- 有明确的年龄/条件分组
- 存在两条以上可能的路线的方向混淆

**验证流程**：

```python
# 每条路线跑完 scTour 后，立即执行年龄梯度验证
from scipy.stats import spearmanr

stats = []
for zone in zone_order:
    mask = route.obs['subcluster'] == zone
    stats.append({
        'zone': zone,
        'mean_ptime': route.obs.loc[mask, 'ptime'].mean(),
        'mean_age': route.obs.loc[mask, 'age'].mean() if 'age' in route.obs.columns else \
            route.obs.loc[mask, 'type'].apply(lambda t: 70 if 'Old' in t else 25).mean(),
    })

rho, p_val = spearmanr([s['mean_ptime'] for s in stats], [s['mean_age'] for s in stats])
print(f"rho = {rho:.3f}, p = {p_val:.4f}")
```

**Zone1 内部验证**：如果 Zone1 底部（MYH7+）年龄显著低于 Zone1 顶部（COL19A1+），则支持"慢肌→去神经化"方向。

**实际案例（人类骨骼肌衰老，11,630 cells）—— 年龄梯度验证基准：**

| 亚群 | 平均年龄 | 平均伪时间 | 伪时间排名 | 年龄排名 |
|:----|:-------:|:---------:|:---------:|:-------:|
| Zone6（慢肌池） | 54.4岁 | 0.661 | 5（最高） | 1（最年轻） |
| Zone5（快肌池） | 57.3岁 | 0.670 | 6（最高） | 2 |
| **Zone1（去神经化）** | **72.0岁** | **0.223** | **1（最低）** | **6（最年长）** |
| Zone2（再神经支配） | 68.0岁 | 0.389 | 2 | 5 |
| NMJ | 58.7岁 | 0.429 | 3 | 3 |

**Spearman 相关**：`ρ = -0.943, p = 0.017`（强负相关，统计显著）
→ **伪时间越低 → 年龄越大 → 病理加重方向** ✅

**Zone1 内部年龄梯度**（进一步验证慢肌→去神经化方向）：
| Zone1 内部分层 | 平均伪时间 | 平均年龄 |
|:------------|:---------:|:--------:|
| 底部（MYH7+） | 伪时间高（~0.3-0.4） | 中年 |
| 中部（RUNX1+去神经） | 伪时间中（~0.15-0.25） | ~70+ |
| 上部（COL19A1+） | 伪时间低（~0.1） | ~75+ |
→ 年龄从底部到上部递增 → **慢肌→去神经化方向**(MYH7在Zone1底部高表达, 随伪时间降低减少; 去神经基因相反)

**年龄梯度锚点的绝对基准**：
- 如果 Spearman ρ 绝对值 > 0.8 且 p < 0.05 → **强验证**，方向可靠
- 如果 Spearman ρ 绝对值 0.3~0.8 → **中验证**，需结合其他锚点
- 如果 Spearman ρ 绝对值 < 0.3 → **弱/无验证**，可能是两条路线互相混淆的结果

### Zone1 内部梯度分析（Internal Gradient Analysis）

当双路线中包含一个"连续过渡"的亚群（如 Zone1 内部有 MYH7→去神经基因→COL19A1 的梯度）时，可以用 scTour 伪时间验证该亚群内部的连续过渡：

**原理**：利用 scTour 的伪时间对单个亚群内部排序，验证已知基因梯度是否沿伪时间单调变化。

**实现**：
```python
# 路线A 跑完 scTour 后，对 Zone1 内部做梯度分析
z1 = route_a[route_a.obs['subcluster'] == 'zone1'].copy()
z1_pt = z1.obs['ptime'].values

# 按伪时间三等分 Zone1
q = np.percentile(z1_pt, [33, 67])
z1.obs['z1_region'] = 'bottom'
z1.obs.loc[z1.obs['ptime'] >= q[0], 'z1_region'] = 'middle'
z1.obs.loc[z1.obs['ptime'] >= q[1], 'z1_region'] = 'top'

# 验证基因梯度：底部MYH7→中部RUNX1→顶部COL19A1
genes = ['MYH7', 'RUNX1', 'COL19A1']
for g in genes:
    for region, color in [('bottom','#4ECDC4'), ('middle','#FFA07A'), ('top','#FF6B6B')]:
        mask = z1.obs['z1_region'] == region
        expr = z1[mask, g].X.toarray().ravel() if hasattr(z1[mask,g].X, 'toarray') else z1[mask,g].X.ravel()
        print(f'{g}/{region}: mean={expr.mean():.3f}, pct={(expr>0).mean()*100:.0f}%')

# 基因表达沿伪时间散点图
fig, ax = plt.subplots(figsize=(10, 5))
for g in genes:
    expr = z1[:, g].X.toarray().ravel() if hasattr(z1[:,g].X, 'toarray') else z1[:,g].X.ravel()
    order = np.argsort(z1.obs['ptime'].values)
    ax.plot(z1.obs['ptime'].values[order], expr[order], '.', markersize=1, alpha=0.3, label=g)
ax.set_xlabel('Pseudotime (Zone1 only)')
ax.set_ylabel('Expression')
ax.legend()
```

**预期结果**：如果 Zone1 内部是慢肌→去神经化的连续过程，则伪时间从低到高，MYH7 表达递减、去神经基因表达递增、COL19A1 在末端出现。

### 年龄梯度锚点可视化（Age Gradient Anchoring Plot）

跑完 scTour 后，用双轴图同时展示伪时间均值和年龄均值，直观验证方向一致性：

```python
fig, ax1 = plt.subplots(figsize=(10, 6))
zones = ['zone6','zone5','zone1','zone2','NMJ']  # 按生物学方向排列
x = np.arange(len(zones))
mean_pt = [...], mean_ag = [...]  # 从 stats_df 提取

ax1.bar(x - 0.2, mean_pt, 0.35, label='Mean Pseudotime', color='#45B7D1', alpha=0.8)
ax1.set_ylabel('Mean Pseudotime', color='#45B7D1')
ax1.tick_params(axis='y', labelcolor='#45B7D1')

ax2 = ax1.twinx()
ax2.plot(x, mean_ag, 'o-', color='#FF6B6B', linewidth=2, markersize=8, label='Mean Age')
ax2.set_ylabel('Mean Age (years)', color='#FF6B6B')

ax1.set_xticks(x); ax1.set_xticklabels(zones)
ax1.set_title('Age Gradient Anchoring')
fig.tight_layout()
```

**Spearman 相关验证**：如果伪时间均值与年龄均值呈正相关，则支持"病理加重"方向。

双路线跑完后，必须对以下问题调用 `debate_analysis`：

1. **路线A 方向辩论**：伪时间方向是慢肌→去神经化（病理加重）还是去神经化→恢复慢肌（修复）？
2. **路线B 方向辩论**：Zone4 伪时间是否介于 Zone3 和 Zone5 之间（过渡态）？
3. **一致性检查**：两条路线的伪时间推断是否与已知生物学知识一致？

### 相关参考\n\n- 完整案例：`references/smf-subcluster-transition-analysis.md`（v2 修正版，包含 Zone1 内部梯度结构和双路线方法论）\n- 可复用脚本：`scripts/dual_route_sctour.py`（配置好 DATA 路径和亚群列表即可运行）\n
---

### 报告生成要求

使用脚本 `scripts/generate_full_report.py` 生成综合 HTML 报告，**必须包含以下全部内容**（2026-07-08 用户明确要求："把辩证结果、参数怎么来的、结论辩证全都写上去"）：

#### 报告必备 8 项清单
| # | 内容 | 检查标准 |
|:-:|:----|:--------|
| 1 | **分析流程** | 完整写出每一步的文字描述 |
| 2 | **参数来源表** | 每个关键参数：参数名、值、来源（知识库/技能模板/辩论轮次/官方默认）、选择依据 |
| 3 | **配置裁决表** | 多配置对比时展示量化指标（平均KS统计量、Delta均值、训练时间），标注胜出配置 |
| 4 | **所有图集** | 所有配置的所有 PNG（base64 嵌入），按配置分组展示 |
| 5 | **统计表** | 分组统计（均值/标准差/中位数）、亚群统计、KS检验表 |
| 6 | **辩论记录** | 每轮辩论完整呈现：辩题 + 正方论点×3（各自独立）+ 反方论点×4 + 裁判裁决（胜方+得分+决策+理由+行动） |
| 7 | **结论辩论** | 对最终生物学结论的独立辩论 → 裁决 → 限定后的结论 |
| 8 | **最终结论** | 经辩论验证的生物学结论，含辩论提醒/限定条件 |

#### 辩论样式模板
辩论在报告中用独立面板展示，正方/反方分列左右，下方展示裁决：
```html
<div class="debate-box">
  <h3>{步骤名称}</h3>
  <p>{时间戳}</p>
  <p><strong>辩题：</strong>{topic}</p>
  <div class="args">
    <div class="pro-side"><h4>✅ 正方（独立论证）</h4>{pro_args_html}</div>
    <div class="con-side"><h4>❌ 反方（独立论证）</h4>{con_args_html}</div>
  </div>
  <div class="verdict">
    <p><strong>胜方：</strong>{winner}（正方{X}分 vs 反方{Y}分）</p>
    <p><strong>决策：</strong>{decision}</p>
    <p><strong>理由：</strong>{reasoning}</p>
    <p><strong>行动：</strong>{action}</p>
  </div>
</div>
```

#### 辩论持久化（铁律）
- 每轮 `debate_analysis` 后，**立即**将辩论全记录写入 `results/.../log/debate_<序号>_<主题>.json`
- JSON 必须含：`id`、`step`、`timestamp`、`topic`、`pro_args`（各含role+argument）、`con_args`（各含role+argument）、`judge_verdict`（含winner/pro_score/con_score/decision/reasoning/action）
- 报告中辩论章节直接引用这些 JSON 的数据渲染

#### 报告生成脚本
- 封装为 `scripts/generate_full_report.py`，下次同类分析只需改路径和图片引用
- 内容包括：图片 base64 嵌入、辩论 JSON 读取、参数来源表生成、统计表渲染
- 参考 `references/report-content-checklist.md` 确保不遗漏

#### 文件命名与版本
- **完整版**（含辩论+参数来源+结论+自进化日志+全部图集）：`scTour_Complete_Report.html`（2026-07-08 最终用户接受的命名）
- **精简版**（仅图+统计）：保留原 `scTour_Trajectory_Report.html` 或 `scTour_Full_Report.html` 作为对照
- **原报告不覆盖**，多个版本并存
- 完整版与精简版同时交付，满足不同阅读需求

报告保存到 `results/.../03_advanced/scTour/`，**不保存到桌面**。
- **报告生成前必须先加载 `bioinformatics-html-report` skill**（`skill_view('bioinformatics-html-report')`），不可凭记忆手写 report builder 代码。
- 可复用模板：`templates/generate_html_report.py`（2026-07-08 人类骨骼肌 SMF 双路线分析验证通过），修改路径和解读文本即可使用。

#### 图片引入策略（2026-07-08 用户强制执行 — 不可违反）

**⚠️ 铁律：所有图片必须 base64 嵌入到 HTML 中，禁止使用路径引用。**

2026-07-08 会话教训：Agent 生成了一个 38KB 的报告（仅文字 + 路径引用的图片），用户立即质疑"怎么只有37kb?不审查吗？" → 被迫重写完整的 9.3MB 报告。用户要的是可双击直接看的报告，不是路径引用的轻量版。

```python
# ✅ 强制使用（写入 generate_full_report.py）
with open("figure.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")
html += f'<img src="data:image/png;base64,{b64}">'

# ❌ 禁止使用
<img src="file:///E:/.../figure.png">     # 路径引用 → 用户拒绝
<img src="figures/figure.png">             # 相对路径 → 本地打开空白
```

**后报告验证**：生成后必须检查图片是否真正 base64 嵌入（`content.count("data:image") >= 总图数`），文件大小应 > 1MB/图数 × 图数（每张嵌入图 ~500KB-2MB）。16 张图 + HTML 结构 ≈ 8-15MB 为正常。**小于 500KB 的报告意味着图片未嵌入。**

#### 后报告验证（Post-Generation Verification）

HTML 报告生成后，必须运行以下验证确保完整性：

```python
with open(report_path, encoding='utf-8') as f:
    html = f.read()
    
checks = {
    "结构": html.startswith("<!DOCTYPE html>") and "</html>" in html,
    "图片引用数≥15": html.count('<img') >= 15,
    "辩论段数≥5": html.count("辩论 #") >= 5,
    "裁判裁决≥5": html.count("⚖") >= 5,  # 含⚖️变体
    "自进化日志≥6": all(f"...{d:04d}" in html for d in range(6)),
    "参数来源表": "参数来源" in html or "tag-kb" in html,
    "图集章节": any(k in html for k in ["三配置训练结果", "平衡版深度分析"]),
    "最终结论": "最终结论" in html or "生物学结论" in html,
}
failed = [k for k, v in checks.items() if not v]
assert not failed, f"报告验证失败: {failed}"
print(f"✅ 报告验证通过 ({len(checks)}/{len(checks)})")
```

#### 报告必备 8 项清单（增强版）

| # | 内容 | 检查标准 |
|:-:|:----|:--------|
| 1 | **分析流程** | 完整写出每一步的文字描述 |
| 2 | **参数来源表** | 每个关键参数：参数名、值、来源（知识库/技能模板/辩论轮次/官方默认）、选择依据 |
| 3 | **配置裁决表** | 多配置对比时展示量化指标（平均KS统计量、Delta均值、训练时间），标注胜出配置 |
| 4 | **所有图集** | 所有配置的所有 PNG（按配置分组展示），包括：\
  - 每个配置的 overview UMAP（1张）+ vector field（1张）\
  - 平衡版额外图：最终UMAP总览、最终向量场、组间箱线图、亚群箱线图、运动效应图、衰老梯度图\
  - 三配置对比图：箱线图对比、KS热力图、Delta均值对比 |
| 5 | **统计表** | 分组统计（均值/标准差/中位数）、亚群统计、KS检验表 |
| 6 | **辩论记录** | 每轮辩论完整呈现：辩题 + 正方论点×3（各自独立）+ 反方论点×4 + 裁判裁决（胜方+得分+决策+理由+行动） |
| 7 | **结论辩论** | 对最终生物学结论的独立辩论 → 裁决 → 限定后的结论 |
| 8 | **自进化日志表** | 列出每一步的 `run_record_*.json`：脚本名、质量评分、关键经验 |

---

## 参数调优建议

### `alpha_recon_lec` 和 `alpha_recon_lode`（必须满足和为 1）

| 场景 | alpha_recon_lec | alpha_recon_lode | 效果 |
|------|:---:|:---:|------|
| 保留细胞类型差异 | 0.7-0.9 | 0.3-0.1 | 潜在空间更能区分细胞类型 |
| 强调伪时间排序 | 0.3-0.5 | 0.7-0.5 | 潜在空间更按伪时间排列 |
| 平衡（默认） | 0.5 | 0.5 | 默认推荐 |

### `alpha_z` 和 `alpha_predz`（get_latentsp 参数）

| 场景 | alpha_z | alpha_predz | 效果 |
|------|:---:|:---:|------|
| 保留内在结构 | 0.7-0.9 | 0.3-0.1 | 适合下游聚类 |
| 强调时间顺序 | 0.3-0.5 | 0.7-0.5 | 适合轨迹可视化 |
| 平衡（默认） | 0.5 | 0.5 | 默认推荐 |

### `loss_mode`

| 模式 | 输入要求 | 适用场景 |
|------|---------|---------|
| `'nb'` | 原始 UMI counts | 推荐，默认 |
| `'zinb'` | 原始 UMI counts | dropout 较多时 |
| `'mse'` | log1p 归一化表达 | 已归一化数据 |

---

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| `AttributeError: module 'sctour' has no attribute 'get_pseudotime'` | 使用了不存在的模块级函数 | scTour v1.0.0 的 API 全在 Trainer 方法上：`tnode.get_time()` / `tnode.get_latentsp()` / `tnode.get_vector_field(T, Z)`。`sct.get_pseudotime()` 等函数不存在！详见 `references/api-verification.md` |
| `ValueError: too many values to unpack` (get_latentsp) | 未解包 3-tuple | `get_latentsp()` 返回 `(mix_zs, zs, pred_zs)` 三元组，需 `mix_zs, zs, pred_zs = tnode.get_latentsp(...)` |
| `KeyError: 'n_genes_by_counts'` | 未计算 QC metrics | 先运行 `sc.pp.calculate_qc_metrics(adata, percent_top=None, log1p=False, inplace=True)` |
| `Invalid expression matrix` (loss_mode='nb') | `.X` 不是原始 UMI counts | 确保 `.X` 是整数 counts，或改用 `loss_mode='mse'` |
| `Invalid expression matrix` (loss_mode='mse') | `.X` 值域不对 | 确保 `.X` 是 log1p 归一化值，值域 [0, log1p(1e6)] |
| `alpha_recon_lec + alpha_recon_lode != 1` | 两个参数之和不为 1 | 调整参数使和为 1 |
| 伪时间方向反了 | ODE 积分方向随机 | 用 `reverse_time()` 反转 |
| `RuntimeError: mat1 and mat2 must have the same dtype, but got Double and Float` | AnnData 默认 float64（Double），PyTorch 模型用 float32（Float） | 训练前转换 dtype：`if issparse(adata.X): adata.X.data = adata.X.data.astype('float32') else: adata.X = adata.X.astype('float32')`。这是 PyTorch 经典问题，scTour 不会自动处理 |
| `ModuleNotFoundError: No module named 'skmisc'` 或 `ImportError: cannot import name 'loess'` | `flavor='seurat_v3'` 需要 `scikit-misc` 包，但未安装 | `pip install scikit-misc`。scTour 不会自动安装这个隐式依赖 |
| 训练极慢/不收敛/伪时间无意义 | **忘记选高变基因** | 全基因（>20000）直接喂 VAE → 训练慢 10× + 噪声淹没信号。必须先跑 `sc.pp.highly_variable_genes(adata, flavor='seurat_v3', n_top_genes=1000, subset=True)` |
| 训练很慢 | 数据量大且无 GPU（CPU 模式） | 减小 `percent` 参数，或 subsample 到 5000-10000 细胞；CPU 模式正常现象，不是错误 |
| 潜在空间不能区分细胞类型 | alpha_recon_lec 太小 | 增大 alpha_recon_lec（如 0.7-0.8） |
| 向量场不明显 | 数据噪声大 | 增加 `n_top_genes`，或调整 `stream_density` |
| 跨数据集预测失败 | 新数据基因不匹配 | 确保新数据使用相同的基因集 |
| scanpy/anndata 包版本冲突，`import scanpy` 报错 | 环境中的 anndata 与 scanpy 版本不兼容（如 `make_register_namespace_decorator` 签名不匹配），或 Windows 上 `D:\Python\site-packages` 在 sys.path 中优先级高于系统 site-packages 导致加载了错误 Python 版本的包 | **方案 A（最快）**：`PYTHONPATH="" python ...` — 清除 PYTHONPATH 后系统 Python 只加载自己的 site-packages，绕过冲突包。**方案 B**：用 h5py 直接读取 h5ad 元数据做预览（详见 `references/h5ad-data-access.md`）。**方案 C**：创建新的 conda/uv 虚拟环境重新安装兼容版本 |
| `AttributeError: 'SparseCSRView' object has no attribute 'A'` 或 `AttributeError: 'SparseCSRMatrixView' object has no attribute 'A'` | 新版 scipy（≥1.14）中 `SparseCSRView`/`SparseCSRMatrixView` 没有 `.A` 属性（即 `.toarray()`），但 scTour 的 `data.py:99` 调用了 `X.A` | 训练前将稀疏矩阵转为 dense numpy array：`if issparse(adata.X): adata.X = adata.X.toarray().astype('float32')`。11,630 细胞 × 1,000 基因 ≈ 46MB，内存无压力。**注意**：`.toarray()` 返回 dense 矩阵，适合 < 100,000 细胞的数据；更大数据需考虑子采样<br><br>**⚠️⚠️ 转换必须放在 `run_single_config` 函数内部，不能只放在顶层数据加载处。** 原因为：`sc.read()` 读取 h5ad 后 `.X` 是 `SparseCSRMatrixView` 类型；即使你在顶层转换了，`adata.copy()` 在函数内会保留原始矩阵类型。2026-07-08 会话教训：顶层转换正确，但 `run_single_config` 内用 `adata.copy()` 后仍报错，因为 copy 保留了 `.X` 的视图类型。修复方法：在训练代码附近直接转换，确保 Trainer 初始化时 `.X` 是 `float32` 的 dense 或常规 CSR 矩阵 |
| `IORegistryError: No method registered for writing <class 'pandas.arrays.StringArray'>` | anndata 0.10.9 + pandas 3.0.3 的 StringArray 写入 h5ad 不兼容 | 改用内存管道：不保存中间 h5ad，直接在内存中加载 → 预处理 → scTour 训练 → 可视化。或在保存前转换所有 string 列为 `object` dtype（但 pandas 3.0+ 的 `.values` 仍返回 StringArray，跳过中间 h5ad 更可靠） |
| `TypeError: Axes.boxplot() got an unexpected keyword argument 'labels'` | matplotlib ≥3.9 将 `labels` 参数重命名为 `tick_labels` | 使用 `tick_labels` 替代 `labels`：`ax.boxplot(data, tick_labels=labels)` |
| GPU 不可用但用户有 NVIDIA 显卡 | PyTorch 安装的是 CPU-only 版本（`torch 2.12.1+cpu`），或显卡架构太新（如 Blackwell sm_120）不被旧版 PyTorch 支持 | 检查：`python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"`。若为 CPU-only 且是 Blackwell 显卡，需安装 `torch>=2.8.0` 从 cu128 测试通道（见上方 GPU 策略） |
| `OSError: [Errno 28] No space left on device` 在安装 PyTorch cu128 时 | C: 盘空间不足（<10GB 可用），cu128 包 ~2.7GB 需要下载+解压的临时空间 | 设置临时目录到其他盘：`TMPDIR=/e/tmp TEMP=/e/tmp TMP=/e/tmp pip install "torch>=2.8.0" --index-url https://download.pytorch.org/whl/test/cu128 --force-reinstall --no-cache-dir`。常见于 Windows C 盘空间紧张的系统。 |
| `.X` 存储的是归一化值而非原始 UMI counts，但 `loss_mode='nb'` 要求整数 counts | 数据是已注释 Seurat 对象，SCTransform 归一化后 `.X` 存储的是 Pearson 残差而非 counts | **解决方案 A**：直接从 `.layers['counts']` 提取原始 counts（推荐）→ `adata.X = adata.layers['counts'].copy()`。**解决方案 B**：若 `adata.raw` 存在且 `.raw.X` 是 counts，复制 `adata.X = adata.raw.X.copy()`。**解决方案 C**：用 `loss_mode='mse'`（已归一化数据用 MSE 损失）。**验证方法**：`print(adata.X[:5, :5].toarray() if issparse(adata.X) else adata.X[:5, :5])` — 若为整数则为 counts |

---

## Proven Scripts

> 成功运行并通过审查的脚本记录。

| Species | Tissue | Condition | Date | Score | Notes |
|---------|--------|-----------|------|-------|-------|
| human | skeletal_muscle | aging_diabetes_exercise | 2026-07-07 | 9.0 | 3-config comparison (balanced/encoder/ODE), counts from layer, CPU mode |
| human | skeletal_muscle | aging (SMF subclusters dual-route) | 2026-07-09 | 9.0 | Dual-route scTour: Route A (Zone1/2/NMJ/5/6: denervation→reinnervation) + Route B (Zone3/4/5: stress→maturation). **All 3 configs completed for Route A** (run1_balanced won), **both configs completed for Route B** (run1_balanced won; run2_encoder failed due to Zone3≈Zone5 collapse). 200 epochs, CPU mode. Age gradient anchoring: ρ=-0.943 (p=0.017) for Route A. Condition anchoring: Old_diabete_Post Zone1 ptime=0.163 (lowest). Zone1 internal gradient validated: MYH7(bottom)→RUNX1(middle)→COL19A1(top). Zone5 dual-role discovery (healthy endpoint in both routes). Checkpoint resume strategy verified effective. Complete HTML report with 10 figures + 5 debates + 6 self-evolution logs. |

---

## 🚨 Agent 常见错误清单（每次加载此 skill 后必须逐条检查）

> **⚠️ 以下错误多次被 Agent 违反，导致用户纠正。每次加载此 skill 后，在写代码前逐条检查。** 这些错误不是"可能会犯"——它们是"之前已经犯过"的。

| # | 错误 | 用户纠正 | 正确做法 |
|:-:|:----|:--------|:--------|
| 1 | **写代码前不调 skill_view** | "你不触发skill吗？" | 每个分析步骤写代码前必须先调 `skill_view(name="sctour-trajectory-inference")` 加载完整 SKILL.md。即使你觉得会写，skill 里有最新参数模板和审查规则 |
| 2 | **生成 HTML 报告前不加载 bioinformatics-html-report skill** | "生成html，你触发html skill 了吗？" | 生成报告前必须调 `skill_view(name="bioinformatics-html-report")` 加载报告生成 skill。**不可凭记忆手写 report builder 代码** |
| 3 | **报告放桌面不询问用户** | "我说生成到桌面了吗？" | 报告保存到 `results/.../03_advanced/scTour/`，**不保存到桌面**。除非用户明确指定桌面路径。使用 `generate_report` 时必须指定 `output_path` |
| 4 | **报告不 base64 嵌入图片** | "怎么只有37kb?不审查吗？" | 所有图片必须 base64 嵌入到 HTML 中（`src="data:image/png;base64,..."`），**禁止使用路径引用**。报告文件应 > 1MB |
| 5 | **报告生成后不验证完整性** | 用户多次发现报告缺图 | 生成后运行后报告验证脚本，检查图片引用数、辩论段数、裁判裁决数、参数来源章节 |
| 6 | **报告细胞数时不区分原始 vs subset** | "不是一万多吗？" | 报告数据规模时必须区分：原始多少细胞、subset 后多少细胞、每个步骤实际用了多少细胞。**禁止只说"32万细胞跑scTour"——实际只跑了subset后的1万** |
| 7 | **跳过 search_knowledge 直接写代码** | （系统铁律） | 每个分析步骤必须先调 `search_knowledge(species, tissue, direction, "步骤名 参数")` 查知识库。知识库无匹配→搜文献→提取参数→写入知识库 |
| 8 | **一次性写完多个步骤的代码** | （系统铁律） | 写一步跑一步，禁止 `&&` 连接多步骤。每个步骤单独写脚本 → 执行 → 审查 → 辩论 → 下一步 |

### 为什么这些错误必须被记住

- 用户对**分析透明度**要求高：跳了哪些步骤、为什么跳、补了哪些，都要如实汇报，不粉饰
- 用户对**数值精度**要求高：说细胞数时必须确认是原始数据还是 subset 后的
- 用户期待**严格遵循 MemOmics 铁律**：关键词触发技能时必须立即加载 skill_view，8 步循环不可跳步
- 用户期待**脚本/Notebook 直接交付到对话中**，而不是只保存到 skill 目录

---

## 自进化日志 (.run_logs/ + results/log/)

> 日志以**双路径**存储。每次 `record_run`/`record_error` 后必须验证两个路径均有文件落盘（2026-07-08 会话教训：仅一路径有日志导致用户两次追问）。

| 路径 | 用途 | 验证命令 |
|:----|:----|:---------|
| `~/.hermes/skills/bioinformatics/sctour-trajectory-inference/.run_logs/` | 跨分析复用 | `ls ~/.hermes/skills/.../sctour-trajectory-inference/.run_logs/` |
| `results/.../scTour/log/run_record_*.json` | 本次分析追溯 | `ls results/.../scTour/log/run_record_*.json` |

> 文件名格式：`脚本名_物种_组织_方向_日期.log`（`.run_logs/`）或 `run_record_日期_序号_run.json`（`results/log/`）

---

## References

- Li, Q. (2023). scTour: a deep learning architecture for robust inference and accurate prediction of cellular dynamics. *Genome Biology*, 24, 149. [doi:10.1186/s13059-023-02988-9](https://doi.org/10.1186/s13059-023-02988-9)
- scTour 官方文档: https://sctour.readthedocs.io/
- scTour GitHub: https://github.com/LiQian-XC/sctour
- scTour PyPI: https://pypi.org/project/sctour/
- Blackwell GPU 设置: `references/blackwell-gpu-setup.md` — RTX 50 系列 CUDA 配置
- 多配置对比工作流（2026-07-07 第一次运行）: `references/multi-config-comparison-20260707.md` — 3 config comparison, run2_encoder won
- 多配置对比工作流（2026-07-08 第二次运行）: `references/multi-config-comparison-20260708.md` — 同一数据不同辩论标准, run1_balanced won
- SMF 亚群转换分析（骨骼肌衰老去神经/再神经支配路线）: `references/smf-subcluster-transition-analysis.md` — **v2（2026-07-08）** SMF亚聚类Zone1~Zone6+NMJ的生物学解读模型。**关键修正**：Zone1从MYH1+（快肌）→MYH7+（慢肌）。新增Zone1内部梯度结构（MYH7→去神经→COL19A1）、双路线独立scTour方法论（解决单轴混淆问题）、GALNTL6/FKBP5桥梁基因、Zone4超补偿假说。
- skill_evolution 静默失败修复: `references/skill-evolution-silent-failure.md` — 当 record_run 返回 Success 但不落盘时的排查和修复方法
- 报告内容清单（报告生成前必查）: `references/report-content-checklist.md` — 8项必备内容的详细检查标准
- 完整报告生成脚本: `scripts/generate_full_report.py` — 可复用的综合HTML报告生成器

---

## 🔒 审查机制（rail_review）

本 skill 执行代码前**必须**调用 `rail_review(phase="pre")` 进行前置审查，执行后**必须**调用 `rail_review(phase="post")` 进行后置审查。

### 审查内容
- **pre 审查**：环境检查（包是否安装）→ 参数校验（alpha_recon_lec+alpha_recon_lode=1？）→ 数据检查（n_genes_by_counts 存在？）→ **HVG 检查（高变基因是否已筛选？n_vars > 5000 且未 subset 则阻断）** → 硬件检查（GPU 可用则用 GPU，不可用则回退 CPU，不阻断）
- **post 审查**：结果质量评估（伪时间是否合理？）→ 图表检查（图是否生成？）→ 数值检查（潜在空间维度是否正确？）→ 错误检查（有无 warning/error）

### 审查不通过
- pre 不通过 → **阻断执行**，修正后重新审查
- post 不通过 → **阻断下一步**，修正后重跑，直到通过
- 失败时调用 `skill_evolution(action="record_error")` 记录错误
- 修复成功后调用 `skill_evolution(action="record_run")` 记录成功

---

## 🗣️ 辩论机制（debate_analysis）

当遇到**不确定的参数选择或结果判断**时，**必须**调用 `debate_analysis`：

- **正方 3 位专业编辑**（各自独立，互相看不到）：生物学编辑 / 统计学编辑 / 生信编辑
- **反方 4 位专业编辑**（各自独立，互相看不到，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
- **裁判编辑**：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
- **上下文隔离**：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
- **分科知识库**：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
- **辩论结果自动归档**到 results/.../log/debate_*.json

### 辩论触发场景
- `alpha_recon_lec` 选择（0.3 vs 0.5 vs 0.7）
- `alpha_z` 选择（偏向结构 vs 偏向时间）
- `loss_mode` 选择（nb vs zinb vs mse）
- `n_latent` 维度选择（3 vs 5 vs 10）
- 伪时间方向判断（是否需要反转？）
- 潜在空间质量评估（是否能区分细胞类型？）
- 向量场方向的生物学合理性---

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
