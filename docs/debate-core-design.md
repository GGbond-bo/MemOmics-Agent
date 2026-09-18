# MemOmics 辩论核心化 + 架构消融实验设计文档

> 版本：v1.0 ｜ 日期：2026-08-08 ｜ 状态：待审阅 ｜ 作者：Reasonix（基于用户 2026-08-08 需求）
> 目标读者：MemOmics 维护者（用户）

---

## 0. 摘要

两个目标，一个工程：

1. **核心化**：把"写在技能描述里几句话"的辩证机制，升级为 MemOmics 的一级核心子系统（可配置辩论引擎 + 独立 `debate-core` skill + 代码级触发钩子 + 裁决回流）。
2. **科学验证**：回答"一个模型扮演 7 角色 vs 双模型对抗+第三模型裁决 vs 多模型轮换，哪种更好"，产出可发表期刊的消融实验。

核心思路：**引擎参数化是两者的共同地基**——`debate_mode` 开关让 MemOmics 日常真实任务自动积累实验数据，论文数据不另外造。

---

## 1. 现状盘点（2026-08-08 实测）

| 组件 | 位置 | 现状 |
|---|---|---|
| 辩论引擎 | `memomics/bio_tools/debate_analysis.py`（998 行） | v3 多角色：正方 3 编辑（生物/统计/生信）+ 反方 4 编辑（+历史经验）+ 裁判。**全部角色读同一组环境变量 `DEEPSEEK_API_KEY/BASE_URL/MODEL` → 单模型同构** |
| 知识库分科 | 同上 | `biology_kb/statistics_kb/bioinfo_kb` 参数，空则回退通用；`_auto_load_kb()` 按物种/组织/方向自动加载 |
| 缓存去重 | `_save_debate/_load_debate` | md5(topic+context) → `hermes_home/skills/bioinformatics/_debates/`，72h TTL；失败结果不缓存（P0-1 已修） |
| 归档 | `_archive_debate_to_results` | `results/<sid>/log/debate_{ts}_{hash}.json` |
| 强制触发 | `webui/enforcement.py` | 仅 1 处钩子：`rail_review(post)` 通过且 `analysis_level == "analysis"` 且 `debate_done == False` → 弹窗强制 `debate_analysis`（L302-305） |
| 铁律 | `hermes_home/SOUL.md` | 铁律 -6：禁止多角色 LLM 并发（已改串行）；分析级 9 步含 debate；统计级 7 步跳过；轻量级 5 步跳过 |
| 运行手册 | `hermes_home/skills/bioinformatics/multi-role-debate/SKILL.md`（109 行） | 偏排障（8/8 失败排查），**文档与代码脱节**：仍写 `_call_role_parallel` 用 ThreadPoolExecutor 8 路并发（代码已改串行） |
| Key 注入 | `webui/server.py::_sync_debate_env()`（L1645） | 优先 `_current_model` → deepseek 官方 → dcs 匹配；dcs-cloud key 已失效(401) |
| 模型池 | `config.yaml::custom_providers` + `server.py::_CHINA_PROVIDERS` | dcs-cloud / opencode-go / deepseek 三 provider；DeepSeek V4、GLM-5.x、Kimi K2.6-K3、Qwen3.7/3.8、MiniMax-M3、MiMo 等 10+ 模型；**opencode-go 聚合平台 key 有效 → 异构多模型在基础设施上零成本可行** |
| 历史存档 | `_debates/`（17 份，7/8~8/1） | 含成功案例（如 2026-07-14 DEG 辩论）与失败残留（8/1 hdWGCNA 8/8 失败） |

**关键结论**：机制已经产品化了一半（引擎+强制+归档齐全），缺的是**可配置性（多模型/多模式/多轮次）**、**代码级触发钩子**、**独立核心 skill**、**结果回流闭环**。

---

## 2. 市面调研结论（2026-08-08，证据见附录 A）

