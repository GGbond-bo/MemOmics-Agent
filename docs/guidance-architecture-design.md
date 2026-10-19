# MemOmics 引导体系设计（Guidance Architecture）

> 2026-10-19 · 调查 + 设计。对照系：DSH（DeepSeek Harness）引导机制。
> 回答三个问题：**多个引导怎么分、什么时候读、能不能被正确读取并反哺任务**。

---

## 1. 调查结论

### 1.1 DSH 的引导机制（参照系）

DSH 把引导拆成 5 个独立子系统，各有明确读取时机：

| 层 | 载体 | 读取时机 | 刷新机制 | 预算/保护 |
|---|---|---|---|---|
| 系统提示词段 | 插件贡献的有序段（order -100 身份 / 0 persona / 100-199 工具引导） | **每个 step 重组装** | `system-prompt/assemble` waterfall 协作修改 | 段级去重、complete 段唯一性校验 |
| 工作区指令 | `$DSH_HOME/AGENTS.md`（全局）+ 项目根→cwd 链 + `AGENTS.local.md` overlay | **首个 step**注入为持久 user 消息（system-reminder 框） | **touch 驱动**：read/write/edit 成功后发现嵌套文件、替换变更、通知删除；无 watcher | `maxBytes` 总预算：宽文件先丢、最具体文件截断；**绝不摘要**；同目录内容去重 |
| 技能目录 | skills catalog（name+description 摘要） | **会话开始**注入持久目录消息 | provider 失效事件 → 仅追加式目录替换 | 分层 provider（全局/预设层），调用策略分离 model/user |
| 技能全文 | SKILL.md | **按需**：模型调 `skill` 工具 / 用户 `/skill` 点名 | 加载即注入 `<skill_content>` 块 | 每技能独立文件，不占常驻预算 |
| 运行时记忆 | USER.md / MEMORY.md 快照 | **每轮**作为 runtime context | 写后下轮生效；容量到限自动归档压缩 | 字节预算投影 |

DSH 的核心思想：**「常注的小而稳，大的按需读；变更只追加不重写；预算显式、截断可见」**。

### 1.2 MemOmics 现状（实测）

MemOmics（hermes-agent 底座 + webui 层）实际是**三层注入 + 按需读取 + 代码铁轨**：

**A. Stable 系统提示**（会话创建时一次，`agent._cached_system_prompt` 缓存，仅压缩后重建）：
- SOUL.md（身份槽位，**51,395 字符**，安全扫描 + 动态截断）
- hermes 引导段（任务完成/并行调用/记忆/技能使用指导）
- hermes 原生技能索引 `build_skills_system_prompt()`（**25,217 字符 / 275 技能**）
- AGENTS.md（cwd 上下文：webui 未设 TERMINAL_CWD → 落在启动目录=仓库根，仓库根 AGENTS.md 会被加载）
- volatile：记忆快照、USER.md、时间戳

**B. 每轮 ephemeral**（server.py:19755，每轮重新赋值但内容字节稳定以保前缀缓存）：
- SOUL-detail.md（13.4K，**每轮重读磁盘**）
- SKILLS_INDEX.md（**71.6K 字符 / 98KB**，mtime 感知缓存）
- _PLANNING_PROMPT + _EXECUTION_POLICY + _REPLY_STYLE + 输出目录归位铁律 + 语言锁

**C. 每轮尾部 system 消息**（conversation_history 尾部，随用户消息变化）：
- `_build_skill_injection()`：显式 `/skill` 点名 > 置顶技能 > RED 必触发 > 意图路由指令
- `_semantic_trigger_block()`：语义判定纪律 + grill 前置
- `_build_kb_tail_injection()`：KB 预查询/领域路线引导（仅 heavy 意图）
- task_plan 上下文 / 主线恢复 / alerts.json / 记忆 digest / L0-L1 结论 / L2 速览 / 本轮唯一任务聚焦

**D. 按需读取**：`skill_view`（全文 + linked files）、`skills_list`、`skill_search`

**E. 代码铁轨**（enforcement.py）：rail_review 前后审查**硬阻断**、debate_gate 辩论门控、grill 澄清门禁、意图确认表单门禁、code_edit 门禁、辩论裁决→会话待办（blocks 硬约束）

**F. 生成端**：`skills_registry.py`（SKILL.md frontmatter + skill.json + SOUL 必触发表 → SKILLS_INDEX.md 单一口径整表重建）、`auto_register.py`（新技能自动落 skill.json + 索引 + SOUL 表）

