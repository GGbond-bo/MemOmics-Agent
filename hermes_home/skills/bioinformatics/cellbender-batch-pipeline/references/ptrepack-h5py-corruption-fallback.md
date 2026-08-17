# ptrepack HDF5 Checksum 损坏 — h5py 绕过方案

## 触发条件

ptrepack CLI 报以下任一错误：

```
tables.exceptions.HDF5ExtError: HDF5 error back trace
  ...
  incorrect metadata checksum after all read attempts
  bad object header version number
```

## 根因

HDF5 底层库检测到文件的 metadata checksum 不匹配，`tables` (PyTables) 拒绝打开文件。但 Python `h5py` 使用不同的 HDF5 驱动层，通常能正常读取同一个文件。

## 症状

- `ptrepack` 或 `tables.open_file()` 报 `HDF5ExtError`
- 但 `h5py.File(path, 'r')` 可以正常打开
- `cellbender_output_filtered.h5` 在 CellBender 训练中正常生成（100+ MB），只是 ptrepack 写目标时触发源文件 checksum 错误

## 已验证案例

2026-07-27: `PROJECT_DATA_DIR/cellbender_output/4CL_SD_D5_1_scRNA/cellbender_output_filtered.h5` (107 MB)
- ptrepack CLI → `HDF5ExtError: incorrect metadata checksum`
- h5py → 正常读取 `/matrix` group → 成功复制到 `seurat_h5/` (557 MB)

## 修复脚本

```python
import h5py, os

def h5py_copy_matrix(src_path, dst_path, complevel=5):
    """用 h5py 复制 /matrix group（绕过 ptrepack HDF5 checksum 问题）"""
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    
    with h5py.File(src_path, 'r') as src:
        with h5py.File(dst_path, 'w') as dst:
            def copy_group(src_g, dst_g):
                for k, v in src_g.items():
                    if isinstance(v, h5py.Group):
                        g = dst_g.create_group(k)
                        copy_group(v, g)
                    elif isinstance(v, h5py.Dataset):
                        dst_g.create_dataset(
                            k, data=v[:],
                            compression='gzip',
                            compression_opts=complevel
                        )
            copy_group(src['matrix'], dst.create_group('matrix'))
    
    return os.path.getsize(dst_path)
```

## 批量应用

```python
import os

cb_dir = r'PROJECT_DATA_DIR\cellbender_output'
out_dir = r'PROJECT_DATA_DIR\seurat_h5'

for sname in os.listdir(cb_dir):
    in_file = os.path.join(cb_dir, sname, 'cellbender_output_filtered.h5')
    out_file = os.path.join(out_dir, f'{sname}_filtered_seurat.h5')
    
    if not os.path.exists(in_file):
        continue
    if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
        continue  # skip existing
    
    try:
        h5py_copy_matrix(in_file, out_file)
        print(f'OK: {sname} ({os.path.getsize(out_file)/1e6:.1f} MB)')
    except Exception as e:
        print(f'FAIL: {sname} — {e}')
```

## 与 ptrepack CLI 对比

| 方法 | 优点 | 缺点 |
|------|------|------|
| ptrepack CLI | 原生 HDF5 压缩优化 | MSYS 路径转换、checksum 敏感 |
| h5py copy | 绕过 checksum 问题、无 MSYS 陷阱 | 无底层压缩优化，文件可能略大 |

## 何时用 h5py

- ptrepack CLI 连续失败 2+ 次
- 错误信息包含 "metadata checksum" 或 "bad object header"
- h5py 能正常打开源文件
