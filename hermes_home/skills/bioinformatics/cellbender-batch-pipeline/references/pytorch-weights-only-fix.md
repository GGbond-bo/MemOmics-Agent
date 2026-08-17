# PyTorch 2.11 weights_only 修复

## 问题

PyTorch 2.11+ 将 `torch.load()` 的默认 `weights_only` 从 `False` 改为 `True`，导致 CellBender 无法加载自己的 checkpoint（自定义类 `RemoveBackgroundPyroModel` 不在安全白名单）。

### 错误日志特征

```
_pickle.UnpicklingError: Weights only load failed. 
This file can still be loaded by setting `weights_only=False`. 
Unsupported class: remove_background.downstream.Model
```

或类似的自定义类 unpickling 错误。

## 修复：sitecustomize.py monkey-patch

在 Python 的 `sitecustomize.py` 中同时 patch `torch.save` 和 `torch.load`：

```python
# sitecustomize.py — 放在 Python 的 site-packages 目录下
import torch
import builtins

_original_save = torch.save
def patched_save(obj, f, *args, **kwargs):
    try:
        return _original_save(obj, f, *args, **kwargs)
    except (TypeError, AttributeError) as e:
        print(f"[sitecustomize] torch.save patch caught {type(e).__name__}: {e}", flush=True)
        raise

torch.save = patched_save

_original_load = torch.load
def patched_load(f, *args, **kwargs):
    # PyTorch 2.11+ defaults weights_only=True, which blocks CellBender checkpoint loading
    if 'weights_only' not in kwargs:
        kwargs['weights_only'] = False
    return _original_load(f, *args, **kwargs)

torch.load = patched_load

print("[sitecustomize] torch.save + torch.load patched (weights_only=False default)", flush=True)
```

## 验证

启动 CellBender 后检查日志是否出现：
```
[sitecustomize] torch.save + torch.load patched (weights_only=False default)
```

## 安装位置

```bash
# 找到 site-packages 路径
python -c "import site; print(site.getsitepackages()[0])"

# 复制 sitecustomize.py 到该路径
cp sitecustomize.py <site-packages>/
```
