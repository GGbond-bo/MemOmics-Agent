# 仓库代码修复的「eol 噪音 + 部署生效性」闭环（2026-10-01 实测）

> 场景：用户说「改引擎扫描路径」（`skill_evolution` 认 `plotting/ comparison/ statistics/`），并附加
> 「治本，但动的是仓库代码，**改完得跑 pytest**」。属 SKILL.md 使用要点第 18 条同族 —— 是
> **code-edit + 验证闭环**，不是 analysis_exec（无数据、无产物分析，但仍要跑仓库测试并交结果）。
> 本文件记录该条没覆盖的四件事：**换行符、指纹、重启语义、测试断言自伤**。

---

## 1. CRLF 噪音：为什么 diff 会凭空多出 2000 行

本仓库（`E:/MemOmics-Agent`）的 `.py` 是 **CRLF**。两个写入路径都会把它改成 LF：

| 写入方式 | 症状 | 实测数据 |
|---|---|---|
| `write_file` 整文件重写 | 全文件行尾 LF | `git diff --numstat` **+1230/−1131**；`git diff -w --numstat` **+114/−15** |
| `patch(mode='patch')`（V4A 多块） | **新增行 LF、原有行 CRLF → 混行尾** | 多块 patch 后 numstat 300/81（-w 239/20） |

### 自查（两行命令，任何改动后都跑）

```bash
git diff --numstat     <file>     # 含行尾差异
git diff -w --numstat  <file>     # 忽略空白/行尾，≈ 真实改动
```

两者差值大 ⇒ 行尾被打乱。也可用 `file <path>` 看 `with CRLF, LF line terminators`。

### 修复（整文件归一，一次搞定）

```python
d = open(p, 'rb').read()
d = d.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')   # 先归一 LF 再统一 CRLF
open(p, 'wb').write(d)
```

- **收尾统一做一次**：多块 V4A patch 之后文件必然是混行尾，最后统一归一。
- 新建的**未跟踪**文件（如新增测试）也要归一，保持仓库一致。
- 判据：**「diff 无换行符噪音」写进本步验证清单**——否则用户 review 时看到 2000 行红色会误判改动规模。

---

## 2. 引擎指纹：mtime 不可靠，且「文件哈希 ≠ 进程已加载」

长驻 server 启动时 `import` 的模块**不热重载**（手动工具调用走旧模块），而 enforcement 的动态
`spec_from_file_location + exec_module` 路径每次都读新代码 ⇒ 同一份代码两条路径行为不同。

两轮辩论（L2 + L1 复审）**都**把这一条列为 `blocks` 项，要求的顺序是：

1. **指纹主判据 = 内容哈希**，不是 mtime：

```python
def _engine_fingerprint() -> str:
    _p = os.path.abspath(__file__)
    _h = hashlib.sha256()
    with open(_p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            _h.update(chunk)
    _st = os.stat(_p)
    _git = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          cwd=os.path.dirname(_p), capture_output=True,
                          text=True, timeout=5).stdout.strip() or "none"
    return (f"{os.path.basename(_p)}@sha256:{_h.hexdigest()[:12]}@size:{_st.st_size}"
            f"@mtime_ns:{_st.st_mtime_ns}@git:{_git}")
```

   ⚠️ mtime 在 **git checkout / 打包安装 / rsync·tar 保留时间戳 / 时钟回拨** 下会把「内容已变」判成没变。
   `size` / `mtime_ns` / `git 短 SHA` **只作人工核对附件，不得单独当部署门禁**。
   配对用例要有两个：① mtime 变、内容不变 → 哈希不变；② **内容变、mtime 与另一份相同 → 哈希必须变**。

2. **启动期自证**（把内容哈希绑到「进程内实际加载的那份」）：

```python
ENGINE_VERSION = _engine_fingerprint()
logger.info("skill_evolution engine loaded: file=%s version=%s",
            os.path.abspath(__file__), ENGINE_VERSION)
```

3. **部署验收 = 重启后 smoke**。没重启就**不得声称已生效**——两轮裁决的 fallback 都写着
   「若无法立即重启，先把改动留在分支，禁止用哈希当生效门禁」。

### 实操坑：公共调度器返回的是 **JSON 字符串**

