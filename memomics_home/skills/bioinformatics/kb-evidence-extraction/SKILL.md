---
category: Literature
name: kb-evidence-extraction
description: >
  把文献库/交互框文献提炼成可复核的 claim 级知识库条目（kb-evidence-v2）。每条原子结论带
  L0-L3、英文原文 quote、章节/图号、测序或实验技术、物种/组织、实验对象、队列/分组、背景和
  claim-specific validation；同时提取文章明确用于注释的 marker、湿实验条件/试剂、类器官/3D
  培养条件。AI/科研智能体论文走独立 ai_agent/<子类>（frameworks/benchmarks/evaluation/
  agent_design/systems/applications）。L2 只认针对该结论的湿实验，L3 只认临床试验或足够规模
  独立临床队列。触发：提炼文献进知识库 / 补充知识库 / 评估知识可信度 / 分析辩论前查 KB。
trigger:
  when:
    - 用户要求"把这篇/这些文献提炼进知识库"、"提取知识/参数进知识库"
    - 交互框里上传/指定论文或结果，要求"存进知识库/按证据链入库"
    - 文献库选中文献后点「🧠 一键知识提取 / ⚡ 一键全流程」
    - 分析/辩论前需要查参数、结论、队列背景（走 search_knowledge，不重新提炼）
    - 用户要求"构建/补充知识库（带证据链）"、"知识库搭建"
    - 需要评估知识库条目可信度（L0-L3）时
    - 一键全流程（翻译+提炼+证据链知识+双语锚定）
  not_when:
    - 用户只要论文解读/9 项摘要（那走 literature-full-summary / summarize_paper）
    - 只是提取生信参数清单浏览而不入库（那走 literature-param-extraction）
  rules:
    - "只收 8–15 条高价值原子生物结论；不把 marker/pathway/chemical 大清单倒进知识库"
    - "每条必须有英文原文 quote + 章节/图号 + 技术 + 对象 + 队列 + 背景"
    - "L2 必须是针对该结论的湿实验/功能验证，claim_specific=true；整篇有湿实验不等于每条 L2"
    - "L3 只给临床试验/随机/前瞻或足够规模独立临床队列；小样本人组织不是 L3"
    - "综述/二手来源最高 L1；L0 保留文章出处但明确无直接支持证据"
    - "文章明确用于注释的 marker 进 markers；湿实验的条件/试剂/读数进 wet_lab"
    - "类器官/3D 培养进 organoids；组织与模型类型用受控词表，不新造目录名"
    - "物种统一用专业名（Homo_sapiens/Mus_musculus/Rattus_norvegicus 等），不混用 human/mouse/rat"
    - "入库必须过 save_knowledge 铁轨：evidence 必填；quote/上下文缺失则降级并标 review_required"
    - "入库后必须能被 search_knowledge 立即检索；分析/辩论前先查 KB，不靠提示词自觉"
    - "多文章结论冲突时并列，保留各自对象/队列/背景，不合并"
---

# 知识库证据链提炼 Skill（kb-evidence-v2）

## 干什么

把文献库里的文献提炼成**可复核、可检索、可被后续分析引用**的 claim 级知识，而不是整篇论文摘要。

- 执行工具：`kb_extract_from_paper(file_or_title)`（单篇）/ WebUI 文献库「🧠 一键知识提取」/「⚡ 一键全流程」
- 落盘：人读版 `memomics_home/papers/knowledge/<文件名>.md`；机读条目 `knowledge_base/五级目录/*.yaml`（顶层 `claims` + `evidence_chain`）
- 方法/参数/QC 继续走 `source_only` 条目，不与生物结论混级

## 两个入口，同一套提取

| 入口 | 触发 | 实际调用 |
|---|---|---|
| 交互框 | 用户贴论文/指定文献/上传 PDF 后说“提炼进知识库/按证据链入库” | 先 `literature_import`（若还不在库）→ `kb_extract_from_paper(file_or_title)` |
| 文献库 | 选中文献 → 「🧠 一键知识提取」/「⚡ 一键全流程」 | 同一个 `kb_extract_from_paper`；一键全流程额外做翻译/摘要/双语锚定 |

两处共用 `evidence_chain.normalize_knowledge_evidence`、`save_knowledge` 和同一份 YAML `claims`；不要为交互框另写一套摘要式入库。

## AI / 科研智能体论文：独立分类

AI 论文（agent、LLM、benchmark、evaluation、科研智能体）**不进生物五级目录**，走：

