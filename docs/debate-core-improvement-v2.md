# 辩论模块完善设计 v2（草案，待批准后实施）

> 日期：2026-08-27 ｜ 状态：设计文档（尚未改代码）
> 依据：2026-08-27 测试报告（106/106 离线通过；修复 token 上限与 JSON 扫描 2 缺陷）+ 多层改进建议
> 原则：全部改动向后兼容；config 不配置时行为=现状；每个改动有离线测试锁死；缓存指纹纳入新参数防串用。

---

## 0. 目标

把“观点生成器”升级为“证据审查器”：

1. **可信度**：每个论点必须挂在可溯源证据上（PMID/DOI/文件/数值），无证据必须明说；
2. **诚实度**：角色必须主动报告自己领域的硬伤/失效条件，而非只站在立场上辩护；
3. **可裁决性**：裁判按固定 rubrics 打分，证据不足时明确列“缺什么”而不是被迫二选一；
4. **可验证性**：引入多裁判一致性与校准指标；为 P4 BioDebateBench 铺路。

---

## 1. 现状问题（测试与代码审计确认）

| # | 问题 | 证据 | 严重度 |
|---|---|---|---|
| 1 | 角色提示词只要求“论证/质疑”，无证据契约，LLM 常给无源断言 | PRO/CON prompt 无“必须带来源”条款 | 🔴 高 |
| 2 | 300 字上限塞不下证据链；实测论点约 400-500 字被截 | live_L2_fixed pro 长度 439-465；部分角色回退 2021 字 reasoning 草稿 | 🟠 中高 |
| 3 | judge max_tokens 2048 被推理消耗 → 100% 静默降级 need_more_info/low | 本测试已修复但需固化为配置项 | 🟠 中（已部分修复） |
| 4 | 正反方同质化，只是“支持/质疑”镜像 | 8 角色 7 个模板结构完全相同 | 🟠 中 |
| 5 | 裁判无 rubrics，单凭说服力；单裁判 bias 无交叉验证 | adversarial 实测 need_more_info+high 矛盾裁决 | 🟠 中 |
| 6 | KB 注入是碎片拼接（≤4 条 × 800 字符），无元数据/冲突来源 | _auto_kb_injection 实现 | 🟠 中 |
| 7 | history 编辑自由辩论，不做相似度匹配 | prompt 无匹配要求 | 🟡 低 |
| 8 | rounds 只有下限无上限；verdict 允许非字符串；L1 judge 失败无 error 标记 | 极端测试发现 | 🟡 低 |

---

## 2. 总体架构（变更后）

```
输入 topic/context/KB/evidence                     证据层（新增）
   │                                                        │
   ▼                                                        ▼
role_preset 装配（7 or 9 角色，可配置）  ←── 结构化证据卡（PMID/DOI/结论/效应量/冲突/反证）
   │                                                        │
   ▼                                                        ▼
每角色 prompt = 角色设定 + 证据契约 + 领域自检清单 + 结构化输出 schema
   │
   ▼
正方 N 角色（独立调用，互不可见） ──► 反方 N 角色（独立调用）
   │                                     │
   └──────────────┬──────────────────────┘
                  ▼
        judge×K（K=1 现状；K=3 可选多裁判投票）
                  ▼
        verdict + confidence + recommended_params + 缺什么
                  ▼
     一致性门禁 → 缓存/归档 → record_verdict → 效用追踪（新）
```

---

## 3. 分层设计

### 3.0 统一“证据契约”（所有角色共享，写进每个 prompt 头部）

新增 _EVIDENCE_CONTRACT 段落：

```
## 证据契约（必须遵守）
1. 每个观点必须有证据锚点：[PMID:xxxxx] / [DOI:xxxxx] / [KB源:文件] / [数据:数值]。
2. 无直接证据的推理，必须标注 [仅是推理] 且不得作为论点计分。
3. 给出证据等级：P(实验/文献) ≥ C(证据卡) ≥ I(推理)。
4. 若你的专业领域内存在失败条件/已知反例，必须列出；不得只报“支持/质疑”。
5. 若证据不足，明确写“本领域证据不足，不可下结论”，并说明缺什么。
```

### 3.1 角色提示词改造（7+2 角色）

#### 3.1.1 输出结构统一（替代自由散文）

每个角色输出 JSON：

```json
{
  "claims": [
    {"claim": "…", "evidence": "[PMID:…] / [KB源:…] / [数据:…]",
     "level": "P|C|I", "confidence": "high|medium|low", "risk_boundary": "失效条件…"}
  ],
  "self_audit_failures": ["样本量不足…", "未校正多重比较…"],
  "alternative_hypothesis": "若…，则结论可能为…（可检验）",
  "needed_evidence": ["缺什么数据/文献…"]
}
```

#### 3.1.2 各角色专属改造点

