# 源码编辑 + 回归归因配方（「改仓库代码」类任务）

> 触发：用户说**「治本」/「改引擎」/「动的是仓库代码，改完得跑 pytest」**。
> 这类任务是 **code-edit + 验证闭环**，**不是 analysis_exec**（无数据、无产物分析）：
> 不建 task_plan、不走分析流程；但**改完必须跑 pytest 并把结果交给他**。
> 用户对引擎级缺陷的默认期望是 **治本（改引擎代码）而非在调用侧绕路**。

实测案例：2026-10-01 让 `skill_evolution` 认 `plotting/ comparison/ statistics/`
（引擎原先把技能目录硬编码成 `hermes_home/skills/bioinformatics/<名>`）。

---

## 1. 定位：先数「调用点」与「硬编码处」，再动手

```bash
# 私有函数的全部调用点 —— 决定「改一处能否全受益」
grep -n "_get_skill_dir" memomics/bio_tools/skill_evolution.py     # → 6 处调用，全走同一函数
# 硬编码串的全部出现处 —— 决定「别只修一条路径」
grep -n "bioinformatics" memomics/bio_tools/skill_evolution.py     # → 2 处（解析 + 同步），都得改
```

🔑 判据：**改前先出这两张清单**。只看到一处就动手 = 迟早要回来修兄弟路径
（本轮 `_get_skill_dir` 与 `_sync_to_hermes_home` 是同一硬编码的两个落点）。

---

## 2. 改多行代码：`patch` 的三个坑（本轮全踩过）

| 坑 | 现象 | 判据 |
|---|---|---|
| fuzzy **归一化缩进** | `patch(mode='replace')` 返回 `success: true`，lint 却报 `IndentationError: unexpected indent` | `.py` / `.R` 改缩进敏感块 |
| `old_string` **首行漏缩进** | 首行没写前导空格 → 匹配到文件的缩进行后**整体平移**，越改越深（连 patch 两次都修不回） | 替换块的相对缩进被放大 |
| **CRLF/LF 模板不匹配** | `execute_code` 里 `assert old in src` 直接失败，而肉眼看着一字不差 | Windows 文件是 `\r\n`、脚本模板是 `\n` |

**正解模板（行级编辑 + 自校验，本轮一次修好）**：

```python
import py_compile
p = r"E:\...\skill_evolution.py"
raw = open(p, encoding='utf-8', newline='').read()
src = raw.replace('\r\n', '\n').replace('\r', '\n')      # ① 先归一行尾再匹配
# lines = src.split('\n')                                #    或按行号编辑
old = '''def foo():
    body'''.strip('\n')                                   # ② 模板缩进与文件逐字符一致
assert old in src, "未匹配到原文"                          # ③ 断言保护：先验证再写
out = src.replace(old, new)
open(p, 'w', encoding='utf-8', newline='').write(out)     # ④ 写回（保持原行尾风格）
py_compile.compile(p, doraise=True)                       # ⑤ 语法自校验，别靠肉眼
```

⚠️ **断言必须排在 `open(...,'w')` 之前** —— 本轮两次 assert 失败都因此**零副作用**（文件未被写坏）。

---

## 3. 整类 bug 批量修（copy-paste 模板 bug）

症状：多个 fallback 块**照抄了同一个返回模板**，`action` 字段错成别人的值。
本轮 `"action": "query_logs"` 出现在 **4 个** fallback 里，只有 1 个（`_query_logs` 自己）是对的。

**扫全类 + 按「所在函数名」判定正确值**：

```python
for i, l in enumerate(lines):
    if l.strip() != 'if not skill_dir:':
        continue
    fn = None
    for k in range(i, -1, -1):                 # 往上找最近的 def
        if lines[k].lstrip().startswith('def '):
            fn = lines[k].lstrip()[4:].split('(')[0].strip(); break
    act = fn.strip('_')                        # _record_success -> record_success
    for j in range(i, i + 7):                  # 该 fallback 块内
        if '"action": "query_logs"' in lines[j] and fn != '_query_logs':
            lines[j] = lines[j].replace('query_logs', act)
```

⚠️ 附带产物：`_record_error` 的 fallback 原本返回 `success=True + action=query_logs` —— 属**假成功**
（调用方以为记录成功、实际什么也没写，还产出 `action` 记错的空壳归档）。
改成 `success=False + error/hint/scanned` 前，**先做第 5 节的调用方审计**。

---

## 4. 「是不是我改坏的」：`git stash` 单文件 A/B

比「读 `git log -1` 日期 + `git status --porcelain`」更直接——**能复现**：

```bash
cd "E:/MemOmics-Agent"
git diff --numstat -- <我改的文件>                 # 对照前：留底（本轮 134/76）
git stash push -m tmp-verify -- <我改的文件>       # 只回退我改的那个文件
.venv/Scripts/python.exe -m pytest -q -p no:warnings <失败的那个测试文件> 2>&1 | tail -6
git stash pop                                      # 恢复
git diff --numstat -- <我改的文件>                 # 恢复后应与对照前一致
```

