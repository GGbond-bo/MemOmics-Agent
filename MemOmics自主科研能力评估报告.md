# MemOmics-Agent 自主科研能力评估报告

> **评估对象**：`E:\MemOmics-Agent`
> **评估日期**：2026-08-04
> **评估方式**：源码全量审读（SOUL.md 全文 503 行 + 工具源码 + 3 个只读子代理深度调查 + 实机验证）
> **评估基准**：自主科研闭环 —— AI 拿到数据库 → 主动分析 → 深入调查 → 及时总结储存结论 → 不断深入 → 验证 → 辩论
> **结论速览**：综合得分 **约 44/100** —— 单次分析链路成熟（执行力 90 分），但自主循环缺失（自主性 20 分）

---

## 目录

1. [执行摘要](#一执行摘要)
2. [系统现状架构地图](#二系统现状架构地图)
3. [能力矩阵：对照 6 项目标](#三能力矩阵对照-6-项目标)
4. [六大关键差距深度分析](#四六大关键差距深度分析)
5. [既有风险与质量问题](#五既有风险与质量问题)
6. [分阶段落地路线](#六分阶段落地路线从现状到自主科研产品)
7. [附录](#七附录)

---

## 一、执行摘要

**MemOmics 目前是一个"执行力 90 分、自主性 20 分"的智能分析助手，而不是自主科研 Agent。**

单次分析链路的深度和工程化程度相当高：

- ✅ 多轮 tool loop（单次触发内最多 **300 轮** API 调用自主连续执行）
- ✅ 8 角色辩论（3 pro + 4 con + 1 judge，独立 LLM 串行调用防限流）
- ✅ 规则审查 + git 回滚（rail_review + guardian）
- ✅ 技能自进化（record_run / record_error / query_logs）
- ✅ 长任务后台化（executor + heartbeat + error_scanner 三源交叉验证）

但它是一个**用户消息驱动的执行器**。所有任务由用户消息触发；"新数据到达自动分析""结论产出自动发起下一步""跨会话知识自动冲突检测"这三个自主科研的**命脉机制全部缺失**。

**一句话总结**：你想要的闭环中，**"做"的环节已成熟，"想、追、存、辩、续"五个环节只完成了一半**。好消息是架构底座（Hermes + bio_tools + SOUL 铁律）不用推翻，是增量改造。

---

## 二、系统现状架构地图

```
用户消息（微信 / WebSocket）
   │
   ▼
webui/server.py（342KB 巨型单文件，FastAPI）
   │  _classify_intent 关键词规则分类（chat / research_plan / analysis / ...）
   │  analysis_exec 由 LLM 声明式前导码 🏷INTENT 产生
   ▼
AIAgent(max_iterations=300)  ← hermes-agent 底座
   │  conversation_loop.py:721 多轮 while 循环（单次消息内自主连续执行工具）
   ▼
20 个 bio_tools 工具
   ├─ 分析执行：scan_data / execute_r / execute_python / module_selector / env_check
   ├─ 验证：    rail_review（pre/post 规则审查）/ guardian（3 次失败 git 回滚）
   ├─ 辩论：    debate_analysis（3 pro + 4 con + 1 judge，串行调用）
   ├─ 调查：    literature_search（PubMed / EuropePMC / Semantic Scholar，24h 内存缓存）
   │           query_geo / kegg / stringdb / uniprot / ensembl / ncbi（7 个外部数据库查询）
   ├─ 存储：    memory_bridge（memory_store.db facts 表 + FTS5 + trust_score）
   │           skill_evolution（proven_params / error_log，200 字 result_summary）
   └─ 知识库：  memomics/knowledge_base/（物种/组织/方向/领域分层 YAML，305 个 skill）
```

### 2.1 关键文件清单

| 文件 | 大小 | 作用 |
|---|---|---|
| `webui/server.py` | 342KB | 主服务（FastAPI + WebSocket + 微信入口），实际运行版本（2026-08-04） |
| `memomics/webui/server.py` | 244KB | **旧版 server 副本**（2026-07-18），已无启动入口 |
| `hermes-agent/agent/conversation_loop.py` | — | 多轮 tool-use 循环主体（while + 300 轮上限） |
| `hermes-agent/run_agent.py` | 301KB | AIAgent 类定义 |
| `hermes_home/SOUL.md` | 26KB | 行为规则核心（决策树 + 23 条铁律 + 自进化铁律 + 权限门禁） |
| `hermes_home/SOUL-detail.md` | 17KB | 场景触发表、分析流程细节 |
| `memomics/bio_tools/` | 20 个模块 | 全部 MemOmics 工具 |
| `memomics/knowledge_base/` | YAML 分层 | 物种/组织/方向/领域（01生物学知识/02质控参数/03测序方法） |
| `hermes_home/skills/bioinformatics/` | 305 个技能 | SKILL.md + skill.json + proven scripts |
| `hermes_home/memory_store.db` | 200KB + WAL 4MB | facts 表（56 条）+ FTS5 |
| `hermes_home/state.db` | 118MB + WAL 35MB | Hermes 会话状态库 |

---

## 三、能力矩阵：对照 6 项目标

| 目标环节 | 现状 | 评分 | 关键证据 |
|---|---|---|---|
| **① 拿到数据库 → 主动分析** | ❌ **没有主动**。`scan_data` 只是单次扫描工具（data_scanner.py:85），无 watchdog/目录监听；cron 调度器存在但 **jobs.json 为零配置**，从不触发任何任务 | **15/100** | 全项目无 inotify/watchdog；cron/ticker 仅存活心跳（17 字节时间戳文件） |
| **② 根据分析数据深入调查** | ⚠️ 能力存在但靠 LLM 自觉。`search_papers_by_context` 能按物种/组织/方向构造查询（literature_search.py:286-357）；铁律-5 强制辩论前调 search_papers；但触发完全依赖 LLM 遵守注入协议，**无自动管线** | **55/100** | SOUL.md:366；webui/server.py:5215-5223 |
| **③ 及时总结和储存结论** | ⚠️ 有存储但**无结论实体**。`record_run` 存 200 字符 result_summary（skill_evolution.py:540-552）；KB key_findings.yaml 有 finding/evidence/source/confidence 四字段，但**无 verified 状态、无 dataset_id/session_id 溯源**；facts 表 56 条全是脚本/经验类，零条生物学结论 | **40/100** | memory_store.db 实查：script_score 23 / skill_exp 28 / user_pref 1 / project 1 / general 3 |
| **④ 不断深入** | ❌ 无跨任务延续。**铁律-5（Session 隔离）明确禁止从历史日志自动启动任务**（SOUL.md:314-331）——这是当前与自主科研目标**直接冲突的最高优先级铁律**；待办（todo）只生成不执行，等用户下一条消息 | **10/100** | server.py:4442-4457 待办无执行器 |
| **⑤ 不断验证** | ✅ 单次任务内验证闭环完整：rail_review 规则审查（图片健康度/代码质量/包一致性）→ 失败修复重跑 → guardian 3 次失败自动 git 回滚；三源交叉验证（GPU+磁盘+日志，铁律-2）。**但修复循环无代码强制**，靠 LLM 自律 | **75/100** | rail_review.py:123-266；guardian.py:91-119 |
| **⑥ 辩论** | ✅ 机制最成熟的一环：8 角色独立 LLM 串行调用（防限流，铁律-6）、judge 唯一看到全部论据并输出 verdict/recommended_params（debate_analysis.py:567-714）、72h 缓存复用、失败不归档。**但裁决不回写知识库**，只落 results/log/debate_*.json | **70/100** | debate_analysis.py:551-564 |

**综合得分：约 44/100**

---

## 四、六大关键差距深度分析

### 🔴 差距 1：缺"自主发起"引擎（最致命）

全系统唯一的多轮自主是"单次消息内的 300 轮 tool loop"。跨消息、跨任务、无用户输入的自主动作**不存在**：

- **cron 作业零配置**：`hermes_home/cron/jobs.json` 不存在。cron 调度器（hermes-agent/cron/scheduler.py:3888 tick()）理论上能为到期作业构造完整 agent，但没有任何作业注册。`cron/ticker_heartbeat` 只是 17 字节时间戳，用于检测调度器进程存活（jobs.py:809）。
- **background_review 不发起分析**：只审查记忆/技能（background_review.py:819-821 工具白名单仅 `["skills"]`/`["memory"]`）。
- **铁律-5 制度性禁止**：SOUL.md:314-331 "跨 session 自动执行任务 = 最严重的 bug"——这条铁律是为防止 agent 失控设计的，但它同时封死了自主科研的"主动"。
- **hooks 管线未接入**：hermes_home/hooks/ 为空；memomics 路径（server.py:1307 直接 `from run_agent import AIAgent`）不经过 gateway hooks 管线，gateway 的 `agent:step` 事件对 memomics 无效。

### 🟠 差距 2：无数据目录监控

没有 watchdog / inotify / 定时扫描。新数据库（.h5ad/.rds/.h5）落地后，系统不会感知。这是"拿到数据库 → 主动分析"的**第一公里**。

- `data_scanner.py` 全文 112 行，只做单次文件元数据扫描（h5ad 用 anndata backed 模式读 n_cells/n_genes/obs_columns/物种/注释状态）。
- server.py 全文 grep 无 `watchdog`/`watch`/`inotify`/`cron`/`ticker` 匹配。
- 根目录 `watchdog.bat` 是进程守护（健康检查 127.0.0.1:8899/api/health，server 挂了自动重启），与数据监控无关。
- 唯一的后台轮询 `_weixin_poll_loop()`（server.py:2397）只轮询微信新消息。

### 🟠 差距 3：结论无结构化实体

"结论"目前散落在**三个互不关联**的地方：

| 存储位置 | 内容 | 结构 |
|---|---|---|
| skill_evolution proven_params | 200 字 `result_summary` 自由文本 | 无结构 |
| results/{session}/log/debate_*.json | 辩论裁决 | JSON 但只归档 |
| knowledge_base key_findings.yaml | 文献发现（人工 curation 为主） | finding/evidence/source/confidence |

没有统一的**结论对象**（hypothesis / evidence / verification_status / dataset / timestamp / session / debate_verdict）。后果：

- 无法查询"上次证明了什么"→ 无法支撑"不断深入"
- 无法做跨 session 矛盾检测
- 无法建立数据 ↔ 文献 ↔ 结论的关联图
- facts 表 schema（memory_bridge.py:58-98）：`fact_id, content UNIQUE, category, tags, trust_score, retrieval_count, helpful_count` —— **无 session_id、无数据来源字段**

### 🟠 差距 4：验证循环靠 LLM 自律，无硬约束

- rail_review 是**纯规则静态审查**（非 LLM）：pre 检查 skill 加载+依赖包；post 检查图片健康度（<5KB/全单色/NA>10%）、代码质量（行数<10、&& 多步）、包注册一致性（rail_review.py:123-266）。
- 但"失败 → 修复 → 重跑 → 再验证"**没有 while 循环 / 重试上限**，完全依赖 LLM 按注入指令执行（rail_review.py:244-251 是提示语不是代码）。
- 唯一代码强制的是 guardian 的 3 次失败自动 `git reset --hard` 回滚（guardian.py:91-119）。
- 自主科研要求**可证明的收敛**（直到 rail_review 通过才放行下一步），现在做不到。

### 🟡 差距 5：辩论与知识库断裂

- 辩论产出（verdict / recommended_params / 被反驳的假设）是科研闭环里最有价值的信息。
- 现状：只归档到 `results/<session>/log/debate_*.json`（debate_analysis.py:551-564）+ 全局缓存 `hermes_home/skills/bioinformatics/_debates/<md5>.json`（72h 复用）。
- **不回写知识库**。没有"结论 → 辩论 → 裁决 → 回写 KB（含 verdict 和 confidence）"的链路。
- 裁决对分析的影响靠 LLM 协议执行（如 cellbender skill 的"confidence=low → 改参数重跑"规则），无代码自动回写。

### 🟡 差距 6：文献调查结果不落库

- `search_papers`（literature_search.py:233-283）：PubMed（NCBI E-utilities）+ EuropePMC + Semantic Scholar 三源合并去重。
- 结果**只做 24h 内存缓存**（webui/server.py:5522-5530 `_lit_cache`），**不落库**。
- "分析结果 → 查文献 → 解释机制"依赖 LLM 按规则触发（铁律-5 辩论前强制），无自动管线。
- 文献与结论的关联无法跨会话复用。

---

## 五、既有风险与质量问题

| # | 严重度 | 问题 | 详情 |
|---|---|---|---|
| 1 | 🔴 | **巨型单文件** | webui/server.py 342KB、run_agent.py 301KB、cli.py 744KB、hermes_state.py 345KB —— 改造自主引擎时是最大维护阻力 |
| 2 | 🔴 | **双 server 并存** | `webui/server.py`（新版 8/4）与 `memomics/webui/server.py`（旧版 244KB 7/18）—— 旧版无入口但保留；`memomics/memomics/` 还有嵌套副本（仅 __init__/bio_tools/knowledge_base），极易改错文件 |
| 3 | 🟠 | **state.db WAL 膨胀** | state.db 118MB + WAL 35MB（记忆中的 WAL 膨胀问题仍存在） |
| 4 | 🟠 | **意图分类纯关键词规则** | `_classify_intent`（server.py:556-744）无 LLM 兜底、无评测集；analysis_exec 靠 LLM 自声明前导码。自主模式下误分类风险被放大（无人盯着纠正） |
| 5 | 🟡 | **临时脚本散落** | 根目录 10+ 个 fix_weixin_v*.py；ckpt.tar.gz 1.4GB、hdwgcn_release.tar.gz 204MB 常驻仓库 |
| 6 | 🟡 | **generate_report 行为矛盾** | 默认输出到桌面（generate_report.py:83-92），与 SOUL.md 目录策略（results/{session_dir}/，SOUL.md:144,171-181）冲突；实际靠 html-report skill 的 ReportBuilder 解决 |
| 7 | 🟡 | **save_conclusions 未注册为工具** | 铁律 26/SOUL-detail 要求"分析完成 save_conclusions 写 conclusions.md/json"，但全项目 grep 无该工具实现，由 LLM 裸落盘 |

---

## 六、分阶段落地路线（从现状到自主科研产品）

**前提**：架构底座（Hermes + bio_tools + SOUL 铁律）不用推翻，是增量改造。

### P0 — 止血（1-2 天）
- [ ] 删除旧副本：`memomics/webui/server.py`、`memomics/memomics/` 嵌套目录
- [ ] state.db WAL checkpoint 清理 + 定时任务
- [ ] server.py 拆模块（意图分类 / 路由 / 工具 / 会话管理）—— 为后续改造打地基
- [ ] 清理根目录临时脚本与大文件

### P1 — 数据感知（2-3 天）
- [ ] 数据目录 watchdog：新文件（h5ad/rds/h5/10x 目录）→ 自动 scan_data → 生成"数据档案"（格式/细胞数/物种/注释状态/分组列）
- [ ] 数据档案入内存队列 + 前端提示"发现新数据，是否开始分析？"（半自主）
- **这是"拿到数据库"的物理前提**

### P2 — 结论实体 + 结论库（3-5 天）
- [ ] 新建 `conclusions` 存储（SQLite 表或 YAML）：`{id, hypothesis, evidence[], refs[], verified, confidence, dataset_id, session_id, debate_verdict, timestamp}`
- [ ] record_run 升级为写结论实体（result_summary → 结构化）
- [ ] 废除铁律-5 对"结论驱动"的禁止，改为**"数据 + 结论驱动，用户可一键关闭"**
- [ ] 结论库可查询（search_conclusions 工具）+ 前端展示
- **这是整个自主闭环的数据基石**

### P3 — 自主循环引擎（5-7 天）
- [ ] **两级引擎**：
  - ① cron 作业化：jobs.json 配置「数据到达 → 分析 → 总结 → 入库 → 触发下一步」的作业链（Hermes cron 已支持 wake-gate 链，scheduler.py:2312-2335）
  - ② agent 内"研究议程"（research agenda）：pending hypotheses 队列，自动排队下一步分析
- [ ] 每个自主步骤带门禁：rail_review 通过才放行 + 预算上限（max_iterations/费用）+ 心跳汇报 + **用户随时接管**
- [ ] 自主模式默认**半自主**（每一步需用户确认或可跳过），逐步演进到全自主
- **"不断深入"闭环成型**

### P4 — 辩论回写 + 冲突检测（2-3 天）
- [ ] debate verdict 自动写结论实体（verdict/confidence/recommended_params）
- [ ] 结论入库时与历史结论做矛盾检测（同 dataset/方向 + 相反 finding）→ 矛盾自动排一场 mini-debate
- **"不断验证、辩论"闭环成型**

### P5 — 文献-结论关联（2 天）
- [ ] search_papers 结果自动落库（paper 表：PMID/DOI/title/findings/date）
- [ ] 分析结论自动挂接引用（结论 ↔ 文献 ↔ 数据关联图）
- [ ] 文献-结论关联可跨会话检索复用
- **"深入调查"可复用**

> **里程碑**：P1-P3 完成后，产品目标即成型 —— 数据落盘 → 系统感知 → 分析 → 文献调查 → 辩论 → 结论入库 → 议程推进下一步。P4/P5 是"科研质量"的放大器。

---

## 七、附录

### 附录 A：证据索引（文件:行号）

| 证据 | 位置 |
|---|---|
| 多轮循环主体（300 轮上限） | hermes-agent/agent/conversation_loop.py:721-746 |
| max_iterations=300 显式设置 | webui/server.py:1311-1316 |
| 待办无执行器（只生成不执行） | webui/server.py:4442-4457 |
| cron 调度器可为到期作业构造 agent | hermes-agent/cron/scheduler.py:3888；jobs.py:71 |
| cron 零作业（无 jobs.json） | hermes_home/cron/（实测目录） |
| background_review 仅审记忆/技能 | hermes-agent/agent/background_review.py:819-821 |
| 铁律-5 禁止跨 session 自动执行 | SOUL.md:314-331 |
| 铁律-6 辩论必须串行（防限流） | SOUL.md:288-310 |
| 铁律-3 强制结构化前导码 | SOUL.md:236-263 |
| 铁律-22 工具权限门禁矩阵 | SOUL.md:388-410 |
| 铁律-24 自动沉淀门禁 | SOUL.md:426-433 |
| 辩论 8 角色 + 裁决 | debate_analysis.py:567-714 |
| 辩论结果只归档不进 KB | debate_analysis.py:551-564 |
| rail_review post 规则检查 | rail_review.py:123-266 |
| guardian 3 次失败 git 回滚 | guardian.py:91-119 |
| record_run 200 字 result_summary | skill_evolution.py:540-552 |
| facts 表 schema（无 session 溯源） | memory_bridge.py:58-98 |
| kb_search 纯只读 | kb_search.py:558-569 |
| search_papers 三源 | literature_search.py:2-13,233-283 |
| 文献 24h 内存缓存不落库 | webui/server.py:5522-5530 |
| KB 写入（参数级，confidence 高者覆盖） | write_to_kb.py:84-149 |
| key_findings.yaml 四字段结构 | memomics/knowledge_base/Homo_sapiens/liver/aging/01_生物学知识/key_findings.yaml |
| 实际运行 server | start.bat:97 `"%PYTHON%" webui\server.py` |

### 附录 B：memory_store.db 实况（2026-08-04 实测）

```
facts 总数: 56
categories: script_score 23 / skill_exp 28 / user_pref 1 / project 1 / general 3
```

**解读**：记忆库 100% 是"脚本经验 + 用户偏好"类，**0 条生物学结论**。这印证了差距 3——系统擅长记住"怎么跑"，不擅长记住"发现了什么"。

### 附录 C：知识库现状

- 结构：`knowledge_base/{物种}/{组织}/{方向}/{01_生物学知识|02_质控参数|03_测序方法}/{RNA|ATAC|spatial|...}/{文件}.yaml`
- 已有物种：Homo_sapiens、Mus_musculus、Macaca_mulatta、zebrafish、monkey、common、error_memory
- 已有方向：aging、AD、development、cardiomyopathy、diabetes 等
- 结论格式样例（key_findings.yaml）：
  ```yaml
  findings:
    - finding: 衰老破坏肝细胞区域化(zonation)稳态
      evidence: |
        - snRNA-seq显示衰老肝脏中Zone 1和Zone 3基因表达边界模糊
      source: |
        - "Nikopoulou et al. 2023, Nature Aging (PMID: 37946043)"
      confidence: high
  ```
- **缺口**：无 `verified` 状态字段、无 `dataset_id/session_id`、无辩论裁决回写、无跨 session 冲突检测

### 附录 D：评估方法

1. **源码审读**：SOUL.md 全文（503 行行为规则）、data_scanner.py、memory_bridge.py、bio_tools/__init__.py
2. **子代理深度调查 ×3**：
   - 自主任务发起与 cron/心跳机制
   - 结论存储与总结机制（KB/memory/skill_evolution）
   - 意图分类、验证、辩论机制
3. **实机验证**：start.bat 启动路径、双 server 版本对比、memory_store.db 表内容、knowledge_base YAML 结构、cron 目录内容

---

*报告生成：Reasonix · 2026-08-04 · 只读评估，未修改任何项目文件*
