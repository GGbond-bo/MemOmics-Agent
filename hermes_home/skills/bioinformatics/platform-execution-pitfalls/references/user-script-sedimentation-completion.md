# 用户脚本沉淀的完整收尾（写到最后一道门：git add + 对口测试）

> 适用：用户说「**把这段代码存到用户 skill**」「**我以后可能会用到，沉淀了嘛**」「**你沉淀了吗**」，
> 或脚本跑通、用户认可后你决定沉淀。覆盖 **plotting / comparison / statistics** 三类用户脚本库。
> 配套：SOUL.md 用户脚本铁律（分类规则）、`platform-execution-pitfalls` 坑表里那两行沉淀相关条目。

---

## 0. 触发与心态：主动，不要等问责

实测（2026-10-01）：脚本交付后停手，用户下一轮直接问「我以后可能会用到，这些你沉淀了嘛？」，
再下一轮追问「**你沉淀了吗？**」——两次追问都是因为我把沉淀留在了「以后」。

- **正确时机**：脚本跑通 + 用户看过交付 = 当轮就沉淀（或至少当轮问一句「要不要沉淀成用户 skill」）。
- **被问到时唯一正确的回答姿势**：先 `read_file` 读 `hermes_home/skills/user-scripts/INDEX.md` 的**实际行数**，
  再回答。本轮即靠这一步得出「索引只有 1 条（9-15 的 AUCell 热图）、你要的这两份一条没登」——
  而不是凭印象说「已经沉淀了」。
- 判据：**盯索引文件的实际内容，不盯自己的记忆。**

---

## 1. 定位脚本：别只搜会话 `scripts/`

同一个会话里产出的脚本**不都在 `<sid>/scripts/`**：本轮火山图在 `<sid>/task3/scripts/`，
计数柱状图在 `<sid>/scripts/`。

```bash
# 按名字搜（快）
#   search_files(path=<sid>/results, pattern='*volcano*', target='files')
# 按内容搜（名字对不上时）
#   search_files(path=<sid>/, pattern='volcano|火山', target='content', output_mode='files_only')
# 列全量再挑（最稳）
#   search_files(path=<sid>/scripts, pattern='*.py', target='files')
```

⚠️ 内容搜用中文关键词在中文路径下可能返回 0（假阴性）——拿不准就改 `terminal grep -n`。

---

## 2. 同一脚本的「变体」要抽出独立可跑版

本轮教训：`fig_deg_updown_8sub_MF_v7b_arrows_at_center.png` 是**内核 exec 注入变量**跑出来的
（`MF_VARIANT="center"` + `STEM_OVERRIDE=...`），磁盘上只留下默认态（`right`）的脚本本体 ——
所以用户问「这张图的脚本是什么？你好像没给我脚本呢」，而磁盘上**没有那个文件**。

沉淀与交付时都要把开关**硬编码另存为独立可跑版**：

```python
MF_VARIANT = globals().get("MF_VARIANT", "center")          # 默认改成用户选定那一版
STEM = globals().get("STEM_OVERRIDE") or "fig_..._v7b_arrows_at_center"
```

---

## 3. 入库：三个实物 + 索引登记

| 实物 | 位置 | 要点 |
|---|---|---|
| `SKILL.md` | `hermes_home/skills/plotting/<名>/` | frontmatter：`metadata.hermes.category: user-skill`（**注意 category 嵌在 `metadata.hermes` 下**，顶层 `category:` 是 `None`）、`source: user` 或 `user-requested`、`verified: <日期>`；正文含 使用场景 / 输入要求 / 参数与版式 / 验证状态 / **修复记录（踩过的坑）** / 来源 |
| `skill.json` | 同上 | 必需键：`id` `name` `category` `source` `proven_script` `trigger_keywords`；再带 `parameters` / `proven_params` / `error_count` / `success_count` / `trigger_level` |
| `scripts/<脚本>` | 同上 | **用 `cp` 从原路径复制**，保字节一致（别手抄/重写） |
| 索引行 | `hermes_home/skills/user-scripts/INDEX.md` | 表列：名称 ｜ 用途 ｜ 触发词示例 ｜ 路径 ｜ 沉淀日期 ｜ 状态 |

⚠️ **skills 根目录是 `hermes_home/skills/`**（`<root>/hermes_home/skills/`），**不是 `<root>/skills/`**。
本轮先搜了错的路径 → `total_count: 0` → 差点得出「索引不存在」的假结论。记忆里也有这条位置映射，直接照它走。

---

## 4. 收尾门禁（**这一步最容易漏**）

### 4.1 `git add` —— 不 add 就是没沉淀完

```bash
cd <root>
git add hermes_home/skills/plotting/<名1> hermes_home/skills/plotting/<名2> hermes_home/skills/user-scripts/INDEX.md
git status --short hermes_home/skills/plotting hermes_home/skills/user-scripts
```

不 add 的后果（2026-10-01 实测，当场红）：

```
webui/tests/test_skills_registry.py:504: in test_index_is_reproducible_from_committed_metadata
    assert not untracked, "这些技能的 skill.json 还没入 git（全新 checkout 的索引会多行或少行）: %s" % untracked[:12]
E   AssertionError: ['deg-updown-counts-by-subcluster', 'deg-volcano-5comps-8sub-R']
```

顺带收益：`git status --short <同族目录>` 会暴露**历史沉淀的同类漏 add**（本轮抓到 9-15 那个 skill
的 `scripts/` 一直是 untracked —— 这正是 AGENTS.md 记的「改完不提交会丢东西」那一类）。

