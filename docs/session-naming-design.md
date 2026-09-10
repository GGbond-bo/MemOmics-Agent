# 历史会话命名与目录识别设计（Session Naming & Identity）

> 状态：设计定稿（待实施）
> 调研对象：Hermes（本地 `hermes-agent`）、Reasonix（本机运行环境）、OpenAI4S（PKU-YuanGroup，GitHub main @ 2026-08-11）
> 目标：保证「会话目录 ↔ 会话」双向正确识别，目录永不丢、恢复永不找错

---

## 1. 三家调研结论

### 1.1 Hermes（本地 hermes-agent，MemOmics 底座）

- **会话 id**：`agent.session_id = f"{timestamp_str}_{short_uuid}"`，`timestamp_str = %Y%m%d_%H%M%S`、`short_uuid = uuid4().hex[:6]`
  → 形如 `20260811_023000_3f8a2b`（agent_init.py:1283-1290）
- **canonical 存储**：`~/.hermes/state.db`（SQLite，`hermes_state.py` 的 SessionDB），`sessions` 表字段：
  `id`(PK) / `title` / `display_name` / `parent_session_id` / `source` / `model` / `cwd` / `git_branch` / `git_repo_root` / `started_at` / `ended_at` / token 计数 / cost 字段 …
- **会话识别三要素**：`id`（唯一锚点）+ `title`（人类可读，可更新，`get_session_title`）+ **git 项目绑定**（`git_repo_root`/`cwd`/`git_branch`）
- **可选 JSON 快照**：`hermes_home/sessions/session_{sid}.json`（opt-in，`sessions.write_json_snapshots`，默认 False；state.db 是 canonical）
- **恢复**：`--resume` 按 session_id 查 state.db

要点：时间戳保证可排序，uuid 尾保证唯一；项目归属靠 git 三元组；快照只是外部工具便利，DB 是唯一真相。

### 1.2 Reasonix（本机运行环境）