```text
knowledge_base/ai_agent/<subcategory>/<paper_ai_*.yaml>
```

`subcategory` 固定为：

| 子类 | 收什么 |
|---|---|
| `frameworks` | 多智能体/agent 框架、架构、系统 |
| `benchmarks` | benchmark、数据集、评测任务套件 |
| `evaluation` | 评测方法、指标、judge、人工评审 |
| `agent_design` | planning / memory / tool use / reflection / 协作范式 |
| `systems` | runtime、orchestration、serving、基础设施 |
| `applications` | 科学发现、生物医学、化学、地球科学等应用 |
| `overview` | 综述、survey、领域全景/taxonomy |
| `general` | 无法归入以上 |

AI 提取 schema 与生物不同：只收 `problem / method / architecture / contributions / benchmarks / results / limitations / claims`；benchmark 的 `name/task/metric/result/baseline` 必须原文原样，claims 必须有 `source.quote + locator`。不要给 AI 论文硬套 marker/湿实验/类器官。

分类由 `literature_library._rule_classify` + LLM 分类共同决定；标题含 agent/LLM/benchmark/evaluation 等强信号会自动识别为 `domain=ai`。

## 借鉴的阅读逻辑

- **professional-paper-interpretation**：每条结论写清“样本 → 平台/实验 → 上游处理 → 统计判据 → 结论”的证据←手段链。
- **nature-paper-card**：claim–evidence 矩阵；逐条写“支持什么、不能支持什么、gap 是什么”，防止把相关写成因果。
- **paper-summary**：知识库只保留高价值结论，不把论文的所有图表、marker、通路、化合物清单复制进来。

## 输出：只收原子结论

每条 claim 必须是一个可独立判断真假的生物结论，不要把“方法 + 结果 + 推测”塞进一句。

```json
{
  "biology": {
    "conclusions": [
      {
        "id": "C01",
        "text": "去神经 7 天时，超过 92% 的小鼠 plantaris NMJ 缺乏可检测的轴突终末接触。",
        "evidence_level": "L2",
        "source": {
          "doi": "10.1016/j.devcel.2026.03.010",
          "locator": "Results 第2段 / Fig.3D–E / PDF p.7–8",
          "quote": "In Den muscle, over 92% of NMJs lacked detectable axon terminal contacts ...",
          "type": "primary"
        },
        "assay": "CUBIC 组织透明化 + BTX/SV2/NF 免疫荧光 + 三维共聚焦",
        "experimental_object": "小鼠 plantaris NMJ",
        "cohort": "basal/Den/OVL；n=3–6 mice；36–84 NMJs",
        "background": "检验 SynM 转录重塑是否对应真实的 NMJ 神经支配丢失，而非仅转录相关。",
        "validation": {
          "method": "三维免疫荧光形态定量，直接测量轴突末梢与 AChR 终板重叠",
          "locator": "Fig.3D–E / PDF p.7–8",
          "claim_specific": true,
          "design": "wet_lab"
        },
        "evidence_type": "wet_lab",
        "grading_reason": "针对该结构结论有直接湿实验；不证明分子因果或人类普适性。"
      }
    ]
  },
  "bioinfo": {
    "sequencing": [],
    "pipeline": [],
    "software": [],
    "parameters": [],
    "qc_params": [],
    "reference_genome": "",
    "databases": []
  }
}
```

## 证据等级（逐 claim，不按整篇）

| 级别 | 含义 | 硬判据 |
|---|---|---|
| **L0** | 作者推测/未来工作/无直接支持证据 | 有文章出处和 quote，但 validation 不能支持该 claim；不能当结论用 |
| **L1** | 有来源但无针对该结论的湿实验/临床验证 | 组学、观察性、相关性、综述转述、纯计算发现；可作候选证据 |
| **L2** | 有针对该结论的直接湿实验/功能验证 | validation 必须是该 claim 的 IF/IHC/RNAscope/qPCR/Western/流式/动物或细胞实验/功能干预，且 `claim_specific=true`、有图号 |
| **L3** | 临床试验或足够规模独立临床验证 | 临床试验/随机/前瞻/多中心或独立临床队列，报告 n；默认 n≥100，可用 `MEMOMICS_L3_MIN_N` 调整 |

### 防虚高硬规则

