# h5ad 数据读取技术 — 无 scanpy/anndata 时的 Fallback

> 场景：scanpy 或 anndata 包缺失/版本冲突/崩溃（如 segmentation fault 或 `make_register_namespace_decorator` 签名不匹配）时，用 h5py 直接读取 h5ad 的元数据和表达矩阵。

## 先试最简单修复：PYTHONPATH=""

Windows 上经常有多个 Python 安装，D:\Python\site-packages 如果排在 sys.path 前面，会加载错误 Python 版本的包。**最快修复：**

```bash
PYTHONPATH="" python -c "import scanpy; print(scanpy.__version__)"
```

如果这能解决，后续所有 Python 调用前面加 `PYTHONPATH=""` 即可。不行再走 h5py fallback。

诊断命令：
```bash
python -c "import sys; print('\n'.join(sys.path))"
# 如果 D:\Python\site-packages 出现在 C:\...\Python312\Lib\site-packages 之前，这就是问题
```

## 技术原理

h5ad 文件本质上是 HDF5 格式，包含以下顶层 groups：
- `X` — 表达矩阵（CSR/CSC 稀疏格式或稠密矩阵）
- `obs` — 细胞元数据（DataFrame）
- `var` — 基因元数据（DataFrame）
- `obsm` — 细胞多维嵌入（UMAP/PCA/tSNE 等）
- `obsp` — 细胞-细胞邻接矩阵
- `uns` — 非结构化元数据
- `layers` — 额外表达层（如 counts）
- `varm` — 基因多维嵌入
- `varp` — 基因-基因邻接矩阵

## 关键技巧：分类变量（Categorical）的读取

**h5ad 中分类变量（如 `celltype`、`type`、`samplename`）不是以 Dataset 存储，而是以 Group 存储**，内含两个 Dataset：

```
obs/type/           ← Group，不是 Dataset
  ├── categories/   ← Dataset: 唯一类别值列表（字符串）
  └── codes/        ← Dataset: 每个细胞对应的类别索引（整数）
```

### 通用读取函数

```python
import h5py
import numpy as np
from collections import Counter

def read_obs_col(obs_group, name):
    """从 h5ad 的 obs group 读取列，自动处理分类/数值列"""
    col = obs_group[name]
    if isinstance(col, h5py.Group):
        # 分类变量：categories + codes
        cats = [c.decode('utf-8') if isinstance(c, bytes) else str(c) 
                for c in col['categories'][:]]
        codes = col['codes'][:]
        return [cats[c] for c in codes]
    elif isinstance(col, h5py.Dataset):
        # 数值/字符串列
        vals = col[:]
        if vals.dtype.kind == 'S':  # bytes
            return [v.decode('utf-8') if isinstance(v, bytes) else str(v) 
                    for v in vals]
        elif vals.dtype.kind in ('i', 'f'):  # int/float
            return vals   # 保持原始数值类型
        else:
            return [str(v) for v in vals]
    return []
```

### 示例：扫描 h5ad 数据概况

```python
import h5py
import numpy as np
from collections import Counter

f = h5py.File('your_data.h5ad', 'r')

# 1. 查看所有顶层 keys
print('Keys:', list(f.keys()))

# 2. 查看 obs 列名
obs_cols = list(f['obs'].keys())
print(f'Obs columns ({len(obs_cols)}): {obs_cols}')

# 3. 判断每列是 Group（分类）还是 Dataset（数值/索引）
for col_name in obs_cols:
    col = f['obs'][col_name]
    if isinstance(col, h5py.Group):
        print(f'  {col_name}: CATEGORICAL (categories={col["categories"][:5]})')
    elif isinstance(col, h5py.Dataset):
        print(f'  {col_name}: Dataset, dtype={col.dtype}, shape={col.shape}')

# 4. 读取分类变量
type_vals = read_obs_col(f['obs'], 'type')
print('Type counts:', Counter(type_vals))

# 5. 读取数值列（如 QC metrics — 整数列）
n_counts = f['obs']['nCount_RNA'][:]
print(f'nCount_RNA: min={n_counts.min()}, max={n_counts.max()}, mean={n_counts.mean():.1f}')

# 6. 获取 X 矩阵形状
if 'X' in f:
    X = f['X']
    if hasattr(X, 'shape'):
        shape = X.shape
    elif 'shape' in X.attrs:
        shape = X.attrs['shape']
    print(f'X shape: {shape}')

# 7. 读取 var 基因名
if '_index' in f['var']:
    genes = f['var']['_index'][:]
    if genes.dtype.kind == 'S':
        genes_decoded = [g.decode('utf-8') for g in genes]
    print(f'Genes: {len(genes_decoded)}, first 5: {genes_decoded[:5]}')

# 8. 读取 obsm 嵌入
for k in f['obsm']:
    if hasattr(f['obsm'][k], 'shape'):
        print(f'obsm/{k}: {f["obsm"][k].shape}')

f.close()
```