- **目录结构**：`%APPDATA%/reasonix/projects/<workspace-slug>/sessions/`
  - workspace-slug = 路径转义（`<用户目录>\global-workspace` → `C--Users-<用户>-AppData-Roaming-reasonix-global-workspace`，`\` 与 `:` 转 `-`）
- **会话文件组**（同前缀多 sidecar）：
  - 主文件：`YYYYMMDD-HHMMSS.<微秒>-<provider-model>.jsonl`（如 `20260808-190919.562733500-dcs-glm-5.2.jsonl`）
  - sidecar：`.meta` / `.events.jsonl` / `.event-index.json` / `.goal-state.json` / `.telemetry.json` / `.recovery.json` / 分支 `.ckpt`（时间戳毫秒-模型名）
- **会话识别**：文件名时间戳（排序）+ 项目 slug 目录（归属）+ sidecar meta（机器真相）；`subagents/` 子目录挂子代理会话
- **迁移幂等**：顶层 `sessions/` 目录是一串 `.legacy-imported*` 空标记文件（v0→v1→v2→v3 逐代迁移标记），防止重复导入

要点：文件名只是索引，`*.meta` 才是可识别真相；同前缀 sidecar 是「一会话多文件」的最佳实践；命名格式演进用标记文件幂等迁移。

### 1.3 OpenAI4S（PKU-YuanGroup）

- **单一 SQLite Store**（`openai4s/store.py`，171KB facade）+ 仓储分层（`openai4s/storage/`，14+ 仓储，共享同一连接与可重入锁）
- **id 模式：语义前缀 + uuid 短片段，无时间戳**（时间戳只是字段）：
  - `fr_<uuid12>` frame（会话帧主干）、`ca-<uuid12>` compaction 归档、`hc-<uuid12>` host 调用审计、`note_`、`fold_`…
- **三重视角分离**（核心架构）：
  1. **Canonical history**：Action Ledger（`actions.py`）只追加，reducer 重放还原——不可变审计
  2. **UI/session projection**：frame / message / artifact head 可变视图
  3. **Workspace state**：`WorkspaceCAS` 内容寻址 blob + tree manifest（`snapshots.py`）
- **会话主干 = frame 层级**：`project_id` → frame → 消息；消息 `seq` 在 root frame 内单调，翻页用 keyset 游标（`before_seq`）而非 offset
- **branch/checkpoint**：`SessionSnapshotRepository` 保存 branch 信封、checkpoint、fork、操作日志；`checkpoint_state.py` 序列化 + **SHA-256 完整性摘要**；`branch_projection.py` 用不可变游标 + head 后新写 row 重建视角
- **恢复链（防断链设计）**：`compaction_archives` 归档时冗余存 `frame_id + summary + ledger_cursor + recovery_pointer + generation_id + context_before/after + artifact_refs`——压缩/归档后仍可精确定位回原会话
- **kernel generation**：环境+generation 引用+重放配方（非 pickle）

要点：机器稳定性优先（uuid 语义前缀）；「只追加历史 ↔ 可变投影」分离是审计与恢复的地基；归档必须带指针（cursor/pointer）防断链。

### 1.4 三家对照表

| 维度 | Hermes | Reasonix | OpenAI4S |
| --- | --- | --- | --- |
| 会话 id | `时间戳_uuid6` | 文件名 `时间戳.微秒-模型` | `语义前缀_uuid12`（无时间戳） |
| 存储 | SQLite state.db（canonical）+ 可选 JSON | JSONL 主文件 + sidecar 组 | 单一 SQLite Store + CAS blob |
| 项目归属 | git_repo_root/cwd/git_branch | 项目 slug 目录 | project_id 字段 |
| 恢复 | --resume 查 DB | .recovery.json + .goal-state + ckpt | Ledger 重放 + checkpoint 信封 + 归档指针 |
| 迁移 | 版本化 schema | 标记文件逐代迁移 | 版本化 migration + integrity_check + backup |
| 人类可读性 | id 含时间戳 + title 字段 | 文件名可读 | 靠字段/UI（id 不可读） |

---

## 2. 设计共识（三家交叉验证的规则）

1. **唯一锚点 + 可排序**：时间戳前缀（排序）⊕ uuid 尾（唯一）——Hermes/Reasonix 直接编码进 id/文件名；OpenAI4S 放弃时间戳导致排序必须查字段（教训：id 里带时间戳更省事）
2. **内容自描述**：文件名只是索引，**会话 id 必须冗余写在文件内容/sidecar 里**（Reasonix `.meta`、OpenAI4S 字段）——改名/迁移/复制后仍可识别
3. **项目归属是第一识别维度**：无归属的会话无法区分（三家分别用 git 三元组 / slug 目录 / project_id）
4. **恢复链不许断**：压缩/归档/快照必须带指针（OpenAI4S `ledger_cursor/recovery_pointer/generation_id`、Reasonix `.recovery.json`）
5. **迁移幂等**：格式演进用版本标记（Reasonix `.legacy-imported*`、OpenAI4S migrations.py）

---

## 3. MemOmics 会话命名设计（四层）

### 第 1 层：会话身份（沿用 Hermes 原生，不改）

- `session_id = %Y%m%d_%H%M%S_<uuid6>`（state.db canonical，`parent_session_id` 已支持会话链）
- 恢复入口不变：`--resume <session_id>` / state.db 查询

### 第 2 层：分析目录命名（新规范）

```
results/<project>/<topic-slug>_<YYYYMMDD-HHMMSS>_<hash8>/
  ├── session.meta.json        # 机器可读真相（强制）
  ├── log/                     # 归档日志（现状保留）
  └── ...                      # 产物