1. **三架构头对头比较 = 研究空白**。MAD 领域 141 篇论文的系统综述（arXiv:2607.26212，审稿 ACM Computing Surveys）明确指出：领域收敛于"同模型多角色+全连接+投票"是**约定俗成而非系统比较**。现有实现（架构 A）与用户设想（架构 B/C）无任何一篇论文做过对比。
2. 关键证据：Du 2023（同构，3 agents 最优、5 饱和）；Khan 2024（**异构强辩手+弱裁判：准确率 48%→76%**）；Liang 2023（异构时 judge 公平性存疑）；JudgeLM（judge 越大越强，33B 与 GPT-4 一致性>90%）；MoA（便宜异构协作超单一昂贵模型）；Agent Forest（纯采样投票随 agent 数单调扩展，与辩论正交）。
3. 生信场景研究原型存在（MARBLE 2026 辩论驱动空间转录组、SOAP 临床多代理辩论），但**"辩论作为产品核心强制环节+裁决回流经验"无成熟先例**——MemOmics 模式独特。

---

## 3. 核心化设计（4 层）

### L1 — 辩论引擎参数化（地基，改 `debate_analysis.py`）

#### 3.1.1 配置源：`hermes_home/config.yaml` 新增 `debate:` 段

```yaml
debate:
  mode: adversarial          # homogeneous | adversarial | multi_model | temperature
  rounds: 2                  # 辩论轮次（1-3；文献拐点在 2-3）
  agents_per_side: 3         # 每方编辑数（文献拐点 3）
  judge:
    model: glm-5.2           # 裁判模型（可独立于辩手）
    provider: opencode-go
  pro:
    model: deepseek-v4-pro
    provider: deepseek
  con:
    model: kimi-k3
    provider: opencode-go
  role_model_map: {}         # 细粒度覆盖：{"pro_biology": {"model": "...", "provider": "..."}, ...}
  auto_trigger:
    script_design: analysis  # off | analysis | statistical —— 代码生成后辩论
    result: analysis         # off | analysis | statistical —— 代码执行后辩论
    conclusion: analysis     # 现状：仅 rail_review(post) 后（analysis 级）
  cache_ttl_hours: 72
  budget:
    max_debates_per_session: 8   # 单会话辩论次数上限（成本护栏）
    warn_tokens: 200000
```

#### 3.1.2 `mode` 语义（= 实验因子 F1）

| mode | 语义 | 对应架构 | 预期成本 |
|---|---|---|---|
| `homogeneous` | 全部角色用同一模型（现状行为） | A | 1× |
| `adversarial` | pro 全用模型 A、con 全用模型 B、judge 用模型 C（默认 C 为最强可用） | B | 1× |
| `multi_model` | 每个角色从模型池轮换/随机抽不同模型（全异构） | C | 1× |
| `temperature` | 同模型多温度采样（隔离"多样性必须来自异构"这一假设的对照组） | A' | 1× |

#### 3.1.3 代码变更点（最小集）

1. `_call_llm_sync(prompt, label, api_key, base_url, model)` → 增加 per-role 模型解析：`role_model_map` 或 `mode` 决定每个 label 用哪个 (provider, model)。**用 `(provider, model)` 取代裸 `(base_url, model)` 作为调用标识**——异构后 base_url 不再唯一。
2. `debate_analysis()` 签名保持向后兼容（topic/context/kb 参数不变），新增可选参数 `mode/rounds/agents_per_side/role_model_map`，缺省从 config 读。
3. **缓存 key 必须含模式指纹**：`_topic_hash` 改为 `md5(topic + "||" + context + "||" + mode + "||" + rounds + "||" + role_model_fingerprint)`——否则不同架构的结果会互相污染缓存（这是本次设计最容易踩的坑，P0 级）。
4. **多轮次**：rounds>1 时，第 2 轮起把上一轮 judge 裁决 + 双方论点摘要作为"新证据"注入各角色 prompt（注意：注入会破坏完全隔离——文档要写明"轮次>1 时隔离降级为轮间隔离"，这也是论文的实验变量）。
5. `_sync_debate_env()` 演进为 `_resolve_role_llm(label) -> (api_key, base_url, model)`：按 role_model_map → mode → 全局 `_current_model` 顺序解析；provider 切换时从 `_provider_keys` 取 key，取不到该 role 记 `error` 并计入失败检测（沿用 P0-1 不缓存规则）。

#### 3.1.4 兼容性

- 未配置 `debate:` 段时，行为 = 现状（homogeneous + 环境变量注入），**零迁移风险**。
- `debate_figure_conclusions`（🖼️ 工具）自动继承新引擎，无需改。

