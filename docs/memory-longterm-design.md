# MemOmics 记忆设计 v2（收敛版）

> 2026-08-11 重写。v1 是六层大架构（L0-L5），本轮根据两个输入收敛：
> ① 用户方向："优先保障单会话不受压缩影响、记住用户给的脚本/路径/文件；跨会话复用现有 memory，只加检索能力，不被跨会话记忆污染"
> ② 代码验证：Hermes 底座已有三个原生机制（on_pre_compress / memory_tool / volatile 段重建），不需要自研大工程。

---

## 0. 设计原则（三不做）

| 不做 | 为什么 | 替代 |
|---|---|---|
| L2 笔记层自动写（LLM 每回合总结） | 写入时机原生存在（on_pre_compress / commit_memory_session / sync_all）；科研要的是"事实"不是"洞见"，事实可规则提取；自动笔记 = 成本+噪音+幻觉污染 | 规则粗筛 + 用户确认 |
| L5 工作记忆块大改 | system prompt 三段结构（stable/context/volatile）+ 压缩时 invalidate+rebuild 已天然支持压缩免疫；大改 = 与 Hermes 上游分叉 + 高风险零增益 | 注册 memory provider 增量扩展 volatile 段 |
| 自研压缩回写钩子 | `on_pre_compress(messages) -> str` 返回值**原生进入压缩摘要 prompt**；回写 = 亡羊补牢 + 双份结论 | 直接用原生 `on_pre_compress` 让资产在压缩中存活 |

核心洞察一句话：**Hermes 的记忆设计已经就是"压缩免疫 + 事件驱动 + 全量画像注入"，MemOmics 只需要往这条管道里注入"科研资产"这一种内容，并加一条跨会话检索通道。**

---

## 1. Hermes 原生机制盘点（本轮代码验证结论）

### 1.1 system prompt 三段结构（`agent/system_prompt.py` build_system_prompt_parts）

```
stable   — 身份、工具引导、skills、环境提示（SOUL.md 所在层）
context  — AGENTS.md + caller-supplied system_message
volatile — memory snapshot（_memory_manager.build_system_prompt()）、用户画像、时间戳
```

- 首轮构建后**持久化到 session DB**（system_prompt 列），续轮从 DB 恢复（前缀缓存）
- **压缩时** `_invalidate_system_prompt()` + 重建 → volatile 段重新生成 → **记忆快照天然免疫压缩**
- `run_conversation(user_message, system_message=None, ...)` 支持每轮传入 system_message（conversation_loop.py:518）

### 1.2 MemoryManager（`agent/memory_manager.py` L353）

- builtin provider + **最多一个外部 provider**（`add_provider` 拒绝第二个）
- `on_memory_write(action, target, content, metadata)`：memory_tool add/replace/remove 时镜像给外部 provider（L874）
- `prefetch_all(user_message)`：按用户消息检索注入（记忆预取）
- `sync_all / queue_prefetch_all`：回合末后台同步（单线程 executor 串行）
- `build_system_prompt()`：生成 volatile 段记忆快照

### 1.3 MemoryProvider 钩子（`agent/memory_provider.py`）

- `on_pre_compress(messages) -> str`（L207）：**压缩前调用，返回值进入压缩摘要 prompt** —— 压缩免疫的官方挂载点
- `on_session_end` / `on_delegation` / `initialize` / `on_memory_write`：生命周期钩子齐备
- `get_tool_schemas()`：provider 可注册自己的工具（如检索工具）

### 1.4 压缩流程（`agent/conversation_compression.py`）

```
commit_memory_session(messages)      # 提交给记忆系统
_memory_manager.on_pre_compress(messages)  # 记忆提取 → 进压缩摘要
_invalidate_system_prompt() + 重建   # volatile 重新生成
protect_last_n                       # 保留尾部最近 N 条
```

---

## 2. 单会话：压缩免疫资产层（本设计核心）

**目标**：会话内用户提供的脚本、路径、文件等资产，**从提供时刻起持续在上下文中**，压缩、续轮、模型切换都不丢失。

### 2.1 资产生命周期