**G. 测试钉住**：test_skills_registry（索引==磁盘、SOUL 对齐）、test_skill_trigger_contract（触发词契约）、test_skill_routing_matrix（路由矩阵）、test_task_convention

### 1.3 实测发现的问题（按严重度）

| # | 问题 | 证据 | 严重度 |
|---|------|------|--------|
| P1 | **SOUL.md 截断炸弹**：截断上限 = 模型窗口 × 4 × 0.06 字符。实测当前 1M 窗口不截（51,395/240,000）；**换 200K 窗口丢 7,989 字符（铁律 22-31.5 等 12 章）；换 128K 窗口丢 23,541 字符（22 章，含铁律 -7 子代理、-5 Session 隔离、-4 多源验证、分析执行 23 条全灭）**。config.yaml 未钉 `context_file_max_chars`，截断只有一条日志 warning，用户无感 | 实测 `load_soul_md()` 三档窗口对比 | 🔴 高 |
| P2 | **双轨技能目录重复注入**：hermes 原生索引 25K 字符（275 技能，stable 层）+ MemOmics SKILLS_INDEX 71.6K 字符（388 技能，每轮 ephemeral）——两套口径、两处维护、近 10 万字符每轮占位 | 实测两个构建函数输出 | 🔴 高 |
| P3 | **SOUL.md 是 51K 字符巨石**：身份、语言锁、触发规则、36+ 条铁律、画图策略、dsh-ui 规范、集群路径混在一个文件；且**会话中途编辑不生效**（缓存到压缩/新会话才重建） | 文件结构 + hermes 文档明示 | 🟡 中 |
| P4 | **每轮 ephemeral 约 90K+ 字符**：SOUL-detail 13.4K + 索引 71.6K + PLANNING/POLICY/STYLE。auto_register 每轮末尾自愈重建索引 → mtime 变化 → 整段前缀缓存失效 | server.py:19755 | 🟡 中 |
| P5 | **意图分类是 600 行关键词 if-else**，与 RED 触发词表、领域检测三处口径分散，误分类直接决定引导注入量 | server.py:5697-6106 | 🟡 中 |
| P6 | **SOUL 铁律 ↔ enforcement 代码无显式映射**：SOUL 改一条铁律，铁轨代码不会跟着变，靠人工同步 | 两文件对照 | 🟡 中 |
| P7 | 仓库根 AGENTS.md 依赖启动目录碰巧是仓库根才加载；换启动目录即静默丢失 | webui 不设 TERMINAL_CWD | 🟢 低 |

---

## 2. 目标设计：多引导分层体系

### 2.1 设计原则（从 DSH 学 + MemOmics 国情）

1. **一个引导一个职责**：每个文件回答「我是谁/现在该干什么/这个领域怎么干」中的一件事
2. **读取时机显式声明**：每个引导文件头部用 frontmatter 声明 `when`（always / intent:xxx / on-demand），代码按声明装配，不靠记忆
3. **常注的必须小**：常驻引导总预算 ≤ 30K 字符；超限**启动报警**而不是静默截断
4. **变更只追加可见**：任何引导被截断/省略/命中，都在前端可见（现在只有日志）
5. **引导即数据**：铁轨 checklist、审查点从引导文件生成，改引导 = 改行为，不再双轨维护

### 2.2 引导文件布局（memomics_home/）

```
memomics_home/
├── SOUL.md                    # L0 身份层：瘦身到 ≤8K 字符
├── guides/                    # L1 规则层：按场景分文件
│   ├── rules-core.md          #   最高优先级铁律（Session隔离/不撒谎/取消协议/多源验证）
│   ├── rules-execution.md     #   分析执行 23+ 条（仅 analysis_exec 注入）
│   ├── rules-debate.md        #   辩论门控/裁决落地（辩论场景注入）
│   ├── rules-plotting.md      #   画图分流决策树 + dsh-ui 规范（出图/展示意图注入）
│   ├── rules-output.md        #   输出归位/表格规范/报告规范（heavy 意图注入）
│   └── env-cluster.md         #   集群实测路径（涉集群关键词时注入）
├── SKILLS_INDEX.md            # L2 目录层：精简版（见 2.4）
├── SOUL-detail.md             # L2 补充层：维持现状（每轮 ephemeral）
└── skills/**/SKILL.md         # L3 按需层：skill_view 触发时读（现状不变）
```