### L2 — 独立 `debate-core` skill（核心机制运行手册）

位置：`hermes_home/skills/bioinformatics/debate-core/SKILL.md`（新目录；`multi-role-debate` 退役或降级为排障附录并入）。

内容大纲：
1. **机制说明**：角色模型、隔离模型、mode 选择指南（附成本矩阵）
2. **运行流程**：何时触发（3 个钩子）、如何组装 topic/context、KB 分科注入
3. **裁决解读**：`verdict=modify` 是产出不是失败；`recommended_params` 必须落为下一步 action；confidence 低 → 建议补数据/补文献
4. **失败恢复**：8/8 失败排查顺序（保留现有内容，修正并发描述），串行脚本回退
5. **引用纪律**：SOUL.md 铁律 5——辩论引用只能来自 `search_papers()` 的真实文献（PMID/DOI），KB 仅作背景
6. **沉淀**：裁决 → `skill_evolution(record_run)` → 知识库验证铁轨

同时修正 `multi-role-debate/SKILL.md` 的过时并发描述（L60-63），避免误导。

### L3 — 触发面扩展（改 `webui/enforcement.py`，不改 Hermes 底座）

`tool_start_cb` / `tool_complete_cb` 已是工具生命周期钩子，直接扩展：

| 钩子 | 触发点 | 辩论对象 | 分级 |
|---|---|---|---|
| ① 脚本设计辩论（新增） | `tool_start_cb` 拦截 `execute_r/execute_python/terminal`，且该步无既有已通过辩论的等价 topic | 代码方案（方法选择、参数、统计模型） | 按 `auto_trigger.script_design` |
| ② 结果辩论（新增） | `tool_complete_cb` 拦截执行完成，`rail_review(post)` 通过后 | 输出解读（DEG 结论、聚类注释、富集解读），带真实输出摘要进 context | 按 `auto_trigger.result` |
| ③ 结论辩论（现状） | rail_review(post) 后 + analysis 级 + 未辩论过 | 最终结论 | analysis 级（现状不变） |

关键实现细节：
- **去重防轰炸**：三个钩子共享 `es.debated_topics`（topic hash 集合，会话级），同一 topic 只辩一次；钩子②自动沿用钩子①的辩论结论（同一 topic 时跳过，附注"已辩"）。
- **成本护栏**：`budget.max_debates_per_session` 触顶后，后续辩论降级为"轻量 pro/con 单轮"或仅提示人工裁决。
- **异步化**：辩论是 8 次 LLM 调用（约 1-3 分钟），建议钩子②③保留现状（agent 工具链内同步执行，保证铁律语义"必须完成才能继续"）；钩子①（脚本设计辩论）可做成 agent 决策（提示"建议先 debate 再执行"，agent 自行调用），避免每次执行前强制等待。

### L4 — 裁决回流闭环

```
debate verdict + confidence + recommended_params
  → skill_evolution(record_run, params_used=recommended_params, score=confidence映射)
  → KnowledgeBaseBuilder._verify_rail() 带 evidence 写入（辩论结论作为 evidence 源）
  → 下次同场景 debate 自动注入历史裁决（KB 分科注入时附带）
```

要点：裁决写入 KB 必须满足知识库验证铁轨（有 evidence 才写）；`verdict=modify` 时写入的是"修正后的参数 + 辩论依据"，不是原参数。

---

## 4. 实验设计（期刊论文）

### 4.1 研究问题与假设

- **RQ1**：架构（同构/异构对抗/全异构/温度采样）对辩论裁决质量的影响？
- **RQ2**：角色数量与轮次的最优配置（验证/挑战 Du 2023 的"3 agents/3 轮"拐点）？
- **RQ3**：judge 相对辩手的能力梯度如何决定"异构是否优于同构"？（调和 Khan vs Liang 的表面矛盾）

假设：
- **H1**：同构多角色存在回声室效应（论证多样性低，裁决偏向模型先验），异构对抗论证多样性显著更高。
- **H2**：judge 强于辩手时异构最优；judge 弱于辩手时异构反而更差（被强辩手说服错误观点）——**judge 选择比角色数量更关键**。
- **H3**：角色数 3 是性价比拐点，7 角色边际收益 < 成本（在生信决策场景验证）。
- **H4**：多轮次（rounds=2）提升裁决稳定性（置信度校准），但轮间注入破坏隔离会引入趋同，收益在 2 轮饱和。

