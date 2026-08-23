---
name: error-recovery
description: "分析报错后自动诊断根因并尝试修复。覆盖常见生信错误: 包缺失/版本不匹配/内存不足/数据类型转换/参数错误/文件路径。每次修复记录到 skill_evolution，累积修复经验。"
when_to_use: "[error-recovery] 当终端运行脚本报错，或用户说'报错了'/'error'/'出错了'/'怎么修'/'这什么错'时触发"
version: 1.0.0
category: General Utility
hermes:
  tags: [error, recovery, troubleshooting, debugging, fix]
  trigger_level: RED
  keywords: "error / 报错 / 出错 / 修复 / 怎么修 / fix / debug"
---

# 🔧 Error Recovery — 生信分析错误自动诊断与修复

> 分析失败时自动触发：读取错误 → 诊断根因 → 尝试修复 → 记录经验

---

## ⛔ MemOmics 强制规则

1. **先读错误再修复**：必须先读取完整终端输出，不能猜测
2. **查历史经验**：`skill_evolution(action="query_logs", skill_name="<当前skill>")` 查同类错误
3. **一次修一个**：每次只修一个错误，修完→跑→确认通过再继续
4. **记录所有修复**：修成功 → `record_run`，修失败 → `record_error`
5. **3 次上限**：同一错误尝试 3 次后仍失败 → 停止并告诉用户

---

## 错误分类决策树

```
终端报错
  ├─ ModuleNotFoundError / 包不存在
  │   → Step A: 包安装修复
  ├─ MemoryError / killed / OOM
  │   → Step B: 内存优化
  ├─ TypeError / class conversion / dgCMatrix
  │   → Step C: 数据类型转换修复  
  ├─ FileNotFoundError / No such file
  │   → Step D: 文件路径修复
  ├─ 参数错误 / argument error
  │   → Step E: 参数修正
  └─ 其他
      → Step F: 查官方文档 + 社区
```

---

## Step A: 包安装修复

### 诊断
```
错误: ModuleNotFoundError: No module named 'xxx'
错误: there is no package called 'xxx'
```

### 修复流程
1. 检查环境: `check_env(packages=["xxx"])`
2. 安装: Python → `pip install xxx`，R → `install.packages("xxx")` 或 `BiocManager::install("xxx")`
3. Bioconductor 包 → 先确认 BiocManager 已安装
4. 版本冲突 → 检查已安装版本，必要时 `pip install xxx==版本号`
5. 修复后: 重启 kernel/重新 import

### 常见坑
- **harmonypy ≠ harmony**: Python 版是 `harmonypy`，R 版是 `harmony`
- **anndata**: `pip install anndata`（不是 anndata2）
- **Seurat v5**: 需要 R >= 4.1，依赖 `SeuratObject`, ` Matrix`
- **scTour**: 需要 PyTorch ≥ 1.10，建议 `pip install sctour --no-deps` 后手动补 torch

---

## Step B: 内存优化

### 诊断
```
错误: MemoryError / Cannot allocate vector of size X Gb
错误: std::bad_alloc / killed (OOM)
```

### 修复流程
1. 检查数据规模: `print(object.size(x))` (R) / `data.nbytes / 1e9` (Python)
2. 子采样: 随机取 20-50% 细胞（保留所有基因）
3. 稀疏矩阵: 确保用 `dgCMatrix` (R) / `scipy.sparse.csr_matrix` (Python)
4. 高变基因筛选: 只分析 top 2000-5000 HVG
5. 清理中间变量: `rm()` / `del` + `gc()` / `gc.collect()`
6. 分批处理: 按 sample/cluster 分批跑

### 基准
| 细胞数 | 内存需求 (R) | 内存需求 (Python) |
|--------|-------------|-------------------|
| 10K | 2-4 GB | 1-2 GB |
| 50K | 8-16 GB | 4-8 GB |
| 150K | 32-64 GB | 16-32 GB |
| 500K+ | >128 GB (考虑分批) | >64 GB |

---

## Step C: 数据类型转换

### 诊断
```
错误: cannot coerce class "dgCMatrix" to a data.frame
错误: TypeError: 'AnnData' object is not subscriptable
错误: 参数不是数值型向量
```

### 修复流程

| 错误 | R 修复 | Python 修复 |
|------|--------|-------------|
| dgCMatrix → data.frame | `as.matrix()` 先转，或直接用矩阵操作 | `X.toarray()` 或 `pd.DataFrame(X.todense())` |
| AnnData subscript | — | `adata.X` / `adata.raw.X` / `adata.layers['counts']` |
| Factor → numeric | `as.numeric(as.character(x))` | `pd.to_numeric()` |
| 稀疏→稠密太大 | 不改格式，用稀疏原生操作 | 不改格式，用 scipy.sparse 操作 |
| counts vs logcounts | 检查 `GetAssayData(..., slot="counts")` | 检查 `adata.raw.X` / `adata.layers` |

### 关键检查清单
- [ ] Seurat: `GetAssayData(..., slot="counts")` vs `slot="data"`
- [ ] scanpy: `adata.X` vs `adata.raw.X` vs `adata.layers['counts']`
- [ ] 稀疏矩阵不能直接转 data.frame → 先 `as.matrix()`
- [ ] R 中 factor 不能直接转数字 → 先 `as.character()`

---

## Step D: 文件路径修复

### 诊断
```
错误: FileNotFoundError / No such file or directory
错误: 无法打开文件
```

### 修复流程
1. 检查路径: `file.exists()` (R) / `os.path.exists()` (Python)
2. 自动搜索: `glob.glob("**/*.h5ad", recursive=True)` / `list.files(recursive=TRUE, pattern="\\.h5ad$")`
3. 常见问题: 相对路径 vs 绝对路径，Windows `\` vs `/`
4. 返回找到的文件列表给用户确认

---

## Step E: 参数修正

### 诊断
```
错误: unused argument / unexpected keyword argument
错误: 参数长度不一致
```

### 修复流程
1. 读 skill 文档: 检查 `skill.json` 中 `proven_params` 的正确参数
2. 读函数签名: `?function` (R) / `help(function)` (Python)
3. 对比调用参数 vs 实际签名，修正差异

---

## Step F: 未知错误

1. 完整复制错误信息
2. `search_knowledge(错误关键词)` 查知识库
3. 如果 skill 有官网链接 → `web_extract(官方文档/FAQ页面)`
4. 仍无法解决 → 整理完整诊断报告给用户

---

## 修复后必须做的事

```
修复成功:
  → skill_evolution(action="record_run", ...)
  → fact_store(action="add", category="skill_exp", ...)

修复失败 (3 次):
  → skill_evolution(action="record_error", ...)
  → 告诉用户: "该错误需要人工介入，这里是诊断报告: ..."
```

## 修复经验速查表 (Community Fixes)

> 每次成功修复后，将 fix 添加到下方表格。

| 错误特征 | 根因 | 修复 | 日期 |
|----------|------|------|------|
| `dgCMatrix to data.frame` | Seurat v5 返回稀疏矩阵 | `as.matrix(GetAssayData(obj, layer="counts"))` | — |
| `SCTransform memory` | 150K+ cells | `SCTransform(..., conserve.memory=TRUE, return.only.var.genes=FALSE)` | — |
| `harmony not found` | Python 装了 harmony 而非 harmonypy | `pip uninstall harmony && pip install harmonypy` | — |
| `anndata.read_h5ad OOM` | 500K cells | `anndata.read_h5ad(path, backed='r')` | — |
