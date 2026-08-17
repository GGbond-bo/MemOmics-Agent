# skill_evolution record_run 静默失败修复记录

> 2026-07-08 会话中发现。`skill_evolution(action="record_run")` 在特定条件下返回 Success 但数据不落盘。

## 现象

- 调用 `skill_evolution(action="record_run", ...)` 返回 `{"success": true, "message": "Success recorded: ..."}`
- 但 `skill_evolution(action="query_logs")` 找不到任何 proven_runs
- `.run_logs/` 目录不存在
- `results/.../log/run_record_*.json` 不存在

## 两种失败模式

### 模式 A: 全程不写（已知，已修复）

调用 1+N 次，**全部**返回 Success 但无一落盘。

**根因：** `_record_success` 函数（`memomics/bio_tools/skill_evolution.py`）在以下三种情况下**静默吞掉异常**（`try/except pass`）：
1. **`skill.json` 不存在** → `json_updated = false`，数据不写入
2. **SKILL.md 没有有效的 Proven Scripts 表格** → `proven_added = false`，数据不写入
3. **`_archive_to_results_log` 失败**（`get_session_results_dir()` 返回空）→ 数据不归档

所有 `try/except` 块只 `pass`，不抛出任何警告或错误。

**修复：** 创建 `skill.json` + 补全 SKILL.md 的 Proven Scripts 表格（见下方修复步骤）。

### 模式 B: 部分成功 + 部分静默不写（2026-07-08 新增发现）

同一 skill/会话内，前 N 次 `record_run` **成功落盘**到 `results/.../log/`，后续 M 次同样返回 Success 但**不写文件**。

**示例（scTour 分析，人类骨骼肌/衰老，2026-07-08）：**
```
调用1: 01_preprocess.py       → ✅ 落盘 (run_record_020000)
调用2: 02_run_sctour.py run1 → ✅ 落盘 (run_record_020001)
调用3: 03_compare_runs.py    → ✅ 落盘 (run_record_020002)  [脚本名带歧义]
调用4: 04_generate_report.py → ✅ 落盘 (run_record_020003)  [脚本名带歧义]
调用5: 03_compare_runs.py    → ⚠️ 返回 Success，但不写
调用6: 04_generate_report.py → ⚠️ 返回 Success，但不写
```

**可能根因（未证实，待后续会话验证）：**
- session state 在若干次调用后重置（`get_session_results_dir()` 变空）
- 内部计数器/缓存溢出
- 文件已存在时，`append` 模式而非 `write` 模式落盘失败
- 内存不足或操作系统级文件句柄限制

**修复：** 同"模式 A"的修复步骤，但只需手动补录缺失的M条记录。不可依赖工具承诺的返回值。

## 修复步骤

### 1. 创建 skill.json

```json
{
  "name": "<skill-name>",
  "version": "1.0.0",
  "success_count": 0,
  "proven_script": "",
  "proven_params": []
}
```

写入 `hermes_home/skills/bioinformatics/<skill-name>/skill.json`

### 2. 补全 SKILL.md 的 Proven Scripts 表格

在 SKILL.md 末尾添加：

```markdown
## Proven Scripts

> 经实际运行验证成功的脚本记录。`skill_evolution(action="record_run")` 自动追加至此表。

| 物种 | 组织 | 方向 | 日期 | 质量评分 |
|:----|:----|:----|:----:|:--------:|
| <!-- 首次运行后自动填充 --> | | | | |
```

### 3. 手动补录缺失的运行记录

对每个已成功执行的脚本，手动创建 `run_record_*.json` 到 `results/.../log/` 目录：

```json
{
  "success": true,
  "action": "record_success",
  "skill": "<skill-name>",
  "proven_scripts_updated": true,
  "skill_json_updated": true,
  "message": "Success recorded: <script_name> for <species>/<tissue>/<direction>",
  "script_name": "<script_name>",
  "species": "<species>",
  "tissue": "<tissue>",
  "direction": "<direction>",
  "params_used": "<JSON string>",
  "result_summary": "<summary>",
  "quality_score": <score>,
  "notes": "<notes>",
  "timestamp": "<YYYY-MM-DD HH:MM:SS>"
}
```

### 4. 验证修复

```bash
# 检查 skill.json 存在
ls -la /path/to/skill/skill.json

# 检查 SKILL.md 有 Proven Scripts 表
grep "Proven Scripts" /path/to/skill/SKILL.md

# 调用 query_logs 验证
skill_evolution(action="query_logs", skill_name="<skill-name>", ...)
# 应返回 proven_runs 列表

# 检查 log 目录
ls results/.../log/run_record_*.json
```

## 预防（强制验证子步骤）

每次 `skill_evolution(action="record_run")` 后，**必须立即验证文件已真实落盘**，不可信任返回值的 `success` 字段。

### 验证脚本（Python）

```python
import os, json
from datetime import datetime

def verify_run_record(log_dir: str, record_data: dict) -> bool:
    """验证 skill_evolution record_run 是否真实落盘。未落盘则手动写入。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"run_record_{ts}.json"
    fpath = os.path.join(log_dir, fname)
    
    if os.path.isfile(fpath):
        with open(fpath, "r") as f:
            existing = json.load(f)
        if existing.get("script_name") == record_data.get("script_name"):
            print(f"✅ [VERIFY] {fname} already on disk — skill_evolution wrote correctly")
            return True
    
    # 未落盘 → 手动写入
    with open(fpath, "w") as f:
        json.dump(record_data, f, indent=2)
    print(f"⚠️ [VERIFY] {fname} NOT written by skill_evolution — manually saved")
    return False
```

### 集成到 8 步循环

```python
# 在 terminal 执行后、rail_review(post) 通过后：
skill_evolution(action="record_run", ...)  # 原调用
verify_run_record(log_dir, record_data)    # 新增验证，不可跳过
```

> **经验教训**（2026-07-08）：此会话中前 4 次调用自动落盘，后 2 次调用返回 Success 但不写。检查发现后已手动补录。**不要在用户问"为什么没日志？"之后才去检查——在每次 record_run 后立即检查。**

## 跨 skill 通用性

此问题不限于 `sctour-trajectory-inference`。所有调用 `skill_evolution(action="record_run")` 的分析 skill 都面临同样的落盘风险。建议其他 skill 复制此验证步骤到其检查清单中。