```

- `topic-slug`：主题拼音/英文短名（ASCII 安全，防跨平台/GBK 问题）
- `hash8`：topic+context 的短内容哈希（`_topic_hash` 前 8 位）——防同名 topic 碰撞
- **`session.meta.json` 必填字段**：
  ```json
  {
    "session_id": "20260811_023000_3f8a2b",
    "parent_session_id": null,
    "topic": "UMAP 分辨率参数选择",
    "topic_hash": "f24156ad",
    "project": "human_skeletal_muscle_aging",
    "model": "opencode-go/deepseek-v4-pro",
    "started_at": "2026-08-11T02:30:00+08:00",
    "git_repo_root": "<安装目录>",
    "git_branch": "master",
    "artifact_refs": ["log/debate_xxx.json", "figure1.png"]
  }
  ```
- 规则：**目录名 = 人类可读索引，`session.meta.json` = 机器可读真相；两者不一致时以 meta 为准**（恢复/列表一律读 meta）

### 第 3 层：子产物命名（语义前缀 + 短 id + 时间戳）

学 OpenAI4S 的语义前缀，保留 Hermes 的时间戳：

| 产物 | 命名 | 示例 |
| --- | --- | --- |
| 辩论归档 | `debate_<hash8>_<ts>.json` | `debate_f24156ad_20260811T023000.json` |
| 会话快照 | `snap_<session短id>_<ts>.jsonl` | `snap_3f8a2b_20260811T023000.jsonl` |
| reasoning_log | `reasoning_<hash8>_<ts>.jsonl` | `reasoning_f24156ad_20260811T023000.jsonl` |
| 恢复日志 | `recovery_<session短id>.jsonl` | `recovery_3f8a2b.jsonl` |

- **每个产物头部字段必写**：`session_id` + `topic_hash` + `created_at`（内容自描述，双保险）

### 第 4 层：恢复链与防断链

1. **落盘写指针**：快照/reasoning_log 写入时同步记 `recovery_<sid>.jsonl`（含最后消息游标/消息数，学 OpenAI4S recovery 日志）
2. **压缩/归档带指针**：compaction 记录冗余存 `{session_id, topic_hash, ledger_cursor, recovery_pointer, context_before/after, artifact_refs}`（对齐 OpenAI4S `compaction_archives`）
3. **孤儿检测**：启动扫描 `results/`，缺 `session.meta.json` 的目录标记 `orphan`（只标记不删除，供审计）
4. **一致性校验**：`session.meta.json` 的 `topic_hash` 与目录名 hash8 不一致 → 告警（改名/复制检测）

### 第 5 层：存量迁移（幂等）

- 一次性脚本给存量 `results/*/` 目录补 `session.meta.json`（从 log 归档/时间戳推断，推断不出记 `"session_id": null`）
- 迁移用标记文件幂等（学 Reasonix `.legacy-imported*`：`results/.meta-migrated-v1`）
- 迁移不删不改原文件

---

## 4. 实施点（MemOmics 代码落位）

| # | 改动 | 位置 |
| --- | --- | --- |
| 1 | 分析目录统一按第 2 层规范创建 + 写 `session.meta.json` | `webui/server.py`（分析启动路径） |
| 2 | 会话列表/恢复接口改读 meta 代替猜目录名 | `webui/server.py`（session/snapshot 相关） |
| 3 | 辩论归档补 `session_id` 字段 | `memomics/bio_tools/debate_analysis.py`（归档写盘处） |
| 4 | 快照/reasoning_log 写 recovery 指针 | `webui/server.py`（快照/缓冲/恢复模块） |
| 5 | 启动孤儿扫描 + meta 一致性告警 | `webui/server.py`（启动路径） |
| 6 | 存量目录补 meta 迁移脚本（幂等标记） | `scripts/` 或 `webui/tools/` |

实施顺序建议：1 → 3 → 4（先保证新会话正确）→ 2 → 5 → 6（存量收尾）。

---

## 5. 附：调研证据索引

- Hermes：`hermes-agent/agent/agent_init.py:1283-1306`（session_id 生成、logs_dir）、`hermes-agent/hermes_state.py:762-800`（sessions 表 DDL）、`:2012`（create_session）、`:3454`（get_session_title）
- Reasonix：`%APPDATA%/reasonix/projects/<slug>/sessions/`（实际文件组 + subagents/）、顶层 `sessions/` 迁移标记
- OpenAI4S：`openai4s/storage/README_zh.md`（仓储职责全景）、`openai4s/storage/metadata.py`（`note_{uuid12}`/`ca-{uuid12}`/`hc-{uuid12}` id 模式、compaction_archives 指针字段）、`openai4s/storage/frames.py`（frame 层级 + keyset 游标）、`snapshots.py`（WorkspaceCAS + SessionSnapshotRepository）、`checkpoint_state.py`（SHA-256 摘要）、`actions.py`（Action Ledger 只追加）

---

## 6. 用户改名机制（2026-08-11 追加）

> 背景：用户抱怨会话名太乱（列表全是"新会话"），要求支持用户改名，且**不得断**会话对接 / 会话目录 / 模型对接 / 心跳 / 后台。

### 6.1 可行性结论：能做到，且基础设施已齐

审计 `webui/server.py` + `hermes-agent/hermes_state.py` 实证：

| 链路 | 寻址方式 | 与 title 关系 |
| --- | --- | --- |
| 会话对接（恢复/续聊） | `_sessions[sid]`、`_restore_single_session(sid)`、state.db `ensure_session(sid)` | 无关（全按 sid） |
| 会话目录 | `_scan_results_dir_for_session` 按目录名末尾短 ID（`rename_results_dir` 先例） | 无关 |
| 模型对接 | `session["model_config"]` 独立字段 | 无关 |
| 心跳 | `.heartbeat_stop` 标记 + `_session_emit(session, ...)` 按 sid | 无关 |
| 后台任务 | `_bg_tasks[sid]` | 无关 |
| WebSocket 分流 | 消息自动注入 `session_id`（server.py L2575-2580） | 无关 |

**身份与名字早已分离**：`sid = memomics-<uuid8>` 是唯一 key（server.py L2628），`title` 只是展示字段。改名只写 title，所有链路天然不断。

Hermes 原生已备好改名后端（hermes_state.py）：
- `sanitize_title`（L3292）：消毒（控制字符/零宽/RTL 覆盖/超长）
- `set_session_title`（L3435）：改名；同名/非法抛 ValueError；空串归一化 None
- `set_auto_title_if_empty`（L3445）：自动命名且**不覆盖手动名**（事务内判断，防并发覆盖）
- `get_next_title_in_lineage`（L3551）：同名自动续号（"xxx (2)"）

### 6.2 "名字太乱"根源

- `_create_session(title="新会话")`（L2627）默认全叫"新会话"：**无自动命名、无用户改名入口**
- 现有 `rename-results` API（L3153）只改**目录名**（物种_组织_方向_日期_短ID），不改会话 title——用户混淆点

### 6.3 改名三原则

1. **名字是投影，sid 是身份**：改名只写 title 字段（内存 + state.db + meta.json），绝不动 sid / 目录名 / 文件名 / WS 路由 / 心跳 token
2. **canonical 单源**：state.db `title` 是权威；`_sessions[sid]["title"]` 与 `session.meta.json.display_name` 都是投影——启动/恢复以 DB 为准回填（`_restore_single_session` 处）
3. **改名可审计**：只追加 `rename_events`（新旧值 + 时间 + sid），学 OpenAI4S Action Ledger——可追溯可回滚

### 6.4 防断链保证（对应用户 5 个担忧）

| 担忧 | 保证 |
| --- | --- |
| 会话能正常对接 | sid 不变；state.db 按 id 查；改 title 不影响任何按 sid 的恢复/续聊路径 |
| 会话目录不断 | **目录名永不变**（改名只写 meta 内 `display_name`）；不学旧式"目录名=会话名"（os.rename 运行中目录有 Windows 句柄风险 + artifact_refs/recovery 指针全断） |
| 模型对接不断 | `model_config` 独立字段，title 无关 |
| 心跳不断 | `.heartbeat_stop`/`_session_emit` 按 sid 寻址 |
| 后台不断 | `_bg_tasks[sid]`、run_serial/batch 按 sid 引用 |

### 6.5 实施清单（预计半天）

- **A. 改名 API**：`POST /api/sessions/{sid}/rename` `{title}` → `sanitize_title` → 同名冲突捕获 ValueError 走 `get_next_title_in_lineage`（或允许重名）→ `db.set_session_title` → 同步 `_sessions[sid]["title"]` + meta.json → 返回新 title 供前端刷新
- **B. 前端入口**：会话列表标题旁 ✏️（index.html + JS fetch）；当前会话标题同步更新
- **C. 自动命名（治"太乱"根本）**：首条用户消息后 `db.set_auto_title_if_empty(sid, 首条消息摘要 ≤30字)`——事务保证不覆盖手动改名
- **D. 审计**：`rename_events` 只追加（webui/server.py 内小表或 JSONL）
- **E. 一致性回填**：`_restore_single_session` 用 DB title 覆盖内存/meta 投影