```
提取 ──▶ 确认 ──▶ 存储 ──▶ 注入 ──▶ 压缩免疫 ──▶ 失效/更新
```

**① 提取（规则粗筛，非 LLM 自动）**
- 挂 `enforcement.py` 现有 `tool_complete_cb`（或用户消息后处理）
- 正则匹配：路径模式（`[A-Za-z]:\\...`、`/...`、`~/...`）+ 文件扩展名（`.R .py .sh .csv .rds .h5ad .json .yaml` 等）+ **`os.path.isfile` 存在性校验**
- 命中 → 候选资产列表（去重）

**② 确认（防假阳性，防污染）**
- 候选非空时，回复中注入提示：`[检测到可能的项目资产：<path>。需要记住吗？/ 用途是什么？]`
- agent 转述给用户确认；用户确认或 agent 判断为项目资产 → 记入资产清单
- 不确认 → 丢弃，不进任何存储（**不自动写**）

**③ 存储（三级分桶，不串）**
```
会话级：results/<project>/<session_dir>/assets.json
项目级：results/<project>/_assets/index.json      （跨会话用）
用户级：MEMORY.md（不动——仅存用户级稳定事实）
```
- 每条资产：`{path, name, ext, size, mtime, content_hash(前4KB md5), purpose, source_turn, first_seen, last_used}`
- `content_hash` 用于路径迁移后的模糊匹配（文件移动可找回）

**④ 注入（volatile 段扩展，每轮可见）**
- **挂载点（已验证）**：MemoryManager 唯一外部槽位已被 `holographic` 占用（config.yaml `memory.provider: holographic`，agent_init.py:1242）→ **不能注册第二个 provider**。holographic 是 MemOmics 自家插件（`plugins/memory/holographic/`），直接扩展它：实现 `system_prompt_block()`（MemoryManager.build_system_prompt() 循环调用每个 provider 的 `system_prompt_block()`，标签 provider 名）返回资产段 → 进 volatile 段
- **注入点唯一正确 = `system_prompt_block()`**（已排除其它两处）：① webui 每轮传 system_message 不可靠——续轮从 DB 恢复缓存 system prompt（`_stored_prompt_matches_runtime`），且压缩重建用的 system_message 是旧值；② messages 前缀会被压缩归档
- **资产变化时 `agent._invalidate_system_prompt()`**（资产增删低频，前缀缓存损失可接受）
- 返回格式：
  ```
  📌 会话资产清单（持续有效，直接引用路径）：
  1. E:\data\human_skeletal_muscle\scripts\01_qc.R — 单细胞 QC（用户 08-11 提供）
  2. E:\data\human_skeletal_muscle\data\counts.rds — 表达矩阵
  ```
- 上限 ≤10 条/会话（超出按 last_used 截断，防上下文膨胀）
- **变化时主动 `agent._invalidate_system_prompt()`**（资产增删频率低，前缀缓存损失可接受）

**⑤ 压缩免疫（已验证：保险 B 是唯一可靠机制）**
- **保险 B（主）**：压缩时 `_invalidate_system_prompt()` + `_build_system_prompt(system_message)` 重建（conversation_compression.py:554/615/652）→ volatile 段重新生成 → `system_prompt_block()` 再次执行 → 资产清单直接回来。**压缩只归档 messages，不销毁 system prompt 的生成源**
- ~~保险 A~~：`on_pre_compress(messages)` 返回值在 conversation_compression.py:578 **被丢弃**（未拼进压缩摘要）——当前不可用；若未来启用需改 Hermes 一行（P2 可选补丁，遵循"不动底座"原则暂缓）
- ~~保险 C~~：不可靠（压缩重建用的 system_message 是旧缓存值，新资产不会进）——已删除

**⑥ 失效/更新**
- 资产路径 `os.path.isfile` 变 false → 标记 `missing`（不删，提示用户）
- 同名不同 hash → 更新（提示"文件已变更"）
- 用户显式"忘掉这个脚本" → 从清单移除（remove 走 memory_tool 镜像链）

### 2.2 不变量

