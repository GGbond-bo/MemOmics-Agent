# 用户追问「这些你沉淀了嘛？」时的核实与补写（唤醒轮）

**来源**：2026-10-01 memomics-afd2d418 唤醒 #18 实测。用户在会话要求块里连着问过两次
（「**我以后可能会用到，这些你沉淀了嘛**」→ 下一轮「**你沉淀了吗？**」），而唤醒轮里我此前只回了一句
「要不要我讲给你听？」——**那是没答，不是答**。

## 0. 判据：这是「沉淀类追问」，不是闲聊

出现下列任一 → 本轮的实质交付 = **核实沉淀状态 + 缺什么补什么**，而不是再贴一次「等待用户」表：

- 用户要求里的「**这些 / 那个 / 之前说的**」+ 「沉淀 / 记住 / 存下来 / 以后可能用到」
- 用户点名某个具体结论要被保留（本轮 = FDR 列在 Excel 显示 `0.0000` 这件事）

## 1. ⛔ 别用 `session_search` 找中文原话

本轮实测：`session_search(query="我以后可能会用到，这些你沉淀了嘛", limit=3)`
→ `{"results": [], "count": 0, "sessions_searched": 0}`。

**中文长句会被 FTS 分词后匹配失败**；且 `sessions_searched: 0` 说明它连会话都没进去。
⇒ **0 命中 ≠ 用户没说过**（与 `search_files` 的「中文 pattern / 中文路径假阴性」同族）。
用户原话与「已确认」的事实**权威来源是注入的会话要求块 / MEMORY / 会话锚点**，其次才是检索。

## 2. 核实三步（缺一步就可能答错）

1. **读注入上下文**（会话要求块 / 记忆 / 锚点）—— 确认「这些」到底指什么，把用户原话里的**特征串**抄下来
   （本轮 = `FDR` / `0.0000` / `1e-51`）。
2. **扫沉淀位置**：`search_files(pattern='<特征串>', path='<hermes_home>')`
   —— 覆盖 `memories/MEMORY.md`、`skills/**`、`references/**`。
   本轮扫 0 命中 ⇒ **结论：确实没沉淀**（不是「可能沉过」）。
3. **核索引文件实际内容**：`read_file('hermes_home/skills/user-scripts/INDEX.md')` 等
   —— ⛔ 用**读到的行数/条目**回答，不用印象回答（本轮靠这一步才敢说「你要的那条没沉淀」）。

## 3. 分流写到哪里

| 内容性质 | 落点 |
|---|---|
| 环境 / 工具坑 / 数据格式 / 交付口径类**事实** | `memory`（一条 ≤150 字，带 `[imp:0.7]` 之类元数据） |
| 可复用**流程 / 配方 / 判据** | 对应 skill 的 SKILL.md 段落，或 `references/<topic>.md` |
| 用户提供的脚本（跑通 + 用户认可后） | `skills/plotting|comparison|statistics/<名>/` + `INDEX.md` + `git add` |

## 4. 唤醒轮的两个附带事实

- **`record_run` 的回执可能是 `query_logs` 形态**：本轮
  `skill_evolution(action='record_run', skill_name='wakeup_check_memomics-afd2d418')`
  返回 `{"action": "query_logs", "proven_runs": [], "summary": "无历史运行记录。skill … 尚未注册或目录不存在"}`。
  对 `wakeup_check_<sid>` 这类**临时核查名**属正常形态，**不代表记录失败** ⇒
  ⛔ 不要换措辞反复重试（赚循环告警）。要记就往**稳定 skill 名**上进一次。
- **只读核查轮的 `debate_reminder` / rail_review warning 是预期误报**（本轮：`未生成任何图片`、
  `No error handling`）：属静态文本类 ⇒ 不重跑脚本；无 ≥2 个活选项 ⇒ 按 **L0 跳过辩论**并写明理由
  （「辩完不改变下一步动作」）。