**未 commit 不算违规**（仓库本就几百个改动文件，提交怎么分组由用户定），但**必须 add**。

### 4.2 跑对口测试

```bash
cd <root> && .venv/Scripts/python.exe -m pytest \
  webui/tests/test_skills_registry.py webui/tests/test_skills_sync.py \
  webui/tests/test_skill_routing_matrix.py webui/tests/test_skill_trigger_contract.py \
  -m "not external and not network and not live_llm and not gpu and not ssh and not lab and not docker and not browser" \
  -p no:warnings --tb=short 2>&1 | tr '\r' '\n' | grep -vE '^\s*$' | tail -6
```

实测结果：**285 passed, 2 skipped in 18.67s**（exit 0）。

⚠️ 两个坑：
- **汇总行会被 `\r` 吃掉** → `| tr '\r' '\n' | tail -6` 才看得到 `N passed`；
- 这 4 个文件**只校验注册表一致性/触发契约，不校验内容质量** → 见 4.3 自验。

### 4.3 自验（测试覆盖不到的部分）

```python
import json, yaml, hashlib, os
SK = 'hermes_home/skills/plotting'
pairs = [('<名>', '<脚本名>', '<原脚本绝对路径>'), ...]
for name, fn, orig in pairs:
    d = os.path.join(SK, name)
    j = json.load(open(os.path.join(d, 'skill.json'), encoding='utf-8'))
    txt = open(os.path.join(d, 'SKILL.md'), encoding='utf-8').read()
    fm = yaml.safe_load(txt.split('---')[1])
    a = hashlib.sha256(open(os.path.join(d, 'scripts', fn), 'rb').read()).hexdigest()
    b = hashlib.sha256(open(orig, 'rb').read()).hexdigest()
    print(name, '缺键', [k for k in ['id','name','category','source','proven_script','trigger_keywords'] if k not in j],
          '| category =', fm['metadata']['hermes']['category'], '| source =', fm.get('source'),
          '| 脚本字节一致 =', a == b)
```

判据三条：**JSON 可解析 + 必需键齐** / **YAML frontmatter 可解析且 `metadata.hermes.category == user-skill`** /
**沉淀脚本 sha256 与原件一致**（证明「字节未改」不是嘴上说的）。

---

## 5. `record_run` 对新建用户 skill 的预期行为

新建的用户 skill 调 `skill_evolution(action="record_run", skill_name="plotting/<名>")`，回执是
**`action: query_logs` 形态**（「无历史运行记录…尚未注册或目录不存在」）——**这是预期，不是失败**
（自进化 run log 只写 bioinformatics 系 skill 自身目录，用户脚本库不在那张登记表内）。

⛔ **不要换措辞反复 record_run**（回执不变，还赚循环告警）。把 §3 的三件实物 + §4 的测试/自验结果
写进汇报即完成闭环。

### 5.1 更糟的一种：`skill_name` 是**自造名**（仓库里根本不存在该 skill）

实测（2026-10-01 唤醒轮）：为记录一次引擎修复，传 `skill_name="skill_evolution-engine-dir-resolution"`
（临时起的名）→ 回执与 §5 同形（`action: query_logs` / `无历史运行记录。skill '...' 尚未注册或目录不存在
— 运行后将自动创建记录`），**再投一次回执一字不差**，也**没有任何 `record_success` 之类的成功回执**；
同一内容改用已注册的 `wakeup-progress-check` → 立刻 `record_success: true` +
`proven_scripts_updated: true` / `skill_json_updated: true`。

⇒ 规则：**`record_run` / `record_error` 的 `skill_name` 应是「真实存在的 skill 名，或明确在沉淀的
`plotting|comparison|statistics/<名>`」**；拿不准先 `skills_list` / `skill_view` 确认，再记。
自造名拿不到可确认的成功回执，事后无法证明「记录过」——**要留档就记在真实 skill 上**。

### 5.2 顺带：门禁工具的传参口径（同一轮实测）

- `rail_review(post)` 的 `code_executed` 传 **terminal 命令行**（一行 `.venv/Scripts/python.exe xxx.py`）
  → 判 `代码过短 (8 行)` + `使用 && 连接多步骤` **failed**；`read_file` 读脚本正文重提 → **passed，
  脚本一行没重跑**（属静态文本类 ⇒ **只改传参，绝不重跑**）。
- 同一议题已辩过的只读核查：按门控如实跳 L0 并写明理由，别为凑门禁硬辩。
- 多轮同状态空转的整轮规程（含弹窗催办 + 探针假阳性/假阴性修复）→ `wakeup-progress-check` 的
  `references/repeated-wakeup-escalation.md`。

---

## 6. 汇报模板（用户会逐项看）

```
沉淀完成：<名1>、<名2> → hermes_home/skills/plotting/
- 三件实物：SKILL.md / skill.json / scripts/<脚本>（cp 保字节）
- 索引：user-scripts/INDEX.md 已登记（触发词：… / …）
- 门禁：git add 完成（含顺带补上的 <同族漏 add>）；对口测试 285 passed / 2 skipped
- 自验：JSON+YAML 可解析、脚本 sha256 与原脚本一致
- 未 commit：仓库还有 N 个改动文件，提交分组等你定
```

**顺带说明**：重跑脚本前先看一下脚本性质 —— **新增用户脚本必须做到 git add**，用户可见的「沉淀」
是文件在库里且可被 `skill_view` 发现，不只是「我记下了」。