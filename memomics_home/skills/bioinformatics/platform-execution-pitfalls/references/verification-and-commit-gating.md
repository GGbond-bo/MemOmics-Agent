# 测试证据与提交门禁（MemOmics 仓库改代码后的收尾纪律）

> 来源：2026-10-08 集群/环境管理特性提交实测。适用于**任何改 `webui/`、`memomics/`、`memomics_home/skills/`
> 的会话**——不是某个任务的专属经验。

## 一、什么算"测试绿了"——只有汇总行算证据

❌ **不算证据**：
- 命令的 `exit_code`（尤其 `.venv/Scripts/python.exe -m pytest ... | tail -N` 这种管道——返回的是
  `tail` 的退出码，不是 pytest 的）；
- 进度条跑到 `[100%]`；
- "没看到 FAILED 行"（`tail` 截断会漏掉总结区）。

✅ **算证据**：输出里出现**字面的 pytest 汇总行**，形如：
```
254 passed, 2 skipped in 14.30s
892 passed, 2 skipped in 82.6s
```

**坑（实测）**：`.venv/Scripts/python.exe -m pytest <files> -q -p no:warnings 2>&1 | tail -18`
连续两次都**没有**汇总行（输出停在 `[100%]` 的进度条）。**去掉 `-q`** 后再跑，同一组测试正常吐出
`254 passed, 2 skipped in 14.30s`。

**收尾动作**：拿到汇总行之前不要写"验证通过"；写不清楚就照实说"只拿到 exit 0，未见汇总行"。
（平台侧会把"凭退出码声称通过"标记为 unverified，反复如此会消耗用户信任。）

## 二、`.githooks/pre-commit` 会自动跑 skills-gate（免手写门禁）

暂存区**只要涉及技能面文件**（`memomics_home/SKILLS_INDEX.md`、`memomics_home/skills/**`、
`webui/server.py`、`webui/tests/fixtures/skill_routing_matrix.json` 等），`git commit` 会自动触发：

```
[skills-gate] 暂存区涉及技能面文件，跑门禁：
    memomics_home/SKILLS_INDEX.md
    ...
[skills-gate] PASS —— 索引一致（393 个技能：RED 69 / YEL 311 / GRN 13） · 测试通过（892 例，跳过 2）（82.6s）
```

要点：
- **`[skills-gate] PASS` 那行本身就是可直接引用的验证证据**（含测试例数与耗时），不必再手跑 `check_skills_gate.py`；
- 它**会硬拦 commit**（`[skills-gate] 提交已被拦下` → exit 1），失败时按 `skill-registration-and-routing` 的坑表修；
- 官方逃生阀 `SKILLS_GATE=0`，非必要不用；
- 所以"改动涉及技能面 → 提交即验证"，一次提交拿到一份权威回执。

### 两个实测盲点（2026-10-08 发现并修复 —— 之前门禁是**半失效**的）

1. **`SKILLS_GATE=0` 会连带关掉 KB 门禁**：原先它在脚本开头直接 `exit 0`，与本节注释自述的
   "两个开关各自独立"自相矛盾。已改为只跳过技能块 → **只关一个开关时另一个仍会跑**。
   实际含义：`SKILLS_GATE=0 git commit` **不等于**"这次提交不校验"，别拿它当通用逃生阀。
2. **KB 门禁其实从未触发过**（更严重）：`git diff --cached --name-only` **默认对非 ASCII 路径加引号**
   输出（`"memomics/knowledge_base/.../03_\346\265\213..."`），而 KB 五级目录的类别目录
   （`01_生物学知识` / `02_质控参数` / `03_测序方法`）**全是中文** → 下面 `^memomics/knowledge_base/`
   的锚点永远匹配不上，`KB_MATCHED` 恒为空。已改用 `-z` + `tr '\0' '\n'`（NUL 分隔，永不加引号）。
   **凡是按路径 grep 做门禁/白名单/归属判定处，都要按这条查一遍。**
3. **`export SKILLS_GATE=0` 会跨命令泄漏**：`terminal` 的 shell 状态在会话内持久 —— 一次
   `export SKILLS_GATE=0` 之后，**本会话所有后续 `git commit` 都在静默跳过技能门禁**，而回执照打
   `[skills-gate] SKILLS_GATE=0，跳过技能门禁`，很容易被读成"正常通过"。用完立刻 `unset SKILLS_GATE`；
   或写成**命令前缀**（`SKILLS_GATE=0 git commit ...`）——前缀只影响该条命令，不污染后续。

**非破坏性自检法**（改完 hook 必做，不产生提交）：
```bash
F="memomics/knowledge_base/Homo_sapiens/.../RNA/x.yaml"
printf '\n# gate-selftest\n' >> "$F"; git add memomics/knowledge_base/
SKILLS_GATE=0 sh .githooks/pre-commit        # 正向：应打印 [kb-gate] 暂存区涉及知识库文件且 exit 0
printf '\nbroken_field: [1, 2\n' >> "$F"      # 反向：坏 YAML
SKILLS_GATE=0 sh .githooks/pre-commit        # 应 exit 1 + [NEW-ERROR] ... yaml_parse_error
git reset -q && git checkout -- memomics/knowledge_base/   # 还原
```
改完 hook 先用 `bash -n .githooks/pre-commit` 过一遍语法（`patch` 手滑插进字面 `\r` 会让整段脚本报
`syntax error near unexpected token`）。

