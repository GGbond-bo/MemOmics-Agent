# 缺顶层 skill.json 的三连锁失败链（2026-10-04 实测）

> 一次「只在 `templates/` 放了 skill.json、顶层忘了写」的小疏忽，触发**三个方向不同**的门禁红灯。
> 三个报错看着互不相干，根因却是同一个 + 一条扫描器规则。把这条链记住，下次 5 分钟收敛。

## 复现条件

新建两个技能（`skill-registration-and-routing` / `windows-com-app-automation`），各自：
```
<skill>/
├── SKILL.md          ← 有完整 frontmatter（trigger_level: RED + trigger_keywords）
├── references/
├── scripts/
└── templates/
    └── skill.json    ← ❌ 只有这里放了 skill.json，顶层没有
```

## 报错链（按出现顺序）

### ① 索引漂移：幽灵技能
```
[skills-gate] x SKILLS_INDEX.md 与磁盘不一致（2 处）：
    . SKILLS_INDEX.md 与磁盘不同步（跑 --build 重建）
    . 索引缺少技能: templates
```
**根因**（`webui/skills_registry.py::scan_skills`）：
```python
for root, dirs, files in os.walk(SKILLS_DIR):
    ...
    if "skill.json" not in files:      # ← 判据只有这一条
        continue
    name = os.path.basename(root)      # ← 技能名 = 目录名
```
扫描器 `os.walk` **全树遍历**，任何含 `skill.json` 的目录都被当技能。
`templates/skill.json` 于是变成一个名叫 **`templates`** 的技能（两个技能各贡献一份，按名字去重后报 1 条）。

**修法**：模板改名 → `templates/skill.json.template`（扫描器只认精确文件名 `skill.json`）。

### ② 两侧口径漂移：WebUI 有、索引没有
```
E  assert {'_debates', ..., 'windows-com-app-automation', 'skill-registration-and-routing'} <= {'_debates'}
E    Extra items in the left set:
E    'windows-com-app-automation'
E    'skill-registration-and-routing'
webui/tests/test_skills_registry.py:309
```
**根因**：两侧扫描判据不同 ——
- WebUI 选择器 `server.list_skills()`：扫 `skills/` + `hermes_home/skills/{bioinformatics,plotting}`，**认目录**
- 注入索引 `reg.scan_skills()`：**认 `skill.json`**

顶层缺 skill.json → 前者列出、后者跳过 → `pick - idx` 多出两个名字。

**修法**：补顶层 `skill.json`（形状见 `templates/skill.json.template`：`name/version/source/trigger_level/trigger_keywords/when_to_use`）。
触发词取 SKILL.md frontmatter 里已写好的那份（skill.json 优先级最高，写这里才算数）。

> 顺带说明：该测试只放行两个**已登记差异**——`_debates`（运行期辩论目录，选择器误当技能）与
> `translate-book`（Hermes 自带根目录，选择器不扫）。差异超出这两个 = 口径又漂了。

### ③ 未入 git：索引可复现性
```
AssertionError: 这些技能的 skill.json 还没入 git（全新 checkout 的索引会多行或少行）:
  ['skill-registration-and-routing', 'windows-com-app-automation']
webui/tests/test_skills_registry.py:504
```
**根因**：该测试从**暂存区**重建索引（`git show :<path>`）再与磁盘对比 —— 刚创建的 skill.json 未跟踪，
全新 clone 出来的索引会比现在少两行。

**修法**：`git add <技能目录>` —— **加整目录**（`templates/`、`references/`、`scripts/` 一起），
不要只 add `SKILL.md`。

## 收口证据（本次）

```
$ python scripts/check_skills_gate.py
[skills-gate] OK 索引一致（387 个技能：RED 66 / YEL 308 / GRN 13）
[skills-gate] OK 测试通过（876 例，跳过 2）
[skills-gate] PASS
```
提交：`235ea5ed`（12 files changed, 985 insertions）— pre-commit 钩子跑同一门禁后才放行。

## 中途一并解决的两件事

### A. 新增 RED 技能 → 覆盖率断言会咬人
`test_skill_routing_matrix.py` 有**覆盖率断言**：每个 RED 技能至少要有一条 case 覆盖
（或登记在 `fixtures/skill_routing_matrix.json` 的 `coverage_exempt`）。
新技能进索引那一刻就变成 RED → 立刻要求用例。

补用例时注意 **matcher 是子串匹配**（`kw in text`）：用例文案必须**字面包含**某条 `trigger_keywords`，
否则用例自己先红、还容易误判成"技能没注册成功"。本次两条可用样例：
```json
{"id": "skill-registration-and-routing-01", "intent": "口语",
 "text": "新建技能后命不中，matcher命中为空，帮我查一下触发词回填的问题",
 "must_hit": ["skill-registration-and-routing"], "max_hits": 4},
{"id": "windows-com-app-automation-01", "intent": "直白",
 "text": "帮我用 ExtendScript 批量改 Illustrator 里的文字，这个软件没有CLI",
 "must_hit": ["windows-com-app-automation"], "max_hits": 4}
```
（`max_hits` 要给同族技能留位：上面第二条同时命中 `cli-anything`，因为「批量改」是它的词。）

### B. 只有换行符差异的 skill.json —— 别当真改动
`git status` 里冒出 1 个「被改过」的 skill.json，`--numstat` 是 **29/29 对称**、diff 全是 `+...\r`：
内容逐字节相同，只是 LF→CRLF。根因是写它的代码缺 `newline="\n"`
（`webui/server.py` 的技能写接口 `open(..., "w", encoding="utf-8")`，Windows 下 `\n` 被翻成 `\r\n`）。
**处理**：`git checkout -- <file>` 还原（零内容损失）。判别法：
```python
d = open(p, "rb").read()
print("CRLF:", d.count(b"\r\n"), "| LF 总:", d.count(b"\n"))   # 相等 = 整文件都是 CRLF
```

## 配套诊断：这一大堆脏文件是不是我弄的？

长会话收尾常看到几百个 `M`，先别慌，**用 mtime 说话**，再与**会话起始快照的 git 计数**对齐：

```python
# 按 mtime 分桶（只统计涉及技能面的改动）
files = [l[3:].strip().strip('"') for l in
         subprocess.run(["git","status","--porcelain"],capture_output=True,text=True).stdout.splitlines()
         if l.strip().endswith("skill.json")]
Counter(datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d") for f in files)
```
本次结果：333 个里 **299 个 mtime = 09-23**（进场前 11 天）、今天只有 1 个 →
结论「不是我干的」，并用 `416 M` 与会话起始快照 `416 modified` 精确对上（还原那 1 个后计数回到 416）。