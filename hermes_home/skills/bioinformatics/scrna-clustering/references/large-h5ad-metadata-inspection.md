# 大型 h5ad 文件低内存元数据读取

> 适用场景：h5ad 文件 >5GB，anndata.read_h5ad(backed='r') 因内存不足崩溃（返回 exit code 3221225794 或 OOM）

## 原理

Anndata 使用 HDF5 格式存储，底层是 h5py。对于大文件，直接访问 h5py 的 `obs` Group 可以绕开 anndata 的内存分配，只读元数据。

## 关键数据结构

```
f = h5py.File("path.h5ad", "r")
obs = f["obs"]
```

### 1. 分类变量（Categorical）— 对应 h5py Group

```python
# Sample column: "celltype", "age", "donor_id", etc.
g = obs["sample_id"]  # This is an h5py.Group, NOT a Dataset

# Has two sub-datasets:
codes = g["codes"][:]       # numpy array of int codes
categories = g["categories"][:]  # numpy array of strings (bytes)

# Decode categories:
cats = [x.decode("utf-8") if isinstance(x, bytes) else str(x) for x in categories]

# Count occurrences without loading ALL codes at once:
from collections import Counter
c = Counter()
for i, cat in enumerate(cats):
    count = int(np.sum(codes == i))
    c[cat] = count
```

### 2. 数值变量 — 直接是 Dataset

```python
# Direct Dataset, no Group wrapper
n_genes = obs["n_genes_by_counts"][:]  # Full array
# For 300K+ cells, use sampling:
sample_idx = np.random.choice(n, min(10000, n), replace=False)
vals = obs["n_genes_by_counts"][sample_idx]
```

### 3. 布尔/小分类 — 也是 Dataset 或 Group

```python
# "predicted_doublet" could be either — check type
if isinstance(obs["predicted_doublet"], h5py.Group):
    codes = obs["predicted_doublet"]["codes"][:]
    cats = [x.decode("utf-8") for x in obs["predicted_doublet"]["categories"][:]]
else:
    # It's a Dataset — values are int64/float64
    vals = obs["predicted_doublet"][:]
```

## 识别变量类型的方法

```python
for key in obs:
    obj = obs[key]
    if isinstance(obj, h5py.Group):
        print(f"{key}: CATEGORICAL (Group)")
    elif isinstance(obj, h5py.Dataset):
        print(f"{key}: NUMERICAL/BOOLEAN (Dataset)")
    else:
        print(f"{key}: UNKNOWN")
```

## 分类变量的 attrs 信息

```python
# attrs tell you how anndata encoded the column
print(g.attrs)
# e.g. {'encoding-type': 'categorical', 'encoding-version': '0.2.0'}
```

## 实用：快速样本分组统计

```python
def count_categories(obs_group, column_name, top_n=30):
    """Return counts of a categorical column without loading all obs"""
    g = obs_group[column_name]
    codes = g["codes"][:]
    cats = [x.decode("utf-8") for x in g["categories"][:]]
    from collections import Counter
    c = Counter()
    for i, cat in enumerate(cats):
        c[cat] = int(np.sum(codes == i))
    return dict(c.most_common(top_n))
```

## 常见坑

| 问题 | 说明 |
|------|------|
| `h5py.Group` vs `h5py.Dataset` | 大部分 obs 列是 Group（分类），少数是 Dataset（数值）。不能统一调用 `.shape` |
| 字节码解码 | h5py 读出的字符串是 bytes，需要 `.decode('utf-8')` |
| attr 中的 `__categories` | 有些 h5ad 存储在 attrs 而非独立的 `categories` dataset 中 |
| X 矩阵 | `f["X"]` 可能是 Group（稀疏矩阵）或 Dataset（稠密），不要假定格式 |
