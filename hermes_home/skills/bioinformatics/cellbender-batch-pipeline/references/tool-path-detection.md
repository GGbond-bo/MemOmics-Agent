# 工具路径动态探测

## 问题

硬编码工具路径（如 `C:/Users/USERNAME/AppData/Local/Programs/Python/Python312/Scripts/ptrepack.exe`）在以下场景失效：
- 不同机器 / 不同用户名
- Python 版本升级（3.12→3.13）
- 虚拟环境 vs 系统 Python

## 三级探测策略

分析启动时执行，结果写入 task_plan.md 的 `## Environment` 段：

```python
import shutil
import sysconfig
import subprocess
import os

def find_tool(name, pip_package=None):
    """
    三级探测：which → sysconfig → pip show
    返回 (full_path, source) 或 (None, "not found")
    """
    # Level 1: PATH 搜索
    path = shutil.which(name)
    if path:
        return (path, "shutil.which")

    # Level 2: Python Scripts 目录
    scripts_dir = sysconfig.get_path("scripts")
    for ext in ["", ".exe", ".cmd", ".bat"]:
        candidate = os.path.join(scripts_dir, name + ext)
        if os.path.exists(candidate):
            return (candidate, "sysconfig.get_path('scripts')")

    # Level 3: 从 pip package 推导
    if pip_package:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", pip_package],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                if line.startswith("Location:"):
                    loc = line.split(":", 1)[1].strip()
                    # Scripts 通常在 Location 的兄弟目录
                    parent = os.path.dirname(loc)
                    scripts_candidate = os.path.join(parent, "Scripts", name + ".exe")
                    if os.path.exists(scripts_candidate):
                        return (scripts_candidate, "pip show Location")
        except Exception:
            pass

    return (None, "not found")
```

## 常用工具探测

| 工具 | name | pip_package |
|------|------|-------------|
| ptrepack | ptrepack | tables |
| cellbender | cellbender | cellbender |
| scanpy | (Python import) | scanpy |

## 写入 task_plan.md

```markdown
## Environment（分析启动时自动探测）
| 工具 | 路径 | 来源 |
|------|------|------|
| ptrepack | C:\Users\...\Python312\Scripts\ptrepack.exe | sysconfig |
| cellbender | C:\Users\...\Python312\Scripts\cellbender.exe | shutil.which |
| python | C:\Users\...\Python312\python.exe | sys.executable |
```

## 在脚本中使用

```python
# ptrepack_all.py / ptrepack_h5py_batch.py 启动时：
import json, os

def load_env_from_task_plan(task_plan_path):
    """从 task_plan.md 的 Environment 表解析工具路径"""
    # 简单实现：读 .md → 正则提取表格行
    # 更可靠方案：同时写 .env.json 文件
    pass

# 或运行独立探测
ptrepack_path, source = find_tool("ptrepack", "tables")
if ptrepack_path:
    print(f"ptrepack: {ptrepack_path} (via {source})")
else:
    print("WARNING: ptrepack not found, falling back to h5py")
```

## 铁律

- **绝不硬编码路径**。所有脱离式 Popen/脚本中的工具路径必须来自探测结果。
- 探测失败 → 写入 task_plan.md `## Errors Encountered` 告警，使用 fallback 方案。