🔴 **必须用 `;` 分隔，不能用 `&&`**：pytest 失败时退出码非 0，`&&` 链会**跳过 `git stash pop`**，
改动留在 stash 里（看着像「改动丢了」）。
🔑 判据：**回退后同测试仍红 ⇒ 既有失败，与本次改动无关**（本轮 `test_kb_retrieval_golden` 即如此）。

---

## 5. 「改了为什么不生效」≠ 修复失败：常驻进程 vs 动态加载

同一份代码，**两条调用路径行为不同**：

| 路径 | 加载方式 | 改文件后 |
|---|---|---|
| 长驻 server 的**手动工具调用** | server 启动时 `import`，注册进 `sys.modules` | ❌ **不热重载**，一直用旧模块 |
| `enforcement.py` 的**自动路径** | 每次 `spec_from_file_location` + `exec_module` | ✅ 立即读新代码 |

**判别法（本轮实测有效）——在主入口返回里注入版本指纹**：

```python
def _engine_fingerprint() -> str:
    try:
        _p = os.path.abspath(__file__)
        return f"{os.path.basename(_p)}@{int(os.path.getmtime(_p))}"
    except Exception:
        return "unknown"

# 主入口所有返回统一注入
if isinstance(result, dict):
    result.setdefault("engine", _engine_fingerprint())
return json.dumps(result, ...)
```

⇒ **返回 JSON 有 `engine` 字段 = 新模块；没有 = 仍是旧模块**。
本轮即靠它同时拿到两方向证据：`execute_python` 新进程里 `engine` 存在且 `plotting/` 解析成功
（找到 5 条记录，改前返回「尚未注册」），而工具调用无该字段（旧模块）——**一条对照说清全部**。

⚠️ 汇报时把「代码修好了」与「需重启进程才在手动路径生效」**分开写**，别让用户以为修复失败。

---

## 6. 调用方审计：改返回语义前必做（**代码路径级，不许推理**）

```
search_files(pattern="skill_evolution")  → 命中处逐个读，找「真正调用 + 真正读返回值」的那一处
```
本轮实测结论（可作为该项目的既知事实）：
- `webui/server.py` / `hermes-agent/toolsets.py`：只在**工具名白名单 + 审计日志检测**里出现，**不读返回值**；
- `webui/enforcement.py:928-998` 是**唯一真实调用点**：3 个调用全被 `try/except Exception` 包裹，
  `record_error` / `record_run` 的返回值**完全不使用**；唯一读返回值的是 `query_logs` 取 `proven_runs`。

🔑 判据：**`success=False` 是否阻断 = 读调用方代码**，不是猜「可能有外部消费方」。
外部/运维外围同理：`grep` 旧 `action` 串，命中若只在 `.backups/`、SKILL.md 文档、session dump ⇒ **无消费方**。

---

## 7. 辩论复审闭环（裁决 `modify` + `missing` 清单时怎么做）

第一轮 L2 拿到 `verdict=modify` + `missing` 清单 + `reopen_condition`（评测 `caller_impact 4 / regression_safety 5`）——
**这不是「被否」，是给了待补证据清单**。补齐 `missing` 里那些项后**值得再辩一次**（不是重复辩论）：

| 补什么 | 怎么补（本轮） |
|---|---|
| 调用方对 `success=False` 的处理 | 读 `enforcement.py` 调用点代码路径（第 6 节） |
| 回归测试 | 新增 `webui/tests/test_skill_dir_resolution.py` 11 用例 |
| 性能基准 | 脚本内计时：带前缀 0.091 ms / 裸名 0.673 ms（结论：不需要缓存） |
| 行尾规范 | `git show HEAD:<file> | tr -cd '\r' | wc -c` 实测原文件本就是 CRLF ⇒ **推翻裁判的前提** |
| 模型/接口审计 | 脚本枚举同形态 fallback 块 |

复审结果：评分全线上调（`caller_impact 4→8`、`regression_safety 5→9`、`diff_hygiene 3→7`），
裁决变为「现在就发布核心修复 + 一条发布门禁」。
🔑 **补齐证据后重辩 ≠ 同一议题重复辩论**；但**同一议题辩满 2 轮即止**，第 3 次同门控要求应在回复里
说明「本议题已辩 2 轮、裁决已给出、剩余项 owner=user」后收束。

---

## 8. 验证证据怎么给（树是脏的时）

- **相关测试集给退出码 0**：`pytest <我改的 + 技能契约 + 内核池>` → `EXIT=0, 308 passed, 2 skipped`
- **全套给归因**：`EXIT=1` 且只剩 1 个失败 → 用第 4 节 stash A/B 证明既有
- 汇总行易被缓冲吞掉：`> log/pytest_relevant.log 2>&1 ; echo "EXIT=$?" ; grep -E "passed|failed" log | tail -4`
- ⚠️ **不要为「让套件变绿」顺手改无关模块**（本轮 KB 检索 golden 失败属另一模块）——
  如实报告 + 问用户是否另开一轮修。