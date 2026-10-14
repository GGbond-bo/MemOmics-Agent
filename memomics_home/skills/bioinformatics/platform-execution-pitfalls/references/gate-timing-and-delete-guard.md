# 门禁时序与删除确认（2026-10-12 实测）

本文记录三类**与代码正确性无关、纯粹由平台门禁时序引发**的阻塞，以及可直接照抄的替代配方。
场景来源：安装外部项目 + 新建技能的一轮长任务（重复出现 2 次，值得固化）。

---

## 1. `ask_user` 发出后，执行类工具全被拦（连验证也拦）

### 现象（原文）
弹完「TeX 要不要装」的意图确认表单后，想补跑当轮验证：

```
⛔ 意图还没确认，先别执行：你已经用 ask_user 问了用户「…」，但用户还没回答（或还没提交勾选）。
现在必须做的：结束本回合等用户答复。不要再尝试调用 terminal 或任何执行/产物工具。
解除方式：① 用户在确认弹窗里勾选并提交；② 用户直接在输入框回复（也算答复）；③ 30 分钟内无人答复则门禁自动失效。
```

同一轮内连续两次调用都被同一条拦下（`terminal`；`execute_*`、产物类工具同理）。

### 顺序铁律
**先把当轮验证跑完，再弹确认表单。** 规划一个任务时把顺序排成：

```
探查(只读) → 改动 → 验证(pytest/静态检查/产物核验) → 弹 ask_user（若有高代价决策）→ 结束本回合
```

### 已被拦住时的正确姿势
1. **不要重试**（重试同一条拦截，白烧 token，还会被系统判"循环失控"）；
2. 如实说明**具体阻塞点**给用户（把门禁原文贴出来），明确"这不是代码问题"；
3. 给一张**证据边界表**：`已有证据（改动后实跑过的回执）` vs `缺什么（被拦住的验证）`；
4. 明确列出解除条件与"你一回复我就立刻做什么"（例：① pytest 出汇总行 ② `bash -n` + JSON 解析 ③ 若有红带原文定位）。

> 反面教训：不要因为"应该验证"就反复戳被拦的工具——系统判循环后会把整轮回答打断。

---

## 2. 铁律 24 的 pending 标记只认 `record_run`

### 现象（原文）
terminal 执行失败后，按铁律调了 `skill_evolution(action="record_error", …)`（返回 `success: true`），
**下一条 terminal 仍被拦**：

```
⛔ 上一步 terminal 完成后未记录经验（铁律）。请先调用 skill_evolution(action='record_run') 沉淀经验，再执行下一步。
```

即：`record_error` 写入错误日志成功，但**不清除 pending 标记**；清除它的是 `record_run`（action 名也接受 `record_success`）。

### 配方
```
terminal 失败
  → skill_evolution(record_error, error_message=报错原文, root_cause=…, fix_applied=…, severity=…)
  → skill_evolution(record_run,   result_summary="本轮实际做了什么 + 拿到的回执")   # 清标记
  → 继续下一条 terminal
```
`record_run` 的 `result_summary` 要写**事实回执**（命令、返回的关键行、失败点），不要写"已完成"这种无信息量的句子。

### 相关：同脚本同日同参数会被去重
`record_run` 对**同一天 + 同脚本名 + 同参数**会返回 `重复运行记录已跳过 (deduplicated: true)`——
这仍算"已完成记录"（标记被清）。所以连续多轮不要用同一个 `script_name`+`params_used`，
否则日志里看不出每轮实际差异；换 `script_name` 或写清差异参数。

---

## 3. `rm -rf` 被删除确认门禁拦下（并诱发 eval 报错）

### 现象（原文）
```
[⚠️ 操作需确认] 你刚才尝试执行删除操作。
📋 要执行的命令: mkdir -p … && cd … && rm -rf ChineseResearchLaTeX && …
⛔ 此操作未被直接执行。请先向用户展示: 1. 列出要删除的具体文件和目录
/usr/bin/bash: eval: line 16: unexpected EOF while looking for matching `''
```
要点：
- **整段命令未执行**（`rm -rf` 之前的部分也没跑），后续 `&&` 链全部作废；
- 命令里用 `\` 续行的多行串在这条错误里更容易触发 `unexpected EOF` 之类的 shell 解析错。

### 配方（照抄）
1. **不删任何东西**：克隆/解包到**独立目录名**（`CRL_gh` / `CRL_gitee` / `CRL_tar`），成功后 `mv` 到目标名；
2. 需要"重装"就先判断存在性（`[ -d "$REPO/.git" ] && echo 已存在，跳过`），而不是先删再装；
3. 确需清理 → 在 `ask_user` 里列清要删的路径、等用户点头；
4. **命令形态**：把多步逻辑写进一个 `.sh` 文件（`write_file`）再 `bash 脚本` —— 规避 eval 包装、可复用、可被 `bash -n` 静态检查；
5. 涉及 GitHub 克隆时同时准备三级回退：`GitHub(GIT_SSL_BACKEND=openssl) → 镜像站 → tarball`，把"用了哪条路"打进回执（例：`CLONE_SOURCE=gitee`）。

---

## 4. 与本 skill 其它章节的关系

- 串行门禁、铁律 26 强制协议 → 本 skill 正文「坑 -1」与末尾强制协议；
- 验证回执纪律（pytest 汇总行才算绿、`[skills-gate]` PASS 行为权威）→
  `references/verification-and-commit-gating.md`；
- 新建技能后的注册/触发/门禁分诊 → `skill_view("skill-registration-and-routing")`
  及其 `references/gate-failure-triage.md`。