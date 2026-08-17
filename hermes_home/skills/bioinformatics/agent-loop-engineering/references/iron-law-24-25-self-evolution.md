# Iron Laws 24 & 25 — 自进化闭环 + 环境持久化

> 2026-07-29 CellBender 6 样本脑数据 session 中发现并修复。

## 发现过程

### 触发事件

6 个脑样本 CellBender 跑完后，用户发现**自进化没有自动触发**：

> "但是自进化应该自己进行的呀"

Agent 检查发现 `skill_evolution(action="record_run")` 从未被调用——虽然铁律 7 写了"必须记录"，但它是**执行后收尾**，不像铁律 1-6（执行前拦截）那样有强制门禁。

### 根因分析

```
铁律 1-6（执行前）: 不调用 → 立即暴露 → LLM 不易跳过
铁律 7（执行后）:   不调用 → 无人知晓 → LLM 经常跳过
```

这是架构上的不对称——执行前拦截有天然的门禁效应，执行后收尾没有。

### 修复方案：双层实现

| 层 | 实现 | 机制 |
|---|---|---|
| **L1: SOUL.md 铁律 24** | terminal 完成 → `_pending_record = True` → 下一个 terminal 阻断 | LLM 级门禁 |
| **L2: pipeline 脚本钩子** | 每样本完成后自动写 `run_log.json` | 磁盘级锚点 |

### 第二个相关发现：环境持久化

用户指出 `environment.json` 放在 `cellbender-batch-pipeline/` 下是错的——其他分析（scRNA、ATAC、空间组学）也用得上。应放到全局路径。

- **修复前**: `cellbender-batch-pipeline/environment.json`（per-skill，其他分析访问不到）
- **修复后**: `MEMOMICS_HOME/environment.json`（全局，含 R 4.5.3/4.6.1 路径、包数、Python venv、CLI工具、GPU信息）
- **验证器**: `MEMOMICS_HOME/scripts/validate_env.py`（启动时自动读→验→修）

## 铁律 24: 自动沉淀门禁

```
terminal 完成 → _pending_record = True
    ↓
agent 想跑下一个 terminal → 阻断 ⛔ "先 skill_evolution(action='record_run')!"
    ↓
agent 调 skill_evolution(action="record_run", ...) → _pending_record = False
    ↓
下一个 terminal 放行
```

- 与铁律 22（工具门禁）、铁律 23（自审计）构成三级门禁
- 跳过铁律 24 = 铁律 -1 同级违规，该 terminal 调用无效
- 磁盘上的 `run_log.json`（pipeline 脚本自动生成）即使 LLM 跳过也是永久记录

## 铁律 25: 环境持久化门禁

```
每次分析启动:
  1. read_file("MEMOMICS_HOME/environment.json")   ← 全局文件
  2. terminal("python MEMOMICS_HOME/scripts/validate_env.py --verbose")
  3. exit 0 → 继续 | exit 1 → 已自动修复 | exit 2 → 阻断
```

- `environment.json` 是全局文件，所有分析共享
- `validate_env.py` 自动探测缺失路径（shutil.which → 已知目录 → pip show 回退）
- **禁止硬编码工具路径到脚本里**

## 当前环境速览 (2026-07-29)

| 工具 | 路径 | 备注 |
|------|------|------|
| R 4.6.1 | `C:/Program Files/R/R-4.6.1/bin/x64/Rscript.exe` | 245包，主力环境 |
| R 4.5.3 | `C:/Program Files/R/R-4.5.3/bin/x64/Rscript.exe` | 仅30 base包 |
| Python 3.12 | `MEMOMICS_HOME/.venv/Scripts/python.exe` | MemOmics venv |
| CellBender | `Python312/Scripts/cellbender.exe` | 需要 `TMPDIR=/e/tmp` |
| GPU | RTX 5070 Ti, 16GB | PyTorch 2.11+cu128 |

## 实施文件

- `MEMOMICS_HOME/environment.json` — 全局环境文件
- `MEMOMICS_HOME/scripts/validate_env.py` — 全局环境验证器
- `MEMOMICS_HOME/hermes_home/SOUL.md` — 铁律 24 + 25
- `cellbender-batch-pipeline/scripts/auto_record_hook.py` — run_log.json 自动生成钩子