### 4.2 因子设计

| 因子 | 水平 |
|---|---|
| F1 mode | homogeneous / adversarial / multi_model / temperature |
| F2 agents_per_side | 3 / 7 |
| F3 rounds | 1 / 2 / 3 |

主实验：4×2×3 = 24 配置 × 每配置 N 题。judge 能力梯度作为**独立子实验**（judge ∈ {弱于辩手, 等于辩手, 强于辩手} 三档，在 adversarial mode 下做 3×2 小矩阵）。

### 4.3 数据集

**轨 1 — 通用推理基准**（证明通用性）：GPQA-Main 子集（~80 题，多选，有 ground truth）、MMLU 科学子集（~100 题）。

**轨 2 — 自建"生信分析决策基准 BioDebateBench"**（论文主要贡献）：
- 来源：`_debates/` 17 份真实辩论 + `results/<sid>/log/debate_*.json` 历史归档 + 未来真实任务
- 题型（对应 MemOmics 真实决策点）：
  - T1 参数选择（如"clustering resolution 0.8 vs 1.0"）——ground truth = 专家标注的最终采用参数 + 理由
  - T2 细胞注释（"cluster 3 = T cells?"）——ground truth = 专家注释
  - T3 结论可信度（"red 模块是运动逆转衰老的分子靶点？"）——ground truth = 专家评级（支持/需修改/证据不足）
- 标注流程：专家（用户）标注 50-100 题 → 双人复核（或用户+LLM 辅助标注，LLM 标注须过验证铁轨）→ 发布 v1.0
- 每道题固定注入 KB 分科内容（保证跨配置可比性——**KB 内容必须是实验常量**）

### 4.4 指标

| 指标 | 定义 | 意义 |
|---|---|---|
| 裁决一致率 | judge verdict 与 ground truth 一致比例 | 主指标 |
| 校准度 | confidence（高/中/低）与正确率的单调关系（ECE 或秩相关） | 置信度是否可信 |
| 论证多样性 | 7 角色输出两两 embedding 平均距离（如 text-embedding 或 bge） | 回声室量化 |
| 信息量 | 反方是否发现正方未提及的实质问题（LLM-as-judge 或人工抽检） | 对抗质量 |
| 成本/延迟 | token 数、墙钟时间 | 工程约束 |

### 4.5 数据采集架构（论文数据从产品中来）

1. **在线模式**：L1 完成后，config `debate.mode` 按会话轮换（实验期随机分配会话到不同 mode 组合），MemOmics 真实任务自动产生带标注上下文的辩论记录（topic 归一化后自动匹配 BioDebateBench 题 → 得到 ground truth 对照）。
2. **离线补测**：对 BioDebateBench 全部题 × 24 配置跑完整矩阵（约 24 × 80 = 1920 次辩论 ≈ 1.5 万次角色调用；按每角色 ~2K token 估算 ~3 千万 token，成本可控但需预算确认）。
3. **随机种子**：每配置固定 seed 跑 3 次取均值（LLM 非确定性）。

### 4.6 统计方法

- 主分析：裁决一致率 ~ mode × agents × rounds 的 logistic 回归（或分层 GEE，题内相关），报告 OR 与 95%CI；
- 多样性/校准：混合效应模型（题作随机效应）；
- 样本量：80 题 × 24 配置，若效应量（OR≥1.5）可检出，功效充足；不足则补题或降为 4×2×2 主矩阵 + 轮次单因子子实验。

### 4.7 预期结果与论文定位

- 若 H2 成立（judge 梯度主导），论文卖点 = **"架构之争的答案：不是人多人少，是裁判强弱"** + BioDebateBench 基准贡献。
- 投稿建议：先投 NLP 会议（EMNLP 2026 / ACL 2027 findings 或 workshops），若审稿反馈"场景窄"则转投生信期刊（Briefings in Bioinformatics / Bioinformatics method 板块），BioDebateBench 可作为独立 benchmark 论文二次发表。