- 用户提供的资产在提供后**任何时刻**都在上下文中（含压缩后、续轮后、模型切换后）
- 资产清单只增不减（除非用户显式移除），永不自动降级
- 资产引用格式始终带路径 + 用途，agent 直接可用的完整信息

---

## 3. 跨会话：复用现有 memory + 检索增强（防污染）

**用户判断**：现有 memory（MEMORY.md 全量注入 + holographic facts）"很大程度能帮助"。本设计只做两件事：**归档** + **检索**，不新建记忆体系。

**已验证的现有能力**（plugins/memory/holographic/__init__.py）：
- `fact_store` / `fact_feedback` 工具：facts 存储与反馈（memory_store.db，FTS5+HRR）
- `prefetch(query)`：按用户消息检索注入（跨会话检索通道已存在）
- `on_session_end` auto_extract：会话结束时自动提取事实（写入时机已存在）
- `on_memory_write`：memory_tool add 镜像为 facts

### 3.1 已有能力的复用（不做新东西）

| 现有能力 | 跨会话作用 |
|---|---|
| MEMORY.md 全量注入（volatile 段） | 用户级稳定事实（语言/工具偏好/项目方向）每会话在场 |
| memory_tool add/replace/remove | 会话中 agent 主动沉淀"用户级事实"（如"用户做人类骨骼肌衰老，用 R"） |
| skill_evolution（record_run/query_logs） | 脚本经验沉淀（参数+产出物路径） |
| search_knowledge | 知识库检索 |

### 3.2 新增：跨会话资产检索（唯一新能力）

**资产归档时机**：会话结束信号（on_session_end）/ 压缩 / 心跳定时（可选）/ 手动命令 —— 四路触发把会话级 assets.json 合并进项目级 `_assets/index.json`

**检索工具**：`search_assets(query, project=None)`
- 在 holographic 的 `get_tool_schemas()` 新增一个 schema（与 fact_store 并列）→ agent 在用户提到"上次的脚本/之前的文件"时调用
- FTS5（复用 memory_store 的 FTS 模式）按 path/name/purpose 匹配 + 按 last_used 排序
- 返回 ≤5 条：`{path, purpose, source_session, first_seen}`
- **资产存 memory_store 新表**（`assets` 表：path/name/purpose/content_hash/source_session/last_used），与 facts 表并列，不污染 facts

**防污染护栏（呼应记忆跳步 bug 修复 · 铁律规则-1）**：
1. 检索结果注入上下文时**强制带来源标记**：`[历史会话资产 · 仅供参考]`——不可冒充本次会话事实
2. **绝不因检索结果跳过本次对话确认**（语言、方向、参数都照常问）
3. 检索结果只用于"定位资产"，使用前必须经用户确认（"是这个文件吗？"）
4. 跨项目隔离：`project` 过滤缺省 = 当前项目；跨项目检索必须显式声明
5. 项目锚点降级链只用 `git_repo_root → results/<project> 目录名`（**删除 cwd 与 results 根兜底**——v1 审查的结论）

---

## 4. 实施落点

| # | 改动 | 位置 |
|---|---|---|
| P0-1 | 资产提取/确认/存储模块（规则匹配 + memory_store `assets` 表读写） | `webui/` 新文件 `asset_memory.py`（或并入 enforcement） |
| P0-2 | holographic 扩展：`system_prompt_block()`（资产段）+ `search_assets` 工具 schema + 资产 CRUD | `memomics/hermes-agent/plugins/memory/holographic/__init__.py` |
| P0-3 | 资产变化 → `agent._invalidate_system_prompt()` 钩子 | server.py `_trigger_agent_turn` |
| P0-4 | 会话结束（on_session_end）→ 项目级资产索引合并 | holographic `on_session_end` 扩展 |
| P1-1 | 测试网：压缩免疫（构造压缩场景断言资产在 volatile 重建中）、确认流程、检索隔离 | `webui/tests/test_asset_memory.py` |
| P1-2 | 前端：资产清单展示（会话侧栏"📌 资产"）+ 确认交互 | `webui/index.html` |

