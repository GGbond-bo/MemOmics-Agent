# AI / 科研智能体 文献库（knowledge_base/ai_agent/）

> 独立分类：AI agent / 科研智能体类文献的架构、benchmark 与评测范式。
> 与生物学问库（物种五级目录）解耦——这类文献没有物种/组织维度，横向对比才是主要用途。
> 入库方式：`save_knowledge(domain="ai", direction="<子类>", ...)` → `ai_agent/<子类>/<name>.yaml`
> 子类约定：`frameworks`（系统与框架架构）| `agent_design`（设计范式与自改进）| `benchmarks`（基准与数据集）| `evaluation`（评测方法）| `overview`（横向综合）

## 收录清单（截至 2026-10-11，共 12 条）

### frameworks —— 系统与框架架构（7）
| 条目 | 系统 | 出处 | 一句话 |
|---|---|---|---|
| `biomni_general_biomedical_agent` | Biomni | Stanford 等（预印本 2025） | 通用生物医学 agent：动作空间（150 工具+105 软件包+59 库）+ CodeAct |
| `deeprare_rare_disease_diagnosis_nature2026` | DeepRare | *Nature* 651 (2026), DOI 10.1038/s41586-025-10097-9 | 罕见病诊断：三层 MCP + 可溯源推理链，R@1 57.18% |
| `chemgraph_agentic_computational_chemistry` | ChemGraph | *Commun Chem* (2025), DOI 10.1038/s42004-025-01776-9 | LangGraph/ReAct 编排 ASE/xTB/MACE/DFT，多 agent 使 GPT-4o 达 100% |
| `biomaster_multiagent_bioinformatics_workflow` | BioMaster | *Bioinformatics* (2025), bioRxiv 10.1101/2025.01.23.634608 | Plan/Task/Debug/**Check** 四角色 + 双 RAG，防累积误差 |
| `paper2agent_paper_to_mcp_agent` | Paper2Agent | *Nature* (2026), DOI 10.1038/s41586-026-11044-y | 论文→MCP agent；100 篇→74 篇 agent 化、599 工具（593 验证通过） |
| `cassia_multiagent_cell_annotation` | CASSIA | *Nat Commun* (2025), DOI 10.1038/s41467-025-67084-x | 细胞注释多 agent：质量分 + 共识分 CS，970 细胞类型 |
| `chemcrow_llm_augmented_with_chemistry_tools` | ChemCrow | *Nat Mach Intell* 6:525 (2024), DOI 10.1038/s42256-024-00832-8 | 18 工具 + ReAct 的早期范式；RoboRXN 真实合成 4/4 成功 |

### agent_design —— 设计范式与自改进（2）
| 条目 | 系统 | 出处 | 一句话 |
|---|---|---|---|
| `co_scientist_google_nature2026` | Co-Scientist | *Nature* 655 (2026), DOI 10.1038/s41586-026-10644-y | Elo 自对弈锦标赛生成新假设；test-time scaling 未见饱和；**代码不公开** |
| `sciencebuddy_recursive_self_improvement` | ScienceBuddy | arXiv:2609.17523v1 (2026) | recursive-in-recursive：内层进化 harness、外层 GRPO 训模型；42.2%→73.3% |

### 横向综合（3）
| 条目 | 内容 |
|---|---|
| `overview/ai_agent_research_paradigms_9papers` | **研究思路谱系**：5 条谱系（动作空间派 / 论文即 agent / 领域专用 / 防误差传播 / 自我改进）+ 3 条设计公理 + "发现 vs 执行"分野 |
| `benchmarks/ai_benchmark_inventory_9papers` | **全部 benchmark 清单**：公开基准复用表 + 9 篇自建基准 + 对抗测试 + 湿实验验证 + 选型建议 |
| `evaluation/ai_agent_evaluation_paradigms_9papers` | **评测范式卡**：专家盲评 rubric / LLM-as-judge（含 ChemCrow 反例）/ Elo 自对弈 / 分层准确率 / 消融 / 对抗 / 真实闭环 + 检查清单 |

## 使用建议
- **做同类系统前**先读 `overview/ai_agent_research_paradigms_9papers`（看清自己在哪条谱系上）；
- **设计评测前**读 `evaluation/...` 与 `benchmarks/...`（避免重复踩"LLM judge 偏好流畅""只自建不强外部真值"两个坑）；
- **复现某篇**时读对应条目末尾的「可复用点」与「元信息」（代码、数据、许可）；
- 每条的「原文矛盾」小节记录了正文/Methods/图注的数字不一致，**引用其规模数字时务必先看这一节**。

## 同期交付物（非知识库）
- 合读解读：`results/memomics-75ba0499/results/AI_agent_前沿工作解读.md`
- 逐篇结构化摘要：`data/AI摘要_paper2Agent_CASSIA.md`、`data/AI摘要_ChemCrow_ScienceBuddy.md`、`Biomni_结构化摘要.md`
- 全文纯文本：`data/lit_text/*.txt`（9 篇，合计 84.6 万字符）