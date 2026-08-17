# GRNBoost2-Only 工作流（无需数据库下载）

> **创建日期**: 2026-07-09  
> **来源**: 人类骨骼肌衰老 SMF 亚群 SCENIC 分析前准备  
> **问题**: SCENIC 数据库（1.18GB + 2-3GB）下载速度仅 ~20KB/s，需 17+ 小时  
> **解决方案**: 跳过 cisTarget/AUCell，只跑 GRNBoost2（无需数据库）

## 触发场景

- 网络太慢无法下载 SCENIC 数据库（海外服务器，~20KB/s）
- 磁盘空间不足（C 盘 < 10GB 可用空间）
- 只需快速查看 TF-靶基因共表达关系
- 需要用表达数据直接推断 TF 调控网络，不依赖 motif 数据库

## 原理

SCENIC 三步骤中，只有 **cisTarget**（步骤2）需要 motif 排名数据库（.feather, ~1.18GB）和 motif 注释文件（.tbl, ~94MB）。**GRNBoost2**（步骤1）只需要表达矩阵本身。

跳过 cisTarget 和 AUCell，只跑 GRNBoost2 可以得到：
- **TF-靶基因共表达矩阵**（adjacencies）：哪些 TFs 和哪些基因在表达上相关
- 虽然没有 motif 水平的验证，但**共表达关系本身就有生物学意义**
- 结合 scTour 伪时间或 DEG 结果做交叉验证更可靠

## 完整工作流

```python
from arboreto import run_grnboost2
import scanpy as sc
import pandas as pd
import numpy as np

# 1. 加载数据并选高变基因
adata = sc.read("your_data.h5ad")
sc.pp.filter_genes(adata, min_cells=3)
sc.pp.highly_variable_genes(adata, n_top_genes=2000, subset=True)

# 2. 提取表达矩阵（cells × genes）
ex_matrix = pd.DataFrame(
    adata.X.toarray() if hasattr(adata.X, 'toarray') else adata.X,
    index=adata.obs_names,
    columns=adata.var_names
)

# 3. 加载 TF 列表
# 方法 A：从 SCENIC 资源下载（~89KB，小文件）
import urllib.request
url = "https://resources.aertslab.org/cistarget/tf_lists/allTFs_hg38.txt"
tf_list = urllib.request.urlopen(url).read().decode().splitlines()

# 方法 B：手动定义关键 TF（肌肉/衰老相关）
muscle_tfs = ['RUNX1', 'MYOD1', 'MYOG', 'MAF', 'MEF2A', 'MEF2C', 'MEF2D',
              'SRF', 'TEAD1', 'YAP1', 'KLF2', 'KLF4', 'KLF5', 'JUN', 'FOS',
              'NFKB1', 'RELA', 'STAT1', 'STAT3', 'SOX4', 'SOX6', 'ETS1',
              'EGR1', 'SP1', 'TP53', 'FOXO1', 'FOXO3', 'PAX3', 'PAX7',
              'TCF4', 'TCF12', 'HES1', 'HEY1', 'NOTCH1', 'RBPJ',
              'GATA4', 'GATA6', 'TWIST1']

# 只保留表达矩阵中存在的 TF
tf_list = [tf for tf in tf_list if tf in ex_matrix.columns]

# 4. 运行 GRNBoost2（核心步骤，不需要数据库！）
network = run_grnboost2(
    expression_data=ex_matrix,
    tf_names=tf_list,
    seed=42,
    verbose=True
)
# network 是 DataFrame：['TF', 'target', 'importance']
# importance > 0 表示正相关，< 0 表示负相关

# 5. 筛选高置信度互作
top_network = network[network['importance'] > 0.01].copy()
top_network = top_network.sort_values('importance', ascending=False)

# 6. 查看特定 TF 的靶基因
tf_targets = top_network[top_network['TF'] == 'RUNX1'].head(20)
print(f"RUNX1 靶基因 TOP 20:\n{tf_targets}")
```

## 结果解读

| 输出 | 含义 | 用途 |
|:----|:----|:----|
| `importance > 0.01` | 强正相关 | 该 TF 可能激活这些靶基因 |
| `importance < -0.01` | 强负相关 | 该 TF 可能抑制这些靶基因 |
| 多个 TF 共有相同靶基因 | 协同调控 | 这些 TF 可能形成调控复合体 |

## 结合 scTour 伪时间验证