1. **整篇有湿实验 ≠ 每条 L2。** 如果一条结论的 validation 是 snRNA-seq、scRNA-seq、UMAP、聚类、差异表达、富集、CellChat、相关性分析，即使论文别处做了 IF/RNAscope，也只能 L1。
2. **L3 降级后必须重新跑 L2 检查。** 小样本人组织（如 n=5 vs 8、RNAscope 3/组）不是 L3；若该 claim 没有直接湿实验，也不能自动变 L2。
3. **二手综述最高 L1。** 综述引用原始实验，不等于综述完成了该实验；`source.type=secondary` 时不得给 L2/L3。
4. **quote 必须逐字来自原文。** 后端会把 quote 与 PDF/Markdown 原文归一化匹配；不匹配则降 L1 并标 `review_required`。
5. **上下文必须完整。** 缺 assay/object/cohort/background，或 locator 不含章节/图号/页码，L2/L3 降 L1。
6. **L0 不是“没有来源”。** L0 仍必须有 DOI、quote、locator；它表示“有文章出处，但没有直接支持证据”。

## 每条 claim 必填

- `text`：一个原子结论，中文，不混方法和推测。
- `source.doi`、`source.locator`、`source.quote`、`source.type`（primary/secondary）。
- `assay`：直接相关的测序/实验技术；不适用写“不适用”。
- `species`：专业物种名列表（Homo_sapiens/Mus_musculus/Rattus_norvegicus…）。
- `tissue`：受控组织名（example_tissue/liver/brain…）。
- `experimental_object`：物种、组织、细胞/模型。
- `cohort`：n、分组、条件、独立队列；未报告写“原文未报告”。
- `background`：该结论回答的具体问题，不写套话。
- `validation.method`、`validation.locator`、`validation.claim_specific`、`validation.design`。
- `evidence_type`：computational/wet_lab/clinical/secondary/speculation/observational。
- `grading_reason`：为什么是该级，明确“不能支持什么”。

## 注释 Marker 与湿实验（实验性文章必看）

除 claim 外，`biology` 还可带两个结构化数组；文章没写就输出 `[]`，不要编造。

### `markers[]`：文章明确用于注释/鉴定的 marker

- `gene`、`cell_type`（或 region/population）、`direction`（up/down/na）、`assay`、`context`、`source{doi,locator,quote}`。
- 只收“用来定义/区分细胞类型或区域”的 marker（如 Pax7→MuSC、Myh4→IIb 肌核），不要把差异基因表全倒进来；≤20 条。

### `wet_lab[]`：湿实验条件、试剂、读数

- `experiment`（CUBIC/RNAscope/IF/动物干预/细胞实验…）、`model`、`species`、`conditions`（分组/时间点/处理）、`n`。
- `reagents[]`：`name`、`vendor`、`catalog`、`dose`（浓度/稀释/剂量）。
- `readout`：定量指标；`source{doi,locator,quote}`。
- 只收真正做过的湿实验；≤8 条。

### `organoids[]`：类器官/3D 培养

- `name`、`species`、`tissue`、`model_type=organoid`、`media`、`cytokines[]`、`matrix`、`duration`、`passage`、`readout`、`source`。
- 物种/组织必须走下面的受控名；没有类器官就输出 `[]`；≤8 条。

### 组织与模型类型（受控词表）

- 组织：`example_tissue` / `cardiac_muscle` / `smooth_muscle` / `liver` / `brain` / `lung` / `kidney` / `heart` / `blood` / `pbmc` / `bone_marrow` / `spleen` / `intestine` / `colon` / `skin` / `adipose` / `pancreas` / `retina` / `eye` / `bladder` / `uterus` / `prostate` / `ovary` / `testis` / `thymus` / `tumor` / `other`。
- 模型类型：`in_vivo` / `ex_vivo` / `organoid` / `cell_line` / `primary_cells` / `human_sample` / `other`。
- 中文/英文别名（如 肌肉→example_tissue、肝→liver、大鼠→Rattus_norvegicus）由后端 canonical 化；不要新造目录名。

### 物种统一

`experimental_object`、`species[]`、YAML 目录统一用专业名：

`Homo_sapiens` / `Mus_musculus` / `Rattus_norvegicus` / `Macaca_mulatta` / `Macaca_fascicularis` / `Danio_rerio` / `Drosophila_melanogaster` / `Caenorhabditis_elegans` / `Sus_scrofa` / `Oryctolagus_cuniculus`

不要在同一篇里混用 `human`/`mouse`/`rat` 或 `小鼠`/`大鼠` 作为物种字段；中文正文可保留“小鼠”，但 `species` 必须是上述专业名。

## 入库形状

YAML 顶层同时保留：