## 5. 验证点（已完成，2026-08-11）

- [x] **on_pre_compress 返回值**：conversation_compression.py:578 调用后**未拼接进压缩摘要**（docstring 声称可用，实际未接线）→ 保险 A 不可用，已从设计移除
- [x] **压缩重建 system_message 来源**：`_build_system_prompt(system_message)` 用的 system_message = 压缩前缓存的旧 system prompt（L409 注释 "Current system prompt; rebuilt after compression"）→ caller 每轮 system_message 不可靠，**注入点必须是 provider 的 system_prompt_block()**
- [x] **MemoryManager 外部槽位**：已被 `holographic` 占用（config.yaml:20 + agent_init.py:1242）；MemoryManager 硬限制只允许一个外部 provider（L386-403）→ **扩展 holographic 自身**，不注册第二个
- [x] **续轮 system prompt 恢复**：`_restore_or_build_system_prompt`（conversation_loop.py:277）——续轮从 session DB 恢复缓存 prompt（前缀缓存），仅 runtime 身份变化才重建 → 资产变化必须显式 `_invalidate_system_prompt()`

## 6. 不做清单（明确排除，防范围蔓延）

- ❌ LLM 自动写笔记/总结（无用户确认不写任何记忆）
- ❌ embedding/rerank 检索（FTS5 起步，有失败样本再升级）
- ❌ 修改 Hermes 底座（memory_manager / system_prompt / compression 一律不动）；唯一例外：扩展 MemOmics 自家插件 holographic（`plugins/memory/holographic/`，不算底座）
- ❌ MEMORY.md 自动写入（资产不进全局画像，防污染）
- ❌ 跨会话目标/进度注入（只注入已完成的**事实**，不注入**目标**——防诱导延续旧任务，违背铁律-5）

---

## 7. 三问补充设计（2026-08-11，用户三问 + 业界调查）

> 触发：用户提出三个核心问题（①几十轮对话怎么记住之前内容 ②用户每次对话提供的信息/诉求怎么记住 ③怎么用意图识别找记忆——话题切换检测 + "继续跑热图"式旧资产召回）。本轮补充代码验证 + 业界调查（Letta/MemGPT memory blocks、Anthropic Context Engineering、Claude auto-compact、mem0），结论：**Hermes 现有机制已覆盖业界全部组件，缺的是"接线"而非"新建"**。

### 7.0 业界对照表（调查结论）

| 业界模式 | 代表 | Hermes 对应（已验证） | 差距 |
|---|---|---|---|
| Core memory（常驻块，永不检索） | Letta memory blocks（label+description+value+limit，XML prepend，agent 可读写） | volatile 段 `system_prompt_block()` | 缺"任务状态块"和"诉求块"两块内容 |
| Compaction（近满自动压缩） | Claude auto-compact / MemGPT | `compress_context`（50% 阈值，auxiliary LLM 总结 middle） | 无（已强） |
| 压缩保留细节（路径/命令/输出） | Claude（保留最近+摘要） | **`_collect_path_mentions` limit=12 + 总结 prompt 明确要求保留路径/命令/输出**（context_compressor.py:223/1330） | 无（已强，超出预期） |
| Recall memory（对话历史检索） | MemGPT recall / mem0 session | **SessionDB FTS5 `search_messages`（messages_fts + trigram 中文，`include_inactive=True` 可搜压缩归档）** | 未暴露给 agent（无工具） |
| Archival memory（外置向量库） | MemGPT archival / mem0 | holographic facts（FTS5+HRR，trust 评分） | 无（已有） |
| Structured memory 注入 | Anthropic agentic memory | `prefetch_all(user_message)` 每轮 pre-turn 按消息检索 facts 注入 | 只搜 facts，不搜资产/历史；query 无意图增强 |
| Self-editing memory（agent 自主写） | Letta memory tools / mem0 ADD | `memory_tool add/replace/remove` + holographic `on_session_end` auto_extract | 会话内诉求无即时捕获 |
| 意图驱动检索 | mem0（按对话上下文检索） | `_classify_intent` 每轮执行（server.py:6520）+ `_detect_domain_from_text` 每轮话题检测 | **无"意图→多源检索"管线** |

