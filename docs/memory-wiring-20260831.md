# 记忆/上下文接线落地记录（2026-08-31）

> 依据 2026-08-31 评审（四断链：资产确认链死线 / 中文 facts 检索 FTS 恒空 /
> 意图未接入检索 / 折叠双实现摘要套摘要 + 压缩辅助模型 404）的一次性接线落地。
> 每个断链 → 改动 → 测试 → 生产实证。
## 1. 资产确认链（P0-1）

- `webui/session_state.py::extract_assets`：默认 `auto_confirm=True` →
  `status="confirmed"`（用户消息显式给出路径 + `os.path.isfile` 双保险，
  视为确认信号；`auto_confirm=False` 保留旧 pending 语义供测试/人工场景）。
  - purpose 用同消息内容实体回填（"继续跑热图"→ purpose=热图，FTS 可命中）
  - 已存在资产若为旧 pending → 顺带升级 + `mark_asset_used`
  - 修复缺陷：原 `raw.lower()` 把资产名/路径小写化（Linux 下 isfile 会失败），
    改为保留原始大小写、去重/比对用 lower 版本
- `hermes-agent/plugins/memory/holographic/store.py`：新增
  `get_asset_id(name, path, session_id)` / `get_asset_status(asset_id)`；
  `search_assets` 的 LIKE 兜底改为**多 token OR**（增强 query "热图 继续跑"
  必须命中 purpose='热图'；此前整串 LIKE 恒空）
- 生产迁移：`scripts/confirm_pending_assets.py`（幂等；先备份再更新）
  - 2026-08-31 实测：25 条 pending → **23 confirmed**（文件真实存在），
    2 条缺失文件保持 pending；备份 `memory_store.db.bak_prewire_20260831-013703`
- 效果：holographic `system_prompt_block` 的"📌 会话资产清单"与 `search_assets`
  （默认 confirmed）从"生产永远为空"变为真实工作。

## 2. 中文 facts 检索（P0-2）

- `hermes-agent/plugins/memory/holographic/retrieval.py`：
  - `FactRetriever.search` 增加 **Stage 1b 词级候选通道** `_cjk_candidates`
    （jieba 分词 → `content LIKE %token%` OR 粗筛 → 与原 Stage 2
    Jaccard×trust×HRR 打分合并）
  - 统一分词器 `_text_tokens`：含 CJK 用 jieba/2-gram，纯 ASCII 回退原
    空白切分（英文行为逐字节不变）
- 实证（生产库干跑）：「继续跑/peak」query 命中
  `[archr-atac-analysis] script 'peak_calling_defaults_check.R' ... addGroupCoverages
  minCells=40/maxCells=500/... [0.8]` —— 即"这个问题的标准答案"从 FTS 恒空
  变为真实召回，且 trust 加权正确置顶。

## 3. 意图/实体增强 prefetch（P0-6）

- `holographic/__init__.py`：新增 `_enhance_query(query, sid, store)` ——
  把 session_state.task_json.entity（P1-4 话题切换旁路写入）并入检索 query
  （"继续跑" → "热图 继续跑"）；`prefetch()` 四源（facts/assets/history）统一
  使用增强后 query
- `webui/server.py::_build_memory_digest`：`fts_recall` 的 query 改为
  `extract_entity(user_text) or user_text`（server 侧同一接线的另一半）
- 注意：Hermes 底座 `turn_context.py` 传给 provider 的是原始用户消息
  （意图值拿不到），因此 entity 从会话状态块取——该块由 server 的
  意图分类+P1-4 旁路共同维护，等价于意图驱动，且不违反"不动底座"约束。

## 4. 折叠统一（P1：防摘要套摘要）

- `webui/context_arch.py::memomics_replay`：新增 `skip_rebuild=False` 参数；
  True 时原样返回 history（不做 new_span/rebuild/writer）
- `webui/server.py`（c0/c 调用序列）：`_maybe_rollup_history` 折叠发生时
  （`is not` 同对象判别）→ `memomics_replay(..., skip_rebuild=True)`。
  分工：>60K 由 c0 确定性折叠接管；30K-60K + 自检触发的长会话才走 P1-P5
  LLM 增量 checkpoint。此前 c 会把 c0 摘要当 span 再压缩一遍（双份摘要）。

## 5. 压缩辅助模型 404（P1）