| 角色 | 新增专属要求 |
|---|---|
| 正方·生物学 | 证据等级必须标注；marker 特异性需给双细胞类型对比数据或文献；无文献则 [I] |
| 正方·统计学 | 必须报告：是否有功效分析、多重比较校正方法、模型诊断；没有就写进 self_audit_failures |
| 正方·生信 | 必须给 QC 数值档位（分布分位数）而非单个均值；参数敏感性必须说明区间 |
| 反方·生物学 | 必须给出可检验替代假设（如“其实同源亚群，可用 X 标记验证”）；引用反证文献 |
| 反方·统计学 | 必须指出：若按用户样本量，该效应量的功效是多少（power 估算或说明无数据）；未估计则 self_audit |
| 反方·生信 | 必须做参数敏感性陈述：换 res=0.x 时聚类稳定性是否变化；给 bootstrap/重复性证据或 [I] |
| 历史经验 | 改为 evidence matcher：检索 error_memory，输出〔相似度/适用性/置信度〕+ 教训，不做自由辩论 |
| 【新增】实验设计编辑 | 检查 design/对照/批次/混杂（如 donor effect），输出 confounding 风险清单 |
| 【新增】可重复性编辑 | 检查随机种子/版本/环境/运行时长，输出可复现性评分与风险 |

> 新增角色通过 `role_preset: "core7" | "core9"` 开关，默认 core7，向后兼容。

### 3.2 裁判改造

#### 3.2.1 评分 rubrics（替代“说服力”打分）

`scores` 改为按维度：

```json
{
  "rubrics": {
    "evidence_quality": 1-10,
    "effect_size": 1-10,
    "confounding_control": 1-10,
    "prior_literature": 1-10,
    "reproducibility": 1-10,
    "pro_claim_coverage": 1-10,
    "con_claim_coverage": 1-10
  },
  "verdict": "support|modify|need_more_info",
  "confidence": "high|medium|low",
  "recommended_params": {},
  "missing": ["必要证据/数据清单"],
  "reasoning": "≤500字，引用谱系：哪些论点挂在哪条证据上"
}
```

#### 3.2.2 裁决决策树（写入 prompt）

```
若 pro 与 con 均证据不足 → verdict=need_more_info, confidence=low, 列出 missing；
若 modify 但无 recommended_params → 禁止（一致性门禁已覆盖）；
若 confidence=high 但 missing 非空 → 强制降 confidence=medium（新规则）；
若双方接近 → 必须输出 need_more_info + missing，不得强行 support/modify。
```

### 3.3 证据层（新增，P1 优先实施）

1. **证据卡 schema**（`_EvidenceCard`）：
   `{id, type: paper|kb|data|error, title, authors?, year, pmid/doi, conclusion, effect, n, direction, conflict_with: [], source_file, retrieved_at}`
2. **注入流程**：`debate_analysis` 收到 evidence 参数或自动 `search_papers/query_logs` 后组装证据卡；
   - 正方注入支持性/相关证据；反方额外注入**反证/阴性结果**检索（negative-evidence 钩子）；
   - KB 注入升级为“系统卡+知识点”，带 file 与日期；
3. **引用校验**：裁判或后处理扫描 claims/evidence，若出现 [PMID/DOI] 不在证据卡集合内 → 标记 citation_unverified；
4. **裁决回查**：recommended_params 中每个关键参数必须能在证据卡中找到来源，否则结果标记 `param_unverified`（软告警，不阻断）。

### 3.4 多裁判一致性（可选开关 `judge_count`，默认 1）

| 配置 | 行为 | 成本 |
|---|---|---|
| judge_count=1 | 现状，单裁判 | 1× |
| judge_count=3 | 3 个独立裁判（默认 role_model_map/judge 组轮换模型），一致性得分 majority_vote + agreement | 约 ×2-3 |
| judge_count=3 且 confidence 分裂 | 自动加判/降级；不一致结果不回流 | ×2-3 |

输出新增：`judge_consensus: {agreement, votes, disagreements}`；
指纹新增 `judge_count` 与 `role_preset`（防缓存串用）。

### 3.5 工程加固（P2）

1. `rounds` 上限：`min(max(1,int(rounds)), cfg.rounds_max or 5)`；
2. verdict 枚举校验：`verdict` 必须 ∈ {support, modify, need_more_info, ok} 且为字符串；
3. L1 judge 失败：结果增加 `judge_error: true`（不再静默降级）；
4. `/admin` 或 config 增加 `debate.max_tokens.judge/role/l1_role/l1_judge`（默认 8192/2048/2048/8192，与本次修复一致）；
5. reasoning fallback 处理：角色内容为空时，若为 reasoning 草稿且含 JSON 关键词 → 尝试提取；仍失败 → 标记 `draft_only: true` 并计为低质量（提示下游不采纳）；
6. fingerprint 追加 `evidence_fingerprint`（证据卡 id 列表 hash），不同证据卡不得复用缓存。

---

## 4. 缓存/兼容性策略