### 7.1 问题 1：几十轮对话怎么记住之前内容 —— 三层答案

**第 1 层 · 常驻（core memory）**：资产清单 + 任务状态块在 volatile 段**常驻**，压缩免疫（v2 §2.1 ⑤已验证）。几十轮后这两块仍在上下文。

**第 2 层 · 压缩（已有，勿动）**：middle turns 压缩为摘要（**路径/命令/输出细节被原生保留**）+ 尾部 `protect_last_n=20` 保留 + 旧 turns **soft-archive 磁盘保留**（active=0）。**压缩不销毁任何内容。**

**第 3 层 · 检索（新增 P1-3）**：把 `SessionDB.search_messages`（FTS5 + trigram 中文，`include_inactive=True`）暴露为 agent 工具 `search_history(query, session_id)`——被压缩归档的内容按需召回。这是"几十轮后找回细节"的最终兜底。

**新增：任务状态块（Task State Block，P0-5）**——Letta scratchpad 模式，volatile 段加：
```
📋 当前任务状态（会话内，任务切换时更新）
- 当前任务：QC → 聚类注释（第 3 步/共 6 步）
- 正在使用：E:\data\...\scripts\01_qc.R
- 最近产出：results/.../figures/umap.png
- 最近结论：<一句话>
```
webui 侧维护（enforcement 里程碑 + 工具完成钩子更新），**会话内注入不违背"跨会话不注入目标"**（那条约束只针对跨会话）。

### 7.2 问题 2：用户对话中的信息/诉求怎么记住 —— 两分类

**事实类**（路径/脚本/文件/参数）：v2 §2.1 资产管线（规则提取→用户确认→assets 表→volatile 注入）✅ 已设计。

**诉求类**（用户要什么/偏好/约束）——**新增：诉求捕获（P0-5）**：
- 每次用户消息：`_classify_intent` 结果 + 规则提取诉求（动词+实体："继续跑热图"→`{intent: analysis, entity: 热图}`）
- 写入会话级 `user_requests.jsonl`（results/<session_dir>/）
- **升级规则**：用户明说"记住/以后都这样" 或 同一诉求重复 ≥2 次 → 提升为 facts（holographic，跨会话带 trust）——对应 mem0 user-level 记忆
- 注入：最近 3 条诉求进 volatile（Letta human block 模式），让 agent 始终知道用户最近要什么

### 7.3 问题 3：意图识别找记忆 —— 两个场景

**场景 A · 话题切换（用户突然问别的，MemOmics 还在答旧的）**
- 现状：`_classify_intent` 每轮执行 + `_detect_domain_from_text` 每轮检测（L6513 注释"不仅是第一条消息，随时切换"）——**机制已有**
- 补（P1-4）：**切换检测旁路**——本轮 intent/domain/实体 vs 任务状态块不一致 → ①更新任务状态块 ②回复注入一句"检测到话题切换：从『QC』切到『知识问答』"（chat/knowledge_ask 类不用确认，analysis 类直接按新意图执行，不阻塞主流程）

**场景 B · 旧资产召回（几十轮后"继续跑热图"）**——**意图→多源检索管线（P0-6，本设计核心新增）**：
```
用户消息 "继续跑热图"
  → _classify_intent → analysis/direct_exec（规则已命中"跑"）
  → 实体提取：热图
  → 检索 query = 实体 + 意图（三源并行）：
     ① assets 表：purpose/name 匹配 "热图"（会话资产+项目资产）
     ② search_messages：会话历史 FTS 命中"热图"轮次（含压缩归档的）
     ③ facts：跨会话用户级（"用户常用 pheatmap"）
  → 命中 → 注入 agent 上下文，带 [历史上下文 · 仅供参考] 标记
  → agent 向用户确认："是 E:\data\...\scripts\heatmap.R（上次 08-10 提供）吗？"
  → 不命中 → 不注入，正常问用户（零污染）
```
- **挂载点**：扩展 holographic `prefetch_all`（每轮 pre-turn 已调用）——query 用 `_classify_intent` 实体增强，检索源加 assets + 会话历史（原只搜 facts）
- **防污染护栏**（沿用 v2 §3.2）：来源标记 + 绝不跳过确认（规则-1）+ 项目隔离