- 根因：`auxiliary.compression` 未配置 → auto 解析到 `mimo-v2.5`
  （opencode.ai 网关），8-29 实测 404 "The model does not exist or is not
  deployed"，compression_fallback_streak=2（errors.log 两处 WARNING）
- `hermes_home/config.yaml`：显式
  `auxiliary.compression: {provider: openai, model: deepseek-v4-flash}`
  （DCS 同主模型 provider，1M 窗口 ≥ 主模型压缩阈值，可行性检查可过）
- config.yaml 被 gitignore（含 API key），不受 git 状态影响。

## 6. 测试

- 新增 `webui/tests/test_memory_wiring.py`（17 用例，全绿）：
  - TestAssetAutoConfirm（默认确认/pending 可选/存量升级/注入层可见）
  - TestCjkFactRetrieval（中文命中/短词/英文不变/无关不误报）
  - TestIntentEnhancedPrefetch（entity 并入/无 entity 不变/裸"继续跑"召回热图资产）
  - TestFoldCoordination（skip_rebuild 恒等/短历史不动/折叠换列表）
  - TestConclusionWiring（append 落盘/注入/去重/L3 归档索引）
- 回归：webui/tests 全量 exit 0（exclude e2e_skill_trigger.py 与
  test_frontend_ux.py::TestScriptIntegrity 两用例——后者为既有失败
  （index.html 脚本块 i18n，HEAD 提交遗留，与本轮改动无关：`git diff
  HEAD -- webui/index.html` 为空））
- 生产干跑（scripts → 真实库）：资产状态 confirmed 23/pending 2；
  prefetch 四源输出含中文 facts/资产/历史；entity=peak 增强有效。

## 7. 遗留（不在本轮范围）

- L0/L1 结论注册表：接线已存在（server.py:12862），生产 conclusions.md 尚无
  数据（8-31 上线后未跑过新会话）——下一轮业务会话自动落盘；本轮以
  TestConclusionWiring 验证逻辑正确。
- user_request facts 噪音（整句代码被当诉求升级到 facts）→ 升级规则加
  "句子含代码/过长截断"过滤，建议作为后续 P2。
- 注入带收敛（12-15 个 system 块统一预算托管）→ 风险高收益中，作为后续 P2。

## 8. 第二轮极端评测（2026-08-31，真实生产数据 + 离线基准）

评测方法：从 memomics-cd677556（1422 条 user 消息）导出干净样本，
人工标注 40 条意图 + 12 个检索 query，跑真实链路；合成 100 轮会话测
压缩免疫；484 条真实消息跑 auto_extract/REQUIREMENTS 提取质量。

### 数据面发现（修复前）

1. **脚手架污染 65%**：1422 条 user 消息中 938 条是注入脚手架
   （145 种唯一文本重复注入），仅 484 条干净用户输入——digest 注入被
   持久化进 state.db 且不断增殖。
2. **facts 元数据占 58%**：630 条 facts 中 skill_exp 192 + script_score 174
   是机器记账；user_request 134 条中 14% 是 R 代码原文（诉求升级规则误捕获）。
3. REQUIREMENTS 元循环：注入脚手架文本被 `_extract_and_store_requirements`
   再次提取入库（"一定要有依据"重复 4 行、脚手架行重复 8 行）。

### 能力测量（修复前后）

| 维度 | 修复前 | 修复后 | 方法 |
|---|---|---|---|
| 意图识别（可接受率） | 85% | **98%** | 40 条真实消息标注 |
| 意图识别（精确率） | 18% | **40%** | 同上 |
| 检索：facts 源 Top-1 命中 | 4/12 | **10/12** | 12 query 人工评分 |
| 检索：实体污染（旧实体挤掉新话题） | 5/12 query | **0/12** | q1/q3/q5/q9 复测 |
| REQUIREMENTS 误报行数 | 19 行（~50% 误报） | **6 行（2 残留）** | 484 条真实消息 |
| auto_extract 精度 | 3 条全对（0 噪音） | 不变（保守策略正确） | 484 条真实消息 |
| 压缩免疫（关键事实保留率） | — | **10/10**（36K→2K token，5%） | 合成 100 轮折叠 |
| 英文 BM25 检索 | 满分 | 满分 | q11 |

### 本轮修复

- `_enhance_query`：有内容词时不拼旧任务实体（"继续跑"才兜底）——
  修复"peak 实体把专利结论表挤出 Top5"的排序污染（bench q3/q9 复测通过）