## 三、提交范围：先分清"本会话改的"与"历史遗留的脏"

工作区常带一堆**上个会话/并行写入方**留下的改动，直接 `git add -A` 会把无关工作扫进提交（违反
AGENTS.md「一个提交一件事」）。**先分类再暂存**：

1. `git status --short` + `git diff --stat` 看全貌；
2. 用 `git diff <file>` 逐条判断归属（本会话任务 vs 他人/历史）；
3. 只暂存本任务的路径，**不要**连带 `git add -A`；
4. 提交后 `git status --short` 复核剩余项，把未提交的**如实报给用户**（附一句"要不要补一个 commit"），不要静默忽略；
5. 大改动可拆多个 commit（例：`代码` 一个、`技能+注册+路由用例` 一个），每个 commit 都能独立过 gate。

**⚠️ 别用 `git commit -a` / `git commit -am`**（2026-10-08 实测踩到）：`-a` 会把工作区**所有已跟踪的修改**
一次性暂存 —— 你以为在提交 A 主题，实际把 B/C/D/E 一起扫进去，**提交消息与内容不符**，只能
`git reset --soft HEAD~1` 拆开重做。主题化提交一律显式 `git add <路径>`；也别指望 `-a` 带上
**未跟踪的新文件**（`references/*.md` 这类新增根本不会被暂存）。
安全姿势：`git add <本主题路径>` → `git diff --cached --name-only` 复核一遍 → 再 commit。
（这个字段列表本身就是 KB 门禁踩过的坑：中文路径会带引号，复核时用 `-z` 或眼睛认括号。）

**归属判据（实测）**：拿会话起始快照的 `git status` 计数对照，或按 mtime 分桶——别靠感觉认领改动。
本仓库预期之外的常见脏项：`memomics_home/skills/**` 的文档增补、`references/*.md` 未跟踪文件、
`memomics/knowledge_base/**` 的 yaml 更新。

## 四、注意：提交后文件可能被并行写入方改动

2026-10-08 实测：刚提交的 `remote-cluster-execution/SKILL.md` 与 `memomics-internals-qa/SKILL.md`
在提交后又被追加了内容（`git status` 重新变 `M`）。**不要当成自己的 bug 去回滚**，也不要顺手
`git checkout --` 抹掉——那会丢掉别人的增量。正确动作：读 diff 判断内容是否完整自洽 → 报告用户
→ 由用户决定是否补 commit。

## 五、`pytest` 覆盖不到的改动（shell 脚本 / 配置 / 门禁本体）——用**两段式**给证据

**别拿"pytest 覆盖不到它"当免证理由**：改了 `webui/`、`memomics/`、`.githooks/` 这类文件后，平台侧会
持续把该文件标成 `unverified`，直到你在那一轮真的跑出测试结果。对 shell / 配置 / 门禁本体这类
pytest 断言不了的东西，正确姿势不是放弃，而是**把证据拆成两层都摆出来**：

| 层 | 验的是 | 怎么做 |
|---|---|---|
| 上游（契约） | 它调用的东西没被改坏 | 全量 offline 套件：`.venv/Scripts/python.exe -m pytest -p no:warnings > log 2>&1; echo "PYTEST_EXIT=$?"` → 认**字面汇总行**（如 `2477 passed, 4 skipped, 25 deselected in 204.53s`）+ `PYTEST_EXIT=0`，两者一起才算证据 |
| 下游（本体行为） | 该跑时真跑、该拦时真拦 | 直接实跑那个脚本：正向 exit 0 且出现应有的回执行（如 `[kb-gate] 暂存区涉及知识库文件`）；反向（塞坏输入）exit ≠ 0 |
| 语法 | 别把脚本本身写坏 | `bash -n <脚本>` |

**一键跑语法 + 下游**：`scripts/selftest_commit_hook.sh`（非破坏性——只临时改一个 KB yaml 做靶子，
验完 `git reset` + `git checkout` 还原，不产生提交；正向 + 反向都查）。

汇报时**把两段式讲清楚**：说明「上游全绿 + 下游正/反向实跑通过」，并如实指出哪些是间接覆盖、
哪些是直接实跑 —— 比反复声称"已验证"可信得多，也不给不存在的证据。

**⚠️ 改 shell 脚本时 `patch` 的坑**：`old_string` / `new_string` 里**不要**夹字面 `\r`。
本仓库 `.githooks/pre-commit` 是 **LF** 结尾，插进去的 `\r` 会变成脚本里的真实字符，
bash 直接报 `syntax error near unexpected token ')'`，且只看 diff 很难发现。
**改完任何 shell 脚本，第一件事就是 `bash -n` 过一遍。**