### 7.4 新增实施项（追加到 v2 §4 路线图）

| # | 改动 | 位置 |
|---|---|---|
| P0-5 | 任务状态块 + 诉求捕获（user_requests.jsonl + volatile 注入 + 升级 facts） | webui 新模块 `session_state.py`（enforcement 里程碑钩子更新） |
| P0-6 | 意图→多源检索管线（扩展 holographic prefetch：实体增强 query + assets/history/facts 三源） | `plugins/memory/holographic/` + `_classify_intent` 输出接口 |
| P1-3 | `search_history` 工具（SessionDB FTS 暴露，include_inactive=True） | holographic `get_tool_schemas` 新增 |
| P1-4 | 话题切换检测旁路（intent/domain vs 任务状态块不一致→更新+提示） | webui server.py ws chat 分支（L6520 附近） |

### 7.5 验证点（实施前）

- [ ] holographic `prefetch_all` 的注入位置确认（run_agent.py:3378 附近 pre-turn 调用链）
- [ ] `search_messages` 对**当前会话**是否可用（source_filter 参数语义，inactive 消息是否含压缩归档）
- [ ] `_detect_domain_from_text` 现有实现（domain 是否够细粒度做切换检测）
- [ ] 任务状态块注入后对 token 的增量（目标 ≤300 字符）

---

## 第 8 章 实施记录（2026-08-11，P0 落地）

P0-5 + P0-6 已实施并全量回归通过（198 passed）。

### 已落地（对应 §7.4）

| 项 | 实现 | 文件 |
|---|---|---|
| P0-1 assets 表 | `assets`（name/path/kind/purpose/session_id/project/status/source/content_hash/use_count/last_used_at）+ `assets_fts`（FTS5 external content + ai/ad/au 触发器）+ `session_state`（task_json/requests_json） | `hermes-agent/plugins/memory/holographic/store.py`（顶层与 `memomics/` 副本同步） |
| P0-2 store 方法 | `add_asset`（(name,path,session_id) 去重）/ `search_assets`（FTS + LIKE 兜底，confirmed 默认隔离，last_used_at 排序）/ `confirm_asset` / `mark_asset_used` / `list_assets` / `has_asset` / `get_session_state` / `update_session_state`（部分更新） | 同上 |
| P0-3 注入 | `system_prompt_block()` 追加"📌 会话资产清单"（本会话 confirmed ≤10 条，volatile 段压缩免疫）；`prefetch()` 四源：facts + Related Assets（跨会话，带"仅供参考"与来源会话标注）+ Related History（本会话，trigram FTS/LIKE，含压缩归档）+ 任务状态/诉求块 | `hermes-agent/plugins/memory/holographic/__init__.py` |
| P0-5 诉求捕获 | `capture_user_request`：实体提取（关键词表）+ 升级规则（明说"记住"或同 entity 第 2 次 → 写 facts category=user_request）+ 60s 同文本去重 + 最近 20 条上限 | `webui/session_state.py` |
| P0-5 任务状态 | `update_task_state` 字段级合并（空值不覆盖） | 同上 |
| P0-6 资产提取 | `extract_assets`：盘符/扩展名正则 + `os.path.isfile` 存在性校验 + `has_asset` 去重，status=pending 待确认 | 同上 |
| 挂钩 | server.py ws chat 分支（`_classify_intent` 后）调用 capture + extract，双路径 import + try/except 静默 | `webui/server.py` |

### 关键坑（实施中发现）

