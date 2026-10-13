# skills-gate FAIL 分诊证据链（2026-10-12 实测）

**场景**：新建技能 `chinese-research-latex`（RED，16 条 trigger_keywords，5 个文件 + 3 条路由用例）后跑 `python scripts/check_skills_gate.py`。
**触发链路本身全绿**，FAIL 全部来自**预存**问题 —— 这份记录的价值在于"别把别人的坑算成自己的"。

---

## 1. 触发链路绿的确凿回执（先拿到这部分，再谈门禁）

```
# 索引重建
使用场景来源: {"json.when_to_use": 396}
触发词来源: {"json.trigger_keywords": 366, "名称派生": 17, ...}
缺触发词: 0 []        RED 但完全没有触发词: 0 []
已写入 memomics_home/SKILLS_INDEX.md (488 行 / 69985 字符)

# 索引行（第 367 行）—— 16 条手写关键词原样保留，未被名称派生回填
367:| 4 | chinese-research-latex | ... | 写基金, 国自然, 标书, 基金申请, 写毕业论文,
   学位论文模板, 毕业论文模板, 学术简历, SCI论文, 投稿信, 期刊选择, LaTeX 模板,
   NSFC, ChineseResearchLaTeX, paper-sci, XeLaTeX 编译 | RED 必触发 |
```

真实 matcher 探针（`server._match_red_skill_triggers`）：

| 输入 | 返回 | 判读 |
|---|---|---|
| 帮我写基金和国自然标书 | `['nature-proposal-writer','academic-research','chinese-research-latex']` | 命中，重叠合理 |
| 我要写毕业论文，学校有模板要求 | `['chinese-research-latex']` | **独占** |
| 帮我写一份学术简历 | `['chinese-research-latex']` | **独占** |
| SCI论文投稿信怎么写 | `['nature-figure','nature-writing','chinese-research-latex']` | 命中 |
| LaTeX 模板怎么用 | `['chinese-research-latex']` | **独占** |
| 今天天气不错 | `[]` | **0 误触发**（反向对照） |

> 反向对照句必须带上——它证明的是"命中对了"，不是"嘴大命中多"。

---

## 2. 三个 FAIL 签名（逐条原文 → 根因 → 修法）

### 签名 A：`test_every_red_skill_is_covered`

```
AssertionError: 有 1 个 RED 技能没有任何路由用例：['paper-structured-extraction']
请在 fixtures/skill_routing_matrix.json 的 cases 里补一条真实用户口径的用例；
确属无法测试的（如纯运行期技能）写进 coverage_exempt 并给理由。
```
- **根因**：索引重建后 `paper-structured-extraction` 被解析为 RED（它有 skill.json），而 fixture 里从没有它的用例。
- **是否我引入**：否 —— `git show HEAD:webui/tests/fixtures/skill_routing_matrix.json | grep -c 'paper-structured-extraction'` → `0`（原始版本就没有）。
- **修法（实证有效）**：先探针选句 → 命中后抄进 cases：
  - `'帮我做深度结构化提取，禁止编造，所有数字必须来自原文'` → `['paper-structured-extraction']` ✅
  - 加 `{id:"paper-structured-extraction-01", intent:"直白", text:"<上面那句>", must_hit:["paper-structured-extraction"], max_hits:3}`
  - 修后：`test_skill_routing_matrix.py` 单跑 **全绿**。
- **不要**用 `coverage_exempt` 绕过——它是"无法测试"的出口，不是"不想测"的出口。

### 签名 B：`test_index_is_reproducible_from_committed_metadata`

```
AssertionError: 这些技能的 skill.json 还没入 git（全新 checkout 的索引会多行或少行）:
  ['paper-structured-extraction', 'r-namespace-and-package-conflicts']
```
- **根因**：这两个是**会话起始就未跟踪**的用户技能（起始 `git status` 快照：21 modified / 22 untracked）；本仓库历史提交里明确写着 `SKILLS_GATE=0: 未跟踪的用户技能 r-namespace... 不进提交`。
- **处置**：不动别人的 skill.json → 用 `SKILLS_GATE=0 git commit`，并在提交信息末尾原样说明：
  `(SKILLS_GATE=0: 残余 test_index_is_reproducible 失败源于未入 git 的用户技能 skill.json —— paper-structured-extraction / r-namespace-and-package-conflicts，预存非本次)`
- 回执：`[skills-gate] SKILLS_GATE=0，跳过技能门禁（KB 门禁照常执行）` → 提交成功。

### 签名 C：`test_task_routes.py` 同秒 id 碰撞（flaky）

```
AssertionError: assert 'qc-20261012-002751-7cb7' not in {'qc-20261012-002751-0559', 'qc-20261012-002751-7cb7'}
webui/tests/test_task_routes.py:998
```
- **判读**：整跑（并发负载高）时同一秒内建两个任务，id 后缀碰撞；`pytest webui/tests/test_task_routes.py -q` **单跑转绿** → flaky，与技能注册无关，**不要改代码**。
- 与此对应：整跑 `2 failed / 898 passed`（86–91 s），单跑两个技能文件只剩签名 B 一条。

---

## 3. 取数与检索纪律

- 门禁一次 ~90 s，**跑一次取汇总**；`pytest ... -q | grep -E "FAILED|passed|failed"`。
- 要看断言正文必须 `grep -E "^E "`：直接 `| tail -30` 会被 `DeprecationWarning`（`webui/server.py` 的 `on_event` 弃用警告，几十行）刷屏，断言被挤出窗口。
- 本 skill 的 `scripts/verify_skill_registration.py` 在 skill 自己的目录下，**不在项目根 `scripts/`**（写裸相对路径会 `can't open file`）。

## 4. 可复用的收尾顺序

```
① 写 skill.json（真数组 ≥10 条，禁斜杠串、禁逗号）→ ② --build → grep 索引行复核
③ matcher 探针（含反向对照：独占句 + 闲聊 0 命中）→ ④ 补/改路由用例（探针选句）
⑤ 单跑 test_skill_routing_matrix.py + test_skills_registry.py 拿汇总
⑥ 分流三个签名 → ⑦ git add 整目录（含 references/scripts）→ ⑧ SKILLS_GATE=0 提交并写明根因
```