# ptrepack MSYS Bash 路径与静默失败修复

## 问题 1: `ptrepack` 命令在 MSYS bash 中找不到

**症状**: `ptrepack: command not found` (exit 127)

**根因**: `ptrepack.exe` 位于 `Python312/Scripts/`，MSYS bash PATH 不含此目录。

**修复**: 使用完整路径：
```
/c/Users/USERNAME/AppData/Local/Programs/Python/Python312/Scripts/ptrepack
```

---

## 问题 2: `python -m tables.scripts.ptrepack` 静默失败

**症状**: exit code 0，无错误输出，但目标文件不存在。

**根因**: PyTables 的 ptrepack 模块在某些参数组合下静默跳过写入（不抛异常也不写文件）。

**检测**: `ls -lh <output>` 返回 "No such file or directory" 但命令 exit code = 0。

**修复**: 放弃 ptrepack CLI，改用 Python `tables` API 直接复制：
```python
import tables, os

filters = tables.Filters(complevel=5, complib='blosc:zstd')
with tables.open_file(src, 'r') as src_f:
    with tables.open_file(dst, 'w', filters=filters) as dst_f:
        for node in src_f.root._f_walknodes():
            src_f.copy_node(node._v_pathname, dst_f.root, recursive=True)

print(f'Done: {os.path.getsize(dst)} bytes')
```

已验证：2026-07-27，`4CL_SD_D4_2_scRNA`，186 MB 输出。

---

## 问题 3: MSYS bash 路径自动转换破坏 ptrepack 参数

**症状**: `FileNotFoundError: ``MEMOMICS_HOME\F`` does not exist`

**根因**: MSYS bash 将 `F:/path` 自动转换为 `MEMOMICS_HOME\F\path`（相对于工作目录）。

MSYS bash 也会把 `/f/path` 转为 `E:\f\path`。

**两种修复**:

### 方案 A（推荐）: 先 cd 到目标目录，再用相对路径
```bash
cd /f/PROJECT_DATA_DIR && python -c "..."
```

### 方案 B: Python 脚本中用原始 Windows 路径
```python
# 在 Python 字符串中，Windows 路径不被 bash 转换
src = r'PROJECT_DATA_DIR\cellbender_output\...'
```

---

## 综合最佳实践（LLM 使用）

```bash
# Step 1: cd 到工作目录（避免路径转换）
cd /f/PROJECT_DATA_DIR

# Step 2: 用 Python tables API 替代 ptrepack CLI
python -c "
import tables, os
filters = tables.Filters(complevel=5, complib='blosc:zstd')
with tables.open_file('cellbender_output/SAMPLE/cellbender_output_filtered.h5', 'r') as src:
    with tables.open_file('seurat_h5/SAMPLE_filtered_seurat.h5', 'w', filters=filters) as dst:
        for node in src.root._f_walknodes():
            src.copy_node(node._v_pathname, dst.root, recursive=True)
print(f'Done: {os.path.getsize(\"seurat_h5/SAMPLE_filtered_seurat.h5\")} bytes')
"

# Step 3: 验证
ls -lh seurat_h5/SAMPLE_filtered_seurat.h5
```