1. **两份 hermes-agent 副本**：`E:\MemOmics-Agent\hermes-agent\`（运行环境实际使用，含"共享连接注册表"新架构）与 `memomics\hermes-agent\`（旧架构副本）独立演化——改动必须两份同步，但**不能整文件覆盖**（顶层 shutdown 是 refcount 版，memomics 是直接 close 版）。
2. **`SessionDB.search_messages(source_filter=...)` 的 source 是渠道类型**（cli/webui），不是 session_id——按会话过滤必须只读 SQL 直查 `messages` 表（`m.session_id = ? AND (m.active = 1 OR m.compacted = 1)`），压缩归档消息仍可搜。
3. **中文检索**：unicode61 FTS 按单字分词，句子 AND 连接过度严格 → 查询侧 `_extract_query_keywords` 去动词噪声词（"继续跑热图"→"热图"）；2 字符查询走 LIKE 兜底；≥3 字符用 `messages_fts_trigram`（CJK 子串原生）。
4. **JSON→heredoc 转义地狱**：`\n` 经工具参数 JSON 层解码为 `\n`，再经 Python 字面量变换行——修复脚本必须用 `chr(92)` 构造反斜杠。
5. 升级重复计数 bug：`len(same_entity) >= 2` 漏算当前条 → 修正为"此前已出现过（≥1）即升级"；60s 去重必须检查**最近 5 条**而非最后一条。

### 验证

- `webui/tests/test_session_memory.py`：25 用例（store 层 / 模块层 / 注入层 / 生产兼容），全绿
- 全量回归：`198 passed, 1 skipped, 3 deselected`，exit 0（未破坏既有功能）
- 生产库补表无损：真实 `hermes_home/memory_store.db` 打开自动补 assets/session_state，68 条 facts 原样保留

---

## 第 9 章 实施记录 2（2026-08-11，P1-3/P1-4 + 记忆能力连接盘点）

### P1-3 search_history 工具（已实施）

- `SEARCH_HISTORY_SCHEMA` 加入 `get_tool_schemas`（query/limit/session_id 参数）
- `_handle_search_history`：检索本会话（或指定会话）用户消息，返回带"仅供参考，用前请与用户确认"标记
- 查询逻辑抽成模块级 `_search_session_messages(sid, query, limit)`（trigram FTS ≥3 字符 + LIKE 兜底 + `(active=1 OR compacted=1)` 含压缩归档），prefetch Source 3 也改用它——单一实现

### P1-4 话题切换旁路（已实施）

- server.py ws chat 分支：analysis/research_plan/direct_exec 意图 + 实体变化 → `update_task_state(entity=新实体, switched_from=旧实体)`
- holographic Source 4 渲染："⚠️ 话题已切换：热图 → umap（旧任务暂停，以用户最新诉求为准）"
- 每轮 prefetch 注入，agent 感知切换不继续旧任务

### Hermes 记忆能力连接盘点（14 个 Provider 接口）

| 接口 | 连接状态 | 说明 |
|---|---|---|
| system_prompt_block | ✅ | facts 提示 + 会话资产清单（volatile 压缩免疫） |
| prefetch | ✅ | 四源：facts/assets/会话历史/任务状态+诉求 |
| queue_prefetch | ⚠️ 未实现 | 异步预取优化路径；同步 prefetch 已连，影响小 |
| sync_turn | ✅ | 显式工具模式（不自动同步，设计如此） |
| get_tool_schemas | ✅ | fact_store + fact_feedback + search_history |
| handle_tool_call | ✅ | 三个工具分发 |
| on_turn_start | ⚠️ 未实现 | turn 计数/周期维护，非核心 |
| on_session_end | ✅（默认关） | auto_extract=false（防噪音），config 可开 |
| **on_session_switch** | ✅ **本次修复** | 重绑 `_session_id`——此前会话切换/压缩后资产清单与 session_state 错绑旧会话 |
| on_pre_compress | ⚠️ 未实现 | 新版已把返回值拼入压缩摘要（memory_context 参数，旧"被丢弃"认知已过时）；资产靠 volatile 重建免疫压缩，摘要不叠加资产（防双份） |
| on_delegation | ⚠️ 未实现 | 子代理任务观察，非核心 |
| on_memory_write | ✅ | 内置记忆写入镜像为 facts |
| shutdown | ✅ | refcount 共享连接安全关闭 |
| save_config/get_config_schema | ✅ | config schema 暴露 |