**SOUL.md（L0）只留**：身份定义、语言锁定、引导地图（「执行类任务必读 rules-execution.md」这类指路）、最高优先级铁律的**一行式摘要**（全文在 guides/）。目标 ≤8K 字符 = 任何窗口永不截断。

每个 guides/*.md 头部声明：

```yaml
---
guide: rules-execution
when: intent:analysis_exec,direct_exec    # 或 always / keyword:集群,remote_cluster
max_chars: 15000
priority: 20                              # 预算不足时先丢低优先级
---
```

### 2.3 读取时机矩阵（核心问题：什么时候读什么）

| 引导 | 读取时机 | 注入位置 | 缓存策略 |
|---|---|---|---|
| SOUL.md（L0 瘦身后） | 会话创建一次 | stable 系统提示 | 会话级缓存；压缩后重建（现状） |
| AGENTS.md（仓库根） | 会话创建一次 | stable context 层 | 现状；另钉 TERMINAL_CWD 防启动目录漂移（P7） |
| guides/rules-core.md | **每轮** | ephemeral 基础段（字节稳定） | mtime 缓存 |
| SOUL-detail.md | 每轮 | ephemeral 基础段（现状） | mtime 缓存（补上，现在每轮读盘） |
| SKILLS_INDEX.md 精简版 | 每轮 | ephemeral 基础段（现状） | mtime 缓存（现状） |
| guides/rules-execution.md | **仅当** 意图=analysis_exec/direct_exec | 尾部 system 消息（随意图变化的内容本来就在尾部，不伤前缀缓存） | mtime 缓存 |
| guides/rules-debate.md | 仅当 debate_gate 判定要辩论 | 尾部 system 消息 | mtime 缓存 |
| guides/rules-plotting.md | 仅当命中出图/展示类触发词 | 尾部 system 消息 | mtime 缓存 |
| guides/rules-output.md | heavy 意图 | 尾部 system 消息 | mtime 缓存 |
| guides/env-cluster.md | 命中集群关键词/remote_cluster 工具 | 尾部 system 消息 | mtime 缓存 |
| SKILL.md 全文 | RED/置顶/显式命中 或 模型自主 skill_view | 工具结果（现状） | 无（按需） |
| KB 预查询/记忆 digest/结论层 | 每轮（现状） | 尾部 system 消息 | 现状 |

**关键论点**：现状把「轻量意图省上下文」和「前缀缓存稳定」对立过一次（2026-08-21 事故），当时的解法是全部塞进 ephemeral 统一基础段。本设计用**第三个注入位**解决这个对立：意图相关引导走**尾部 system 消息**（与 KB tail 同一位，缓存安全已验证），只有字节稳定的小文件留在 ephemeral。于是「闲聊不带执行铁律」重新变得可行。

### 2.4 SKILLS_INDEX.md 精简（P2）

现状 71.6K 字符全量表每轮注入。改为两段式：

- **每轮注入段（≤15K 字符）**：RED 行全量（触发词完整，匹配代码要用）+ 其余技能只列 `name | 一句话`。388 技能 × 一行 ≈ 12K
- **完整表**：落盘不动（WebUI 技能面板用），模型要细查走 `skill_search`/`skill_list_by_domain`（已有工具）

同时**关掉 hermes 原生索引的重复注入**（P2）：MemOmics 的 AIAgent 由 webui 创建，`build_skills_system_prompt()` 与 SKILLS_INDEX 功能重叠。在 `_create_agent` 处把 hermes 技能索引替换为指向 SKILLS_INDEX 的一行指针（「完整技能目录见下方 SKILLS_INDEX 段」），省 25K 字符。注意先跑通测试再切换（test_skills_registry 钉的是 SKILLS_INDEX，不受影响；hermes 侧测试不动它）。

### 2.5 正确性保障（能不能被正确读取）

1. **钉住截断上限**（P1，立刻可做）：`config.yaml` 加 `context_file_max_chars: 60000`——SOUL 瘦身前保底不截；瘦身后 8K 永远安全。
2. **启动自检**：server 启动时校验 `len(SOUL.md) + len(rules-core) ≤ min(cap, 30K)`，超限 → 控制台 ERROR + WebUI 横幅（复用 `_record_truncation_warning` 的 status 通道，别再只写日志）。
3. **装配快照测试**（新增 `webui/tests/test_guidance_assembly.py`）：给定（意图, 触发词命中, 置顶）→ 断言注入块包含/不包含哪些 guide 文件；钉住「chat 不带 rules-execution」「analysis_exec 必带」这类映射。
4. **引导版本戳**：每轮尾部注入一行 `guide_rev: soul=1a2b3c rules-core=9z8y…`（内容 hash 前 6 位）。排查历史会话时知道模型当时看到的是哪版引导；request_dump 已落盘，天然可对账。
5. **引导完整性进现有门禁**：`scripts/check_skills_gate.py` 加一项——guides/*.md 的 frontmatter `when` 值必须在装配代码的已知意图/关键词集合里（防写了没人读的死引导）。

### 2.6 引导 → 任务反哺闭环（引导如何修改/完善任务）

现有闭环已很强：enforcement 铁轨（rail_review 硬阻断）、辩论裁决→待办、说而不做自检唤醒、虚假完成检测。**缺的是「引导文件 ↔ 铁轨代码」的单向生成关系**（P6）：

1. **铁轨 checklist 从引导生成**：rail_review(pre) 的审查点目前写死在 enforcement.py。改为：命中 guides/rules-execution.md 里带 `☑ gate:` 标记的行自动成为审查点（解析时生成 checklist，SOUL/guides 改一条 → 审查点跟着变，消灭双轨维护）。
2. **引导偏离事后审计推广**：现有 `_pinned_expected`（置顶应加载未加载→回合末告警）推广到 RED 必触发：RED 命中但整轮没 skill_view → 回合末警告事件（现在 RED 命中只发 skill_hit 提示，无未执行追责）。
3. **铁律编号对账测试**：test_task_convention 已钉铁律 32 的标记行格式；扩展为「SOUL/guides 里每条 🔴 铁律要么有对应铁轨代码锚点（注释 `# iron-law N`），要么在豁免清单里」——改铁律不加锚点 = 提交被拦。

### 2.7 实施分期

| 期 | 内容 | 风险 | 验证 |
|---|---|---|---|
| **P0（今天能做）** | ① config.yaml 钉 `context_file_max_chars: 60000`；② 启动自检+前端横幅；③ 引导版本戳尾部注入 | 零行为变化，纯防呆 | 手动切 128K 模型配置验证不再静默截断 |
| **P1** | ① SKILLS_INDEX 双段精简；② SOUL-detail mtime 缓存；③ 装配快照测试；④ RED 未加载回合末追责 | 中（索引格式变化，契约测试要同步） | pytest 全量 + 真实会话观察首轮 token |
| **P2（重构）** | ① SOUL.md 瘦身拆 guides/；② 按意图注入 guides；③ 铁轨 checklist 从引导生成；④ 关 hermes 双轨索引 | 高（动 SOUL = 动身份） | 影子对比：同一批历史用户消息，新旧装配输出 diff 评审后再切 |

**P2 的 SOUL 拆分原则**：不是「删掉」，是「移动 + 留指针」。SOUL.md 每条铁律原位留一行摘要 + `→ guides/rules-execution.md#铁律22`。任何时刻 SOUL.md 单独读也能知道全貌骨架，细节按需取。

---

## 3. 附：两边机制速查对照

| 能力 | DSH | MemOmics 现状 | 本设计 |
|---|---|---|---|
| 身份层 | persona 段（order 0） | SOUL.md 51K（stable） | SOUL.md ≤8K（stable） |
| 项目规则 | AGENTS.md 链（首 step + touch 刷新） | 仓库根 AGENTS.md（启动目录碰巧命中） | 钉 TERMINAL_CWD + 现状 |
| 场景规则 | 无（靠技能） | 全混在 SOUL.md | guides/rules-*.md 按意图尾部注入 |
| 技能目录 | 会话开始摘要目录，失效即换 | 双轨 25K+71.6K 每轮 | 单轨精简 ≤15K 每轮 |
| 技能全文 | skill 工具按需 | skill_view 按需 + RED/置顶/显式预载 | 现状（已是优点） |
| 记忆 | mnemon 每轮快照 | memory digest + L0/L1/L2 每轮尾部 | 现状 |
| 截断保护 | maxBytes 预算，宽文件先丢，可见通知 | 动态 cap，只写日志 | 钉 config + 启动自检 + 前端横幅 |
| 引导→执行 | 系统提示词建议性 | enforcement 铁轨硬阻断（已强于 DSH） | 铁轨 checklist 从引导生成 |
