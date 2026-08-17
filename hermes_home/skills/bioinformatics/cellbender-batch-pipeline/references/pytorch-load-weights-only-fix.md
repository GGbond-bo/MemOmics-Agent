# PyTorch torch.load weights_only 修复

## 问题

PyTorch 2.6+ 将 `torch.load()` 的默认参数从 `weights_only=False` 改为 `weights_only=True`。这导致 CellBender checkpoint 加载失败，因为 CellBender 使用了自定义 Pyro 模型类（`RemoveBackgroundPyroModel`），不在 PyTorch 的安全白名单中。

### 错误症状

```
Successfully unpacked tarball to C:\Users\...\Temp\tmpXXXXXXXX
C:\Users\...\Temp\tmpXXXXXXXX\...\model.torch
...
_pickle.UnpicklingError: Weights only load failed. This file can still be loaded...
    (1) Re-running `torch.load` with `weights_only` set to `False` will likely succeed...
    (2) WeightsUnpickler error: Unsupported global: GLOBAL cellbender.remove_background.model.RemoveBackgroundPyroModel
```

关键线索：`Successfully unpacked tarball` → `UnpicklingError`。ckpt 解压成功，是 `torch.load` 拒绝了模型类。

## 修复方案 A：sitecustomize.py monkey-patch（推荐）

在 `C:\Users\USERNAME\AppData\Local\Programs\Python\Python312\Lib\site-packages\sitecustomize.py` 中：

```python
try:
    import dill
    import torch
    _orig_save = torch.save

    # ... (keep existing torch.save weakref patch) ...

    torch.save = _patched_save

    # === 新增：torch.load weights_only=False ===
    _orig_load = torch.load

    def _patched_load(f, map_location=None, pickle_module=None, *,
                      weights_only=False, mmap=None, **kwargs):
        return _orig_load(f, map_location=map_location,
                          pickle_module=pickle_module,
                          weights_only=weights_only,
                          mmap=mmap, **kwargs)

    torch.load = _patched_load
    print("[sitecustomize] torch.save patched v4 + torch.load weights_only=False default", flush=True)
except ImportError:
    pass
```

### 优点
- 一处修改，覆盖所有 PyTorch 调用者（CellBender + 所有其他工具）
- 不修改 CellBender 源码，CellBender 更新后仍有效
- 已验证于 2026-07-26（`4CL_SD_D4_2_scRNA` 成功启动训练）

### 验证
```bash
python -c "import torch; print('sitecustomize loaded, torch.load patched')"
# 应输出: [sitecustomize] torch.save patched v4 + torch.load weights_only=False default
```

## 修复方案 B：直接修改 CellBender checkpoint.py（后备）

编辑 `cellbender/remove_background/checkpoint.py`，找到 `load_from_checkpoint()` 函数中的 `load_kwargs`：

```python
# 修改前
load_kwargs = {}

# 修改后
load_kwargs = {'weights_only': False}
```

### 缺点
- 仅修复 CellBender 内部
- CellBender 更新/重装后需重新应用
- 其他 PyTorch 工具不受影响

## 相关文件

- `sitecustomize.py` 完整代码：`C:\Users\USERNAME\AppData\Local\Programs\Python\Python312\Lib\site-packages\sitecustomize.py`
- 首次出现：2026-07-26, `4CL_SD_D4_2_scRNA` CellBender 重跑