---

## 5. 实施路线图

> **状态更新（2026-08-10）：P0-P3 已全部实现并验证通过。** 以下验收标准均已达成：
> - P0: `debate_analysis.py` 参数化（mode/rounds/role_model_map + config.yaml debate 段 + 缓存指纹）→ 8 角色真实端到端 95.4s 成功、同架构缓存命中、异架构隔离
> - P1: `skill_evolution` 新增 `record_verdict`（skill.json debate_verdicts + run_record 归档 + topic 去重）；`_reflow_verdict` 自动回流；multi-role-debate 文档修正
> - P2: `enforcement.py` 新增 `debate_gate()` 三级门控（8/8 场景测试）+ 五类信号 + 预算护栏 + `debated_topics` 去重 + config budget 贯通
> - P3: `debate-core` skill 成稿（hermes_home/skills/bioinformatics/debate-core/SKILL.md）+ SOUL.md 铁律 5 门控化

| 阶段 | 内容 | 工作量 | 验收标准 | 状态 |
|---|---|---|---|---|
| P0（地基） | L1 引擎参数化 + config schema + 缓存 key 指纹 + 兼容性 | 0.5-1 天 | 现有 17 份存档 topic 重放：homogeneous 模式结果与现状一致；异构模式 8 角色全部成功 | ✅ 2026-08-10 |
| P1 | L4 裁决回流 + 修正 multi-role-debate 文档 | 0.5 天 | verdict=modify 场景跑通 → record_run → KB 带 evidence 写入 | ✅ 2026-08-10 |
| P2 | L3 触发钩子 ①② + 去重 + 预算护栏 | 1 天 | 真实任务：脚本设计辩论触发一次、结果辩论触发一次、同 topic 不重复 | ✅ 2026-08-10 |
| P3 | L2 debate-core skill 成稿 + SOUL.md 铁律修订 | 0.5 天 | skill 通过自审（含失败恢复流程实测） | ✅ 2026-08-10 |
| P4 | BioDebateBench v1.0（50-100 题标注） | 1-2 天（需用户参与标注） | 专家复核完成，发布 JSON 基准 | ⬜ 待启动 |
| P5 | 实验跑批（24 配置矩阵）+ 统计分析 | 2-3 天（含 LLM 调用时间） | 主指标表 + 回归结果 | ⬜ 待启动 |
| P6 | 论文初稿 | 2-3 天 | 结构完整（Intro/Related/Design/Results/Disc） | ⬜ 待启动 |

合计约 7-11 天。**P0-P3 已交付（辩论核心化完成，随时可用），P4-P6 是论文（需用户参与标注 BioDebateBench 后启动）。**

---

## 5.5 辩论触发设计（什么时候该辩论）

> 本章为 2026-08-10 补充，基于第二轮调研（触发时机维度）。

### 5.5.1 领域共识：从"全量辩论"转向"自适应触发"

调研发现辩论触发机制已收敛出三条原则：

1. **盲目全量辩论有害**（iMAD, arXiv:2511.11306, AAAI 2026 Oral）：对每个 query 都辩论不仅浪费 token，还会**推翻本来正确的单 agent 答案**（degrade accuracy）。iMAD 通过"先自我批判提取 41 个犹豫特征 → 轻量分类器决定是否辩论"实现选择性触发：**省 92% token、准确率反升 13.5%**。
2. **难度分级辩论**（HCP-MAD, arXiv:2604.09679）：多数简单任务用**轻量双 agent 辩论 + 早停**即可，只有复杂任务才升级到集体投票。共识作为动态信号驱动"辩多深"。
3. **单模型自我辩论的隐患**（arXiv:2607.28576 "Sample More, Reflect Less"）：等 token 预算下，模型检查自己输出（含与自己辩论）的 18 组比较**全部输给重复采样投票**——Reflexion 在小模型上甚至"每次都判自己对"静默退化为单次推理。→ 直接支持架构实验的异构模型假设：**同模型多角色可能是最弱的辩论形态，采样投票反而更强**。

