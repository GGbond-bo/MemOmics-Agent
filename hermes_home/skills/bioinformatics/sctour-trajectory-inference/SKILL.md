---
name: sctour-trajectory-inference
description: "scTour VAE 深度潜在时间推断 + 向量场 + 跨数据集预测。无需指定起点，无监督学习细胞动力学。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [trajectory, pseudotime, sctour, VAE, vector-field, latent-space, 03_高级分析]
    difficulty: advanced
    language: Python
    category: transcriptomics
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
- 需要 GPU 但没有 GPU → 训练会很慢（但 CPU 也能跑）

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
| **命令行脚本** | `scripts/run.py` → `run_sctour_inference.py` → `run_sctour_visualization.py` | Agent 自动化执行，8 步循环 + 审查 + 辩论 |
| **Jupyter Notebook** | `scripts/sctour_notebook.py` | 手动交互式探索，逐 Cell 运行，参数调优只需重跑 Cell 3 |

> **Notebook 版**：13 个 Cell（环境→加载→预处理→训练→伪时间→潜在空间→向量场→4 种可视化→保存→统计→调参参考），适合在 Jupyter 中逐步调试。训练 Cell 独立，改参数后只重跑它即可。

## Quick Start

**最快测试流程（~15-30分钟，取决于数据大小）：**

```python
# Step 1: 加载数据
import sctour as sct
import scanpy as sc

adata = sc.read("your_data.h5ad")

# Step 2: 预处理（必须计算 QC metrics + 选择高变基因）
sc.pp.calculate_qc_metrics(adata, percent_top=None, log1p=False, inplace=True)
sc.pp.highly_variable_genes(adata, flavor='seurat_v3', n_top_genes=2000, subset=True)

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

**快速安装：**
```bash
pip install sctour scanpy

# 或 conda
conda install -c conda-forge sctour scanpy
```

**GPU 支持（推荐）：**
- scTour 自动检测 GPU，如果有 CUDA 可用则自动使用
- 无需额外配置，`use_gpu=True`（默认）即可
- 如果不想用 GPU，设置 `use_gpu=False`

---

## Inputs

### 必需输入

1. **AnnData 对象**（.h5ad），包含：
   - `.X`：原始 UMI counts（`loss_mode='nb'` 或 `'zinb'`）或 log1p 归一化表达（`loss_mode='mse'`）
   - `.obs`：必须包含 `n_genes_by_counts`（通过 `scanpy.pp.calculate_qc_metrics` 计算）
   - 预处理：建议先跑 `scanpy.pp.highly_variable_genes` 选择 1000-2000 个高变基因

### 数据要求

- **最小细胞数**：500（推荐 1000+）
- **推荐高变基因数**：1000-2000
- **GPU**：推荐但非必需（CPU 也可以跑，但慢）
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
sc.pp.highly_variable_genes(adata, flavor='seurat_v3', n_top_genes=2000, subset=True)
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
    use_gpu=True,
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
| `use_gpu` | True | 是否使用 GPU |

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
| 训练很慢 | 数据量大且无 GPU | 减小 `percent` 参数，或 subsample 到 5000-10000 细胞 |
| 潜在空间不能区分细胞类型 | alpha_recon_lec 太小 | 增大 alpha_recon_lec（如 0.7-0.8） |
| 向量场不明显 | 数据噪声大 | 增加 `n_top_genes`，或调整 `stream_density` |
| 跨数据集预测失败 | 新数据基因不匹配 | 确保新数据使用相同的基因集 |

---

## Proven Scripts

> 成功运行并通过审查的脚本记录。

| Species | Tissue | Condition | Date | Score |
|---------|--------|-----------|------|-------|
| *(none yet)* | | | | |

---

## 自进化日志 (.run_logs/)

> 日志存储: skill 目录下 `.run_logs/` 目录，按 `脚本名_物种_组织_方向_日期.log` 命名

---

## References

- Li, Q. (2023). scTour: a deep learning architecture for robust inference and accurate prediction of cellular dynamics. *Genome Biology*, 24, 149. [doi:10.1186/s13059-023-02988-9](https://doi.org/10.1186/s13059-023-02988-9)
- scTour 官方文档: https://sctour.readthedocs.io/
- scTour GitHub: https://github.com/LiQian-XC/sctour
- scTour PyPI: https://pypi.org/project/sctour/

---

## 🔒 审查机制（rail_review）

本 skill 执行代码前**必须**调用 `rail_review(phase="pre")` 进行前置审查，执行后**必须**调用 `rail_review(phase="post")` 进行后置审查。

### 审查内容
- **pre 审查**：环境检查（包是否安装）→ 参数校验（alpha_recon_lec+alpha_recon_lode=1？）→ 数据检查（n_genes_by_counts 存在？）→ 硬件检查（GPU 是否可用）
- **post 审查**：结果质量评估（伪时间是否合理？）→ 图表检查（图是否生成？）→ 数值检查（潜在空间维度是否正确？）→ 错误检查（有无 warning/error）

### 审查不通过
- pre 不通过 → **阻断执行**，修正后重新审查
- post 不通过 → **阻断下一步**，修正后重跑，直到通过
- 失败时调用 `skill_evolution(action="record_error")` 记录错误
- 修复成功后调用 `skill_evolution(action="record_run")` 记录成功

---

## 🗣️ 辩论机制（debate_analysis）

当遇到**不确定的参数选择或结果判断**时，**必须**调用 `debate_analysis`：

- **正方 3 角色**（各自独立，互相看不到）：生物学 agent / 统计学 agent / 生信 agent
- **反方 4 角色**（各自独立，互相看不到，也看不到正方）：生物学 agent / 统计学 agent / 生信 agent / 历史经验 agent
- **裁判**：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）

### 辩论触发场景
- `alpha_recon_lec` 选择（0.3 vs 0.5 vs 0.7）
- `alpha_z` 选择（偏向结构 vs 偏向时间）
- `loss_mode` 选择（nb vs zinb vs mse）
- `n_latent` 维度选择（3 vs 5 vs 10）
- 伪时间方向判断（是否需要反转？）
- 潜在空间质量评估（是否能区分细胞类型？）
- 向量场方向的生物学合理性