| 项 | 策略 |
|---|---|
| config 缺省 | mode=homogeneous, role_preset=core7, judge_count=1, evidence_mode=off → 行为=现状 |
| 指纹 | 追加 role_preset/judge_count/evidence_fingerprint/rounds_max；旧缓存键不变（向后可读） |
| 旧存档 | 保留 `_load_debate` legacy hash 与无指纹回退 |
| 退出开关 | `MEMOMICS_DEBATE_LEGACY_PROMPTS=1` 强制使用 v1 提示词（回退用） |

---

## 5. 测试计划

| 阶段 | 内容 | 验收 |
|---|---|---|
| T1 离线 | 新增 20-30 项：证据契约解析、结构化 claims 校验、多裁判 consensus、engine 开关、fingerprint 新参数、rounds 上限、verdict 枚举、L1 judge_error | 全部通过，且既有 106 项不回归 |
| T2 线上 L1/L2 | core7 证据卡模式 1 次；core9 1 次；judge_count=3 1 次 | verdict 正常解析、isolation 8/8 → 9/9 call_id 唯一、归档/缓存正常 |
| T3 校准抽样 | 同 3 题 × {homogeneous, adversarial} × {judge_count=1,3} 记录 verdict/confidence | 产出对比表，标注需人工复核题 |
| T4 回归 | 既有全部测试 + 新测试 | 100% 通过 |

---

## 6. 改动清单（批准后按此实施）

| 文件 | 改动 | 优先级 |
|---|---|---|
| memomics/bio_tools/debate_analysis.py | 提示词 v2、证据契约、结构化 schema 解析、多裁判、证据卡注入、rounds 上限、verdict 枚举、L1 judge_error、max_tokens 配置化 | P0 |
| memomics/bio_tools/kb_search.py（只读） | 供证据卡组装复用；无改动则用现有 _search_kb | P1 |
| webui/enforcement.py | debate_gate 支持 uncertainty/high_impact 不变；新增 judge_count/role_preset 从 config 读取；预算按 judge_count 折算 | P1 |
| hermes_home/config.yaml | debate: 增加 role_preset/judge_count/max_tokens/rounds_max/evidence_mode | P1 |
| hermes_home/skills/bioinformatics/debate-core/SKILL.md | 更新机制说明/排障（并发描述滞后已确认） | P2 |
| hermes_home/SOUL.md | 铁律 5 措辞更新（证据卡替代“KB 背景”） | P2 |
| docs/debate-core-design.md | 追加 v2 章节（本设计） | P2 |
| webui/tests/test_debate_extreme.py | 新增上述测试 | P0 |

---

## 7. 风险与预算

| 风险 | 影响 | 缓解 |
|---|---|---|
| prompt 变长 → 单次 token 增加 | 成本约 +30-60% | 默认 core7/evidence_mode=off；core9/judge_count=3 显式开启 |
| 多裁判成本 | ×2-3 | 默认 1；预算护栏按 judge_count 折算 |
| 新提示词改变裁决行为 | 与旧缓存不一致 | fingerprint 含 v2 标记；可一键回退 LEGACY_PROMPTS |
| judge_count=3 分歧 | 需要仲裁 | 简单多数 + 分歧时强制 need_more_info / low |
| 证据卡检索失败 | 无证据可挂 | 降级为 [I] 并计入 self_audit；不影响主流程 |

---

## 8. 待办（批准后启动）

1. P0 提示词 v2 + 证据契约 + 工程加固（半天-1天）；
2. P1 证据层 + config 贯通 + 多裁判（1天）；
3. P2 文档 + SOUL/skill 同步 + 全面回归（半天）；
4. P3 可选：核心 9 角色 preset + judgment 校准小样本实验（后续）。


---

## 9. 实施状态（2026-08-27 已按 P0→P1→P2 完成并验证）

- ✅ P0 提示词 v2：证据契约、结构化论据（claims/self_audit_failures/alternative_hypothesis/needed_evidence）、裁判 rubrics + 决策树 + missing。
- ✅ P0 工程加固：rounds 上限（rounds_max 默认5）、verdict 枚举校验、L1 judge_error 标记、max_tokens 配置化、reasoning draft_only 标记。
- ✅ P1 证据层：evidence_cards 参数 + evidence_fingerprint（证据变化→新缓存）。
- ✅ P1 多裁判/角色预设：judge_count(1-3) 温度采样 + 简单多数；role_preset core7/core9（新增 design_review / reproducibility_review）。
- ✅ P2 配置贯通：config.yaml debate 段 + SKILL.md + SOUL.md 铁律5 + 本文档。
- ✅ 验证：离线 113/113 通过（含 72 项极端/新特性测试）；线上 L1/L2/core9 实跑全部返回结构化 rubrics/missing，隔离/归档/缓存正常。
- ⚠️ 遗留：角色论点仍偶发 reasoning 草稿（draft_only_roles 非空，如 core9 的 pro_statistics）；L1 v2 耗时由 ~36s 升至 ~153s（成本换证据质量），可按场景降级 l1_role max_tokens 或关 v2。