另有机制佐证：
- **盲从风险**（DEAR, arXiv:2608.03648）：MAD 中 LLM 高度易盲从，基于置信度/perplexity 的个体评估反而加剧盲从 → MemOmics 的上下文切断设计恰好规避（arXiv:2603.28813 实证：无交互 NI 基线论证多样性最高）。
- **早停机制**：RADAR（双阈值早停控制器）、DySCo（共识稳定即终止）、SMADE-IE（证据驱动+早停）、RUMAD（RL 控制拓扑，省 80% token）——共识：**共识收敛检测 + 双阈值是主流早停方案**。
- **医疗场景先例**（DEEPMED Search, arXiv:2606.29746, IJCAI 2026）：医学深度研究平台用"因果一致性多代理辩论"在**证据合成前**验证检索证据——与 MemOmics"结论合成前辩论"位置一致。

### 5.5.2 触发策略设计：三级门控（Debate Gating）

```
决策点到达 → 门控评估 → L0 跳过 / L1 轻量 / L2 完整辩论
```

**L0 — 不辩论**：chat / lightweight 级；纯格式化/文件操作；已有同 topic 缓存命中。

**L1 — 轻量辩论（新增，成本 ≈ 1/4）**：
- 形式：同模型 3 次采样投票（self-consistency）或单对 pro/con + judge，共 3 次调用
- 适用：statistical 级结论；analysis 级但门控评估为"低不确定性"
- 理论依据：2607.28576（采样投票等成本下不输辩论）+ HCP-MAD（简单任务轻量即够）

**L2 — 完整辩论（现状 7 角色 + judge）**：
- 适用：analysis 级 + 门控评估"高不确定性"（见 5.5.3 信号）
- 保留现有隔离设计（已被 DEAR/2603.28813 证明是正确选择）

### 5.5.3 触发信号（when：五类信号，任一强信号即 L2）

| 信号类别 | 具体信号 | 来源 | 强度 |
|---|---|---|---|
| **阶段信号**（固定） | 结论合成前（现状保留） | rail_review(post) 后 | 中（默认 L1，升级看其他信号） |
| **不确定性信号**（自适应，iMAD 思路） | agent 自评置信度低；候选参数 ≥2 个（如 resolution 0.8 vs 1.0）；agent 输出含犹豫措辞（"可能/也许/建议进一步验证"） | agent 回复解析 + tool args 检测 | 强 → L2 |
| **冲突信号** | 本次结果与上次运行结果显著差异（数值变化 >30%、DEG 数翻倍等）；rail_review 评分临界（passed 但分数接近阈值） | 结果 diff + rail_review 返回 | 强 → L2 |
| **失败信号** | 同一步骤代码失败重试 ≥2 次；error_memory 命中同类历史错误 | terminal 计数 + errors.jsonl | 强 → L2 |
| **影响信号** | 结论将写入知识库（验证铁轨前）；结论将进入最终报告/图注 | 下游动作检测 | 强 → L2（入库结论必须完整辩论） |

**门控实现位置**：`enforcement.py` 新增 `debate_gate(es, stage, signals) -> L0|L1|L2`，在三个钩子（脚本设计/结果/结论）调用。信号采集复用现有 EnforcementState（terminal_count、skills_loaded、rail 评分），新增 `confidence_hints` 解析。

### 5.5.4 辩论内部的早停与升级

1. **轮内早停**：rounds>1 时，若正反方论点 embedding 相似度 >0.9（已收敛），跳过后续轮次（DySCo/RADAR 双阈值思路的简化版）
2. **裁判升级**：L1 裁决 confidence=low 且影响信号为"入库/报告"→ 自动升级为 L2 重辩（HCP-MAD 的 escalated 思路）
3. **辩论预算**：维持 `max_debates_per_session`，但 L1 不计入预算（L1 成本低），只限 L2

### 5.5.5 与现有三级铁律的融合

| 分析级别 | 现状 | 新设计 |
|---|---|---|
| chat / lightweight | 不辩 | L0（不变） |
| statistical | 不辩 | L1 轻量辩论（默认），强信号升 L2 |
| analysis | 必辩（一次） | 门控：低不确定性 L1，强信号 L2；每个决策点独立评估（取消"每会话只辩一次"限制） |

**取消 `debate_done` 会话级布尔**，改为 `debated_topics` 集合（topic 级去重）——同会话多个结论各自门控评估，这是现状"每会话只辩一次"的修正。