```python
# 查看 TF 表达沿伪时间的变化
for tf in ['RUNX1', 'MYOD1', 'MAF']:
    if tf in adata.var_names:
        expr = adata[:, tf].X.toarray().ravel() if hasattr(adata.X, 'toarray') else adata[:, tf].X.ravel()
        order = np.argsort(adata.obs['ptime'].values)
        smoothed = pd.Series(expr[order]).rolling(50, min_periods=1).mean()
        plt.plot(adata.obs['ptime'].values[order], smoothed, label=tf, linewidth=2)
plt.xlabel('Pseudotime')
plt.ylabel('Expression (smoothed)')
plt.legend()
plt.title('TF expression along pseudotime')
```

## Top50 靶基因均值 TF 活性评分（cisTarget 失败时的替代方案）

当 cisTarget 因基因名不匹配跳过所有模块（`AssertionError: Signatures dataframe is empty!`），可用**靶基因均值**法从 GRNBoost2 adjacencies 直接计算细胞级 TF 活性：

```python
def compute_tf_activity(adjacencies_path, ex_matrix_path, n_top=50, min_targets=5):
    """对每个 TF 取 top50 靶基因均值作为 TF 活性评分"""
    adj = pd.read_csv(adjacencies_path)
    ex = pd.read_csv(ex_matrix_path, index_col=0)
    tf_activities = {}
    for tf_name, group in adj.groupby('TF'):
        group = group.sort_values('importance', ascending=False).head(n_top)
        valid = [t for t in group['target'] if t in ex.columns]
        if len(valid) >= min_targets:
            tf_activities[tf_name] = ex[valid].mean(axis=1)
    return pd.DataFrame(tf_activities)
```

**验证结果**（2026-07-09，人类骨骼肌衰老 SMF 数据，9,568 细胞，2000 HVG）：
- 产出 **121 个 TF 活性**
- RUNX1 排名 #5（验证通）
- ATF3（应激）排名 #1
- 完全替代了全空（25 个 0.0）的 AUCell 矩阵

**前置要求**：表达矩阵必须预过滤至仅包含 cisTarget 数据库中的基因（见 SKILL.md Common Issues）。

## 数据库下载替代方案

当标准 SCENIC 资源服务器太慢时，尝试以下方案：

| 方案 | 命令 | 说明 |
|:----|:-----|:-----|
| **后台下载** | `curl -L -o "file.feather" "URL" &`，用 `process(action="poll")` 轮询 | 不阻塞其他分析 |
| **仅下载 500bp 库** | 1.18GB，比 10kb 库（2-3GB）小，优先下载 | 够用 |
| **仅下载 motif 文件** | 94MB 的 .tbl 文件，配合 GRN 结果手动验证 | 快速替代 |
| **先跑 GRNBoost2** | 等数据库下载完再补 cisTarget+AUCell | 现在就能出结果 |

## 正确文件名（2026-07-09 验证）

```bash
# 500bp TSS 排名数据库（~1.18GB）
# URL: https://resources.aertslab.org/cistarget/databases/homo_sapiens/hg38/refseq_r80/mc9nr/gene_based/
# 文件名: hg38__refseq-r80__500bp_up_and_100bp_down_tss.mc9nr.genes_vs_motifs.rankings.feather
# 注意: 必须包含 .genes_vs_motifs.rankings. 后缀，不能只写 .feather

# 10kb TSS 排名数据库（~2-3GB）
# 文件名: hg38__refseq-r80__10kb_up_and_down_tss.mc9nr.genes_vs_motifs.rankings.feather

# Motif 注释文件（~94MB）
# URL: https://resources.aertslab.org/cistarget/motif2tf/
# 文件名: motifs-v10nr_clust-nr.hgnc-m0.001-o0.0.tbl

# TF 列表（~89KB）
# URL: https://resources.aertslab.org/cistarget/tf_lists/
# 文件名: allTFs_hg38.txt
```

## 何时使用 GRNBoost2-Only vs 完整 SCENIC

| 场景 | 推荐方案 | 理由 |
|:----|:---------|:-----|
| 网络慢，数据库下不了 | **GRNBoost2-Only** 🏆 | 现在就能跑，1-2 小时出结果 |
| 只想快速看主要 TF 趋势 | **GRNBoost2-Only** 🏆 | 足够回答"哪些 TF 可能调控 X 基因" |
| 需要发表级别的结果 | 完整 SCENIC | 需要 motif 验证才可信 |
| 需要细胞级别 TF 活性评分 | 完整 SCENIC（AUCell） | 只有 AUCell 能做 |
| 数据库已下载 | 完整 SCENIC 🏆 | 有数据库就是完整版更好 |