## 读取稀疏矩阵 X

如果 `.X` 是 CSR 格式：

```python
def read_sparse_matrix(group, key='X'):
    """从 h5ad 的 HDF5 group 读取稀疏矩阵"""
    try:
        X_group = group[key]
        # CSR format
        if 'data' in X_group and 'indices' in X_group and 'indptr' in X_group:
            from scipy.sparse import csr_matrix
            data = X_group['data'][:]
            indices = X_group['indices'][:]
            indptr = X_group['indptr'][:]
            shape = X_group.attrs.get('shape', None) or X_group.attrs['h5sparse_shape']
            return csr_matrix((data, indices, indptr), shape=tuple(shape))
    except Exception as e:
        print(f"Could not read {key}: {e}")
    return None
```

## 读取 layers（如 counts layer）

`layers` 下的稀疏矩阵结构与 `X` 相同 — 每个 layer 条目也是一个 Group 含 data/indices/indptr：

```
layers/
  └── counts/           ← Group（CSR 稀疏矩阵）
        ├── data/       ← Dataset: 非零值（int64/float32）
        ├── indices/    ← Dataset: 列索引（int32）
        └── indptr/     ← Dataset: 行指针（int32）
```

读取方式与 `X` 完全相同：

```python
if 'layers' in f:
    for layer_name in f['layers']:
        layer = f['layers'][layer_name]
        if isinstance(layer, h5py.Group) and 'data' in layer:
            n_nonzero = len(layer['data'])
            print(f'layers/{layer_name}: {n_nonzero} non-zero entries, '
                  f'dtype={layer["data"].dtype}')
            # 用 read_sparse_matrix(f['layers'], 'counts') 读取完整矩阵
```

## 读取 uns（非结构化数据）

```python
if 'uns' in f:
    print('uns keys:', list(f['uns'].keys()))
    for k in f['uns'].keys():
        d = f['uns'][k]
        if isinstance(d, h5py.Dataset) and hasattr(d, 'shape'):
            try:
                if d.dtype.kind == 'O':  # object/string
                    vals = [x.decode() if isinstance(x, bytes) else str(x) for x in d[:]]
                    print(f'  {k}: {vals}')
                elif d.dtype.kind in ('i', 'f') and d.shape[0] < 50:
                    print(f'  {k}: {d[:].tolist()}')
            except:
                pass
```

## 常见 h5ad HDF5 结构模式

| 数据类型 | h5py 类型 | 读取方式 |
|---------|-----------|---------|
| 分类变量 (Categorical) | `Group` (有 categories+codes) | `read_obs_col()` |
| 数值/字符串列 | `Dataset` | `dataset[:]` |
| 索引列 (_index) | `Dataset` | `dataset[:]` |
| CSR 稀疏矩阵 (X) | `Group` (data+indices+indptr) | `read_sparse_matrix()` |
| CSR 稀疏矩阵 (layers) | `Group` (data+indices+indptr) | `read_sparse_matrix(f['layers'], 'counts')` |
| 稠密矩阵 | `Dataset` | `dataset[:]` |
| 浮点嵌入 (UMAP/PCA) | `Dataset` | `dataset[:]` |
| 字符串数组 (uns) | `Dataset` (dtype=O 或 S) | `d.asstr()[:]` 或 decode |

## 使用场景

1. **scanpy 环境出问题时**：快速读取 h5ad 的元数据做数据预览
2. **超大文件预览**：只读 obs 和 var 列，不加载 X 矩阵，速度快、内存低
3. **跨语言互操作**：从 Python 用 h5py 读取后，确认数据结构再决定分析路径
4. **数据完整性检查**：在正式分析前确认 obs/var 列名、分类变量取值、嵌入维度
5. **SCTransform 后 Seurat 转换的 h5ad**：X 存储 Pearson 残差（非整数），counts 在 layers['counts'] 中（整数、CSR 稀疏格式），适合 scTour 的 loss_mode='nb'