### 5.5.6 赛前场景预判（2026-09-18，非生物学辩题换裁判）

**动机**：辩论引擎原本硬编码生物学角色（生物学/统计/生信编辑 + 生物学裁判 + 7 条生物学评分维度）。
当辩题其实是**图表排版、代码工程、投稿规范**这类问题时，用生物学评分维度去裁决是错配的——裁判会问"有没有 marker 特异性证据"，
而这类问题的关键证据其实是"期刊投稿指南条款、灰度/CVD 模拟图"。

**做法**：辩论开跑前多一次 LLM 调用（走 judge 路由），先判断本场属于哪类场景，再据此覆盖**席位身份**与**裁判标准**：

| 环节 | 覆盖内容 |
|---|---|
| 席位（7 个槽位不变） | 每个槽位的 title / task / questions 换成场景身份（如"信息设计编辑""期刊技术审稿编辑"） |
| 裁判 | judge_persona（如"目标期刊图版式与技术审稿编辑"）、judge_focus（必查点）、rubrics（评分键） |
| 证据标准 | evidence_types → 裁判点名的"缺失证据"清单 |

**不变的部分**：槽位标签（pro_biology/pro_statistics/... ）、路由、归档字段、缓存指纹都不变——只换 prompt 里的身份与标准，
所以历史归档、前端渲染、模型路由完全向后兼容（老归档没有 scenario 段就照旧走生物学模板）。

**场景枚举**：bio_data｜stats_design｜figure_layout｜code_engineering｜writing｜ops_environment｜general。

**产物字段**（归档可见）：`scenario`（含 scenario/scenario_label/why/judge_persona/judge_focus/rubrics/evidence_types/pro_roles/con_roles）、
`scenario_model`、`scenario_call_id`；失败时写 `scenario_error` 并静默回退生物学模板（**永不阻断辩论**）。

**开关**：config `debate.scenario_analysis: false` 或 env `MEMOMICS_DEBATE_NO_SCENARIO=1`。

**实测（2026-09-18，排版类辩题）**：辩题「FigA3 热图左侧是否删除纤维型色条、亚群顺序如何排列」→ 判为 `figure_layout / 图表版式与视觉呈现`；
裁判身份"目标期刊图版式与技术审稿编辑"，评分维度 journal_compliance / grayscale_accessibility / information_hierarchy /
annotation_clarity / minimal_change_risk / print_fidelity / visual_consistency；7 个席位全部换成排版/出版类身份；
裁判最终裁决 need_more_info（low）并点名缺"期刊投稿规范原文、灰度/CVD 模拟图、亚群-纤维型映射表"——正是场景预判给出的证据标准。
对照组（生物学辩题「LRP1B+(I) 亚群是否为 AMPK-P 通路特异亚群」）判为 `bio_data`，评分维度仍是 marker_specificity / pathway_score_specificity 等 7 条生物学维度。

**成本**：+1 次调用（约 100~200s，与 L2 的 10+ 次调用相比可忽略）。

## 6. 风险与开放问题

| 风险/问题 | 缓解 |
|---|---|
| 🔴 异构多模型 key 可用性（opencode-go 聚合平台实测未验证全部模型） | P0 验收前先跑 1 次全异构 8 角色冒烟测试 |
| 🟠 多轮次破坏隔离（轮间注入）影响实验纯净性 | 设计上明确"rounds>1 = 轮间隔离"，作为 F3 变量本身纳入分析 |
| 🟠 LLM 非确定性 → 结论不可复现 | 固定 seed、每配置 3 次重复、报告方差 |
| 🟡 辩论成本：24 配置全矩阵 ~3 千万 token | 预算确认；必要时降维（4×2×2 + rounds 子实验） |
| 🟡 judge 自偏袒（Liang 2023：judge 偏袒自己家族模型） | adversarial 模式 judge 用第三家模型（避免与任一辩手同族）；论文中作为讨论点 |
| 🟢 BioDebateBench 专家标注瓶颈 | 分批标注（先 30 题启动实验，滚动扩充） |
| 🟢 缓存污染（mode 间结果串用） | P0 的缓存 key 指纹必须最先落地（P0 级 bug） |

---