- `_extract_and_store_requirements`：①注入脚手架剥壳（防元循环）
  ②去重键规范化（忽略 (已确认)/(特别指定) 标记）③征询句/命令回显/
  截断映射过滤——误报 19→6 行
- `_classify_intent`：①进度口语词（"等了两天了还在跑"）②交付类执行短句
  （"把8大类的基因都给我"→direct_exec）③cancel 就近组合规则（长引用
  "不要用这组基因"不再误杀任务）④裸词"状态"收紧为短语
- 测试：`test_memory_wiring.py` 增补 18 用例（含防污染回归）；
  webui/tests 全量 EXIT 0

### 评测脚本（可复跑）

`scripts/bench_audit.py`（污染/审计）、`bench_intent2.py`（意图基准）、
`bench_retrieval.py`（检索基准）、`bench_extract.py`（提取质量）、
`bench_compress.py`（压缩免疫）。

### 与设计文档的剩余差距（第 9 章待办）

1. **检索是"原文召回"不是"知识召回"**：中文 facts 命中多为 [用户诉求]
   整句原文；蒸馏式知识只存在于 MEMORY.md 全量注入（占位 ~30K 字符/轮）。
   设计文档 §7.2"诉求升级 facts"已实现但内容未结构化（无 key-value）。
2. **意图→检索的"意图"仍是弱代理**：entity 兜底有效，但 `_classify_intent`
   的细粒度 intent（research_plan/direct_exec）仍不进检索参数。
3. **常驻注入规模**：SOUL 71KB + skills 索引 65KB + MEMORY/USER ~58KB +
   注入带 ~8KB ≈ 200K 字符/轮（~10 万 token，占 1M 窗口 ~10%），
   尚无统一预算托管。
4. **capture 升级规则**仍会把含关键词的代码行/长句升级为 user_request
   facts（134 条中 14% 代码）。
5. 折叠后细节召回依赖 session_search 工具（elision marker 已在
   `_build_rollup_checkpoint` 中，但 marker 需要 state.db 有记录才生成——
   合成环境无 DB 时为空，线上正常）。

## 9. 第三轮完善（2026-08-31：把第 8 章剩余问题逐项落地）

| # | 问题 | 修复 | 验证 |
|---|---|---|---|
| 1 | intent 值未进检索 | server 每轮 `update_task_state(intent=…)`；prefetch 读 intent 分流（knowledge_ask→facts×6；analysis/direct_exec→assets×5） | test_memory_wiring 23 用例绿 |
| 2 | 项目隔离 project 未传 | `extract_assets(project=results_dir basename)` | 同上 |
| 3 | 资产失效检测未实现（§2.1⑥） | `store.reconcile_assets`（confirmed 且 isfile=False→missing）；extract_assets 每轮对本会话 reconcile；system_prompt_block 渲染"⚠️ 资产失效提示" | test_asset_missing_reconcile |
| 4 | capture 升级误捕代码（14% 污染） | `_code_like` 检测（`<-`/library(/readRDS/≥3 行）→ 不升级 facts（仍记 requests_json） | test_code_paste_not_escalated |
| 5 | 中文排序无区分度 | ①HRR 对 CJK 查询强制中性（随机噪声实锤反超 user_pref）②类别权重作用于相关性（引文 0.8×，短引文 jaccard 偏置被压住）③recency 0.92-1.0 ④短语连续 +0.08 | test_ranking_boost + bench q2/q3/q6 复测 |
| 6 | REQUIREMENTS 句子级脚手架残留 | 分句循环加注入前缀跳过 | bench_extract 复测 19→6 行 |
| 7 | 历史 938 条脚手架持久化污染 | 新消息端 8-21 已修（_run_text 干净）；`scripts/migrate_strip_scaffold.py` 一次性剥离 193 条带原文消息（1898 条纯注入保留，(b) 模型侧过滤） | 已执行，备份 state.db.bak_strip_* |

本轮改动文件：`webui/server.py`、`webui/session_state.py`、
`hermes-agent/plugins/memory/holographic/{__init__,retrieval,store}.py`、
`webui/tests/test_memory_wiring.py`（23 用例）、
`scripts/migrate_strip_scaffold.py`（新增）。
验证：py_compile OK；webui/tests 全量 EXIT 0；bench 检索复测 q2 gold 置顶
保持、q3 专利双 gold 占 TOP2、q6 直接答案 TOP2。