- `content`：人读 Markdown，每条结论显示 `[Lx]`、quote、位置、技术、对象、队列、背景、验证和待复核标记。
- `claims`：机读 claim 列表（上面 schema），供后续分析直接按 claim 检索。
- `evidence_chain`：`standard=kb-evidence-v2`、等级分布、最高级、`source_verified`、`review_required`。

方法/参数/QC 条目使用 `grading: source_only`，不参与 L0–L3。

## 写入后必须能查：检索契约

写入成功不等于可调用。`save_knowledge` 成功后会失效 `kb_search` 的进程内 FTS/文件缓存，保证**不重启**就能查到新条目。

分析、辩论、选参数、下结论前，必须调用：

```python
search_knowledge(
    query="NMJ 去神经 结构 重塑",
    species="mouse", tissue="example_tissue", direction="aging",
    kind="all",          # all | claims | parameters
    level="",            # 可选 L0-L3 过滤
    max_claims=8, max_parameters=10,
)
```

返回：
- `claims[]`：`evidence_level`、`text`、`source{doi,locator,quote,type}`、`assay`、`experimental_object`、`cohort`、`background`、`validation`、`source_file`。
- `parameters[]`：从 `03_测序方法/02_质控参数` 的「关键参数/软件/QC」解析出的 `tool/param/value/context`。
- `conflict_candidates[]`：不同 DOI 但共享主题词的 claim 对，附双方队列/对象；**并列呈现，不合并**。
- `evidence_policy`：引用规则（DOI/quote/cohort/object/background 必写）。

### 何时必须查（硬触发）

- 第一次执行分析代码/terminal 非只读命令前；
- 调用 `debate_analysis` 前；
- 选择 QC 阈值、聚类 resolution、软件版本、统计方法前；
- 写“结论/机制/因果/临床相关性”前；
- 用户问“有没有文献支持/别人怎么做/这个参数多少”。

`webui/enforcement.py::knowledge_gate` 会在上述场景硬拦第一次执行/辩论，要求先调用 `search_knowledge`；只读 terminal 豁免。这是工具门禁，不依赖提示词自觉。

### 多文章冲突

不同文章结论可以相反，只要每条带齐 `experimental_object`、`cohort`、`background`、`evidence_level`，就并列作为不同条件下的论据；禁止把冲突结论合并成一句“平均结论”，也禁止只引用支持自己的一篇。

## 工作流

1. `kb_extract_from_paper(file_or_title)` 读取 PDF/Markdown。
2. LLM 按 schema 输出 8–15 条原子结论；只保留有 quote 和定位的条目。
3. 后端 `evidence_chain.normalize_knowledge_evidence` 做 claim-specific 校验、quote 回查、上下文完整性、二手来源限制、L2/L3 降级。
4. `save_knowledge` 写入 `content` + `claims` + `evidence_chain`；`source=literature` 必须有 evidence。
5. 人读版 `papers/knowledge/<stem>.md` 同步生成，显示待复核条目。

## 使用口径

- **L1**：可作候选假设、检索线索、文献背景；不能写成“已被实验证实”。
- **L2**：可用于方法设计/机制假设，但要保留“模型、样本量、物种、条件”的边界；不能外推到所有人/所有组织。
- **L3**：可用于临床相关性/转化判断；仍要区分临床试验、前瞻队列与回顾性观察。
- **L0**：只作研究问题/未来方向，不作论据。
- 任何 L2/L3 在进入最终论文结论或自动决策前，仍应人工核对 quote、图表和原始实验。

## 与相邻 skill 的分工

| Skill | 方向 | 产物 |
|---|---|---|
| **kb-evidence-extraction（本 skill）** | 给 AI 用的 claim 级证据 | `claims` + `evidence_chain` → knowledge_base |
| professional-paper-interpretation | 中文精读、证据←手段 | 人读深度报告 |
| nature-paper-card | Claim–Evidence 审计、边界分析 | paper card + 矩阵 |
| paper-structured-extraction | 原文行号、QC/参数 | 结构化精读报告 |
| paper-summary / literature-full-summary | 快速概览 | 9 项/15 字段摘要 |

## 铁律

- 入库必须过 `save_knowledge`（evidence 必填、unverified 拒收），不得绕过铁轨手写 YAML。
- 不把 marker/pathway/chemical 大清单当结论；化学/类器官信息只在确有复用价值时单独成条。
- 多值物种/组织字段拆单一合法段；assay_type 使用 RNA/ATAC/spatial/bulk。
- 批量任务失败不硬重试：先看 rejected 原因（路径段非法/LLM 格式/quote 不匹配）再决定。