```python
s = mod.skill_evolution(action="query_logs", skill_name="plotting/<名>")
d = json.loads(s)          # ← 必须先解析；直接 s.get("engine") 会 AttributeError
d["engine"]                # → 'skill_evolution.py@sha256:…@git:0ce87713'
```

实测新模块：字段存在、`proven_runs` 有内容；旧模块（未重启）：`record_run` 回退成 `query_logs` 形态并报「尚未注册」。

---

## 3. 测试断言自伤：用例名进了 `tmp_path`

```python
def test_no_silent_bioinformatics_fallback(engine):        # ← 名字里带了 "bioinformatics"
    r = mod._query_logs("no-such-skill-xyz")
    assert "bioinformatics" not in json.dumps(r, ensure_ascii=False)   # ← 假失败
```

pytest 的 `tmp_path` 会**把用例名嵌进临时目录名**：`.../pytest-952/test_no_silent_bioinformatics_0/hermes_home/skills`
→ `searched_roots` 里就含 `bioinformatics` ⇒ 断言命中**路径本身**，而引擎行为完全正确。

**两条规则**：
1. 断言关键词**不要出现在用例名里**（改 `test_no_silent_path_guess`）；
2. 优先断**结构字段**而非全量字符串（`diagnosis["candidates"] == []`、`status == "not_found"`）。

判据：这类失败**先怀疑断言口径**，别急着改产物代码（本轮改名前一度怀疑引擎回退到了 bioinformatics 猜测）。

---

## 4. 仓库代码修复的 `rail_review(post)` 传参

| 传什么 | 结果 |
|---|---|
| shell 命令（`pytest … ; git diff …`） | ❌ `代码过短 (5 行)` + `使用 && 连接多步骤` |
| **真实改动代码块**（新增/改写的函数体）+ 命令/退出码/用例数证据 | ✅ `passed=true` |

属**静态文本类**判定 ⇒ **不要为此重跑脚本**（同 SKILL.md「静态文本类 issue 不重跑」）。

---

## 5. 收尾：把裁决动作和「用户侧动作」分开写

- 两轮裁决都是 `verdict=modify`，卡的**不是测试**而是**部署生效性**；`next_actions[{action,owner,blocks}]`
  中的 `blocks` 未完成项就是验收清单（已在 task_plan 里逐条勾掉）。
- 汇报模板：**「代码已修好（证据：N 用例 / M 文件全绿 / exit=0）」＋「待你重启进程后 smoke（判据：返回 JSON 含 engine）」**
  两条分开写——别让用户以为修复失败。
- **同一议题本会话已辩过两次、剩余动作只在用户侧**时：如实说明援引「同议题去重 / 辩完不改变下一步动作」
  原则跳到 L0，不为凑门禁硬辩第三轮（SOUL 三级门控给的就是这个授权）。
- 系统反复提示「工作区未验证」时：**跑一次针对性 pytest 取证即止**，不做连环复验（同 SKILL.md「连续多轮同类
  验证 → 循环检测干预」行）。

---

## 6. 本轮改动全貌（可作模板）

```
memomics/bio_tools/skill_evolution.py            # 300/81（-w 239/20）
  _skill_roots()                   双布局根（skills/ + hermes_home/skills/）
  _iter_skill_category_dirs()      任意一级分类 + OSError 隔离（坏目录不中断全解析）
  _resolve_skill_dir_detail()      前缀 → 顶层 → 分类遍历；**唯一命中才接受**（歧义拒绝）
  resolve_skill_dir()             公共诊断入口；_diag_brief() 透传给 4 个调用点
  _engine_fingerprint() / ENGINE_VERSION          内容哈希 + 启动期自证
webui/tests/test_skill_dir_resolution.py         # 26 用例（主路径 11 + 边界 8 + 复审补充 7）
```

验证命令（仓库规定的对口测试）：
```bash
.venv/Scripts/python.exe -m pytest webui/tests/test_skill_dir_resolution.py \
    webui/tests/test_skills_registry.py webui/tests/test_skills_sync.py \
    webui/tests/test_skill_trigger_contract.py webui/tests/test_skill_routing_matrix.py \
    webui/tests/test_kernel_pool.py -q -p no:warnings -rs
```