## 附录 A：市面调研证据（2026-08-08 核验）

| 论文 | 年份/出处 | 与本设计的关系 |
|---|---|---|
| Improving Factuality and Reasoning through Multiagent Debate (Du) | arXiv:2305.14325 | 同构多实例奠基；3 agents 最优、5 饱和；3 轮优于 1 轮 |
| Encouraging Divergent Thinking through Multi-Agent Debate (Liang) | arXiv:2305.19118, EMNLP 2024 | 同构+judge；2 轮最优；异构时 judge 公平性存疑 |
| Debating with More Persuasive LLMs Leads to More Truthful Answers (Khan) | arXiv:2402.06782 | 异构强辩手+弱裁判 48%→76%；架构 B 最强证据 |
| JudgeLM (Zhu et al.) | arXiv:2310.17631, ICLR 2025 | judge 越大越强；33B 与 GPT-4 一致性 >90% |
| Mixture-of-Agents (Wang et al.) | arXiv:2406.04692 | 便宜异构协作超单一昂贵模型（65.1% vs 57.5% AlpacaEval 2.0） |
| More Agents Is All You Need (Agent Forest) | arXiv:2402.05120, TMLR 2024 | 采样投票随 agent 数单调扩展，与辩论正交 |
| Multi-Agent Debate Strategies: Survey, Taxonomy, and Challenges | arXiv:2607.26212（审稿 ACM CSUR） | 141 篇综述；确认三架构头对头为空白 |
| When AIs Judge AIs: Agent-as-a-Judge | arXiv:2508.02994 | judge 方向综述 |
| MARBLE（辩论驱动生物信息学） | arXiv:2601.14349 | 辩论用于空间转录组域分割/药物靶点 |
| SOAP（临床多代理辩论） | arXiv:2508.21803 | 临床场景辩论先例 |
| ChatDRex / BioAgents / ADAM | arXiv:2511.21438 / 2501.06314 / 2501.08324 | 生信多代理先例（无辩论核心化产品） |

### 第二轮补充：触发时机证据（2026-08-10）

| 论文 | 年份/出处 | 与本设计的关系 |
|---|---|---|
| iMAD: Intelligent Multi-Agent Debate | arXiv:2511.11306, AAAI 2026 Oral | **选择性触发辩论**：犹豫特征分类器决定辩不辩，省92% token、准确率+13.5%；全量辩论会推翻正确答案 → L1/L2 门控的直接依据 |
| HCP-MAD: Heterogeneous Consensus-Progressive | arXiv:2604.09679 | 难度分级：简单任务轻量双 agent+早停，复杂任务升级 → L1/L2 分级依据 |
| Sample More, Reflect Less | arXiv:2607.28576 | 等预算下自我辩论 18 组比较全部输给重复采样投票 → L1 用采样投票、支持异构假设 |
| DEAR: Regulating Debate Relationships | arXiv:2608.03648 | 盲从风险：置信度评估加剧盲从 → 验证 MemOmics 上下文切断设计的正确性 |
| Debate protocol case study | arXiv:2603.28813 | 无交互 NI 基线论证多样性最高 → 隔离设计实证支持 |
| DEEPMED Search | arXiv:2606.29746, IJCAI 2026 | 医学深度研究平台用因果一致性辩论验证证据（合成前辩论）→ 与 MemOmics 结论级位置一致 |
| DySCo / RUMAD / RADAR / SMADE-IE | arXiv:2606.01828 / 2602.23864 / 2604.19005 / 2606.04691 | 早停机制：共识稳定终止、双阈值、RL 拓扑控制、证据驱动早停 → 轮内早停设计参考 |

## 附录 B：关联记忆与既有约束

- 三级铁律体系（分析级 8 步含 debate、统计级 7 步、轻量级 5 步）——触发分级沿用此体系，不新增第四级
- 铁律 -6：禁止多角色 LLM 并发调用（保持串行，`multi_model` 模式同样串行）
- 知识库验证铁轨：裁决入 KB 必须带 evidence
- 铁律 5：辩论引用只能来自 `search_papers()`（PMID/DOI），KB 线索不可作引用来源
- `_debates/` 存在 8/1 前失败存档残留（如 54a1c29322da8242.json）——P0 阶段顺手清理
