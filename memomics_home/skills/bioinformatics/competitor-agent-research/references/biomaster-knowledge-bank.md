# BioMaster (Bioinformatics 2025) — 竞品知识库

> 第三篇被精读的科研 Agent 论文（序列：Biomni → Paper2Agent → **BioMaster**）。
> 它代表**第三种范式**：既不是"建资源"（Biomni）也不是"把论文变 agent"（Paper2Agent），
> 而是**给长多步流程加装"多角色 + 双重质检"的容错调度器**。三者互补，见 §6。

## 1. 身份

| 项 | 值 |
|---|---|
| 标题 | BioMaster: Multi-agent System for Automated Bioinformatics Analysis Workflow |
| 作者 | Houcheng Su, Weicai Long, **Yanlin Zhang\***（通讯，yanlinzhang@hkust-gz.edu.cn） |
| 单位 | 香港科技大学（广州）Data Science and Analytics Thrust |
| 载体 | **Bioinformatics (Oxford) 2025**；本篇 PDF 为 **bioRxiv 预印本 2025-01-26**，DOI `10.1101/2025.01.23.634608` |
| 代码 | https://github.com/ai4nucleome/BioMaster |
| 全文落盘 | `results/<sid>/data/BioMaster_fulltext.txt`（44,903 字符 / 9 页） |

⚠️ 本篇 PDF 是**预印本排版**（页眉含 `Advance Access Publication Date: Day Month Year`、`doi: XXX`），非最终版，数字可能变动。

## 2. 一句话定位

**不做工具箱、不做论文翻译器，做"长流程的容错调度器"** —— 四个各司其职的 agent 串成循环，
核心卖点是 **①针对不同 agent 的方言化 RAG 知识注入 ②每步执行完的强制产出校验**，
目的是**阻止错误跨步传播（error propagation）**。

## 3. 架构（4 Agent + 2 RAG + 1 Memory）

```
用户目标+输入文件
  → Plan Agent   : embedding(text-embedding-3-large) → 余弦检索 Plan RAG 取 **top-2** 知识条目
                   → 拆成"不可再分"步骤 → 输出 **JSON plan**（description / input filenames+paths /
                     output filenames / tools）
  → Task Agent   : 查 Execute RAG（参数说明 / 用法示例）→ 生成可执行脚本（含安装命令）→ 执行
  → Debug Agent  : 判定成功与否；失败则读报错 + Execute RAG 排错知识 → 改写脚本重跑（迭代）
                   memory 摘要压缩历史（**灵感来自 mem0**，省 token）
  → Check Agent  : **产出校验（本文核心）** —— 文件存在? 非空? 命名/格式合 plan?
                   ✗ → 打回 Debug Agent 或回改 plan（防 false completion 与 cascading failure）
  → 下一步 …… 循环至全部完成
```

- **两个 RAG 分工**：`Plan RAG`（流程级：标准流程 + 工具文档 + 补充材料；**用户可加 PDF → 自动转文本 + LLM 摘要入库**）；
  `Execute RAG`（工具级：参数、示例、排错策略）。**两者都只返回 top-2 条目**（精度 vs 效率的取舍）。
- **记忆结构**：每个 agent 有**本地知识 + 本地记忆（互不共享）**，但共享一个**全局知识仓库**
  （流程上下文 / 输入文件 / 预期产出）。
- **实现**：LangChain；**GPT-4o（`gpt-4o-2024-08-06`）**；Ubuntu 22.04 + Conda + Python 3.12 + R 4.4.1。
  本机测试机 AMD EPYC 7K62 48-core / 8GB RAM，云机 i9-13900K / 94GB；推荐 CPU ≥16GB RAM（不依赖 GPU）。
- ⚠️ **论文自身口径不一致**：Environment 节写 "OpenAI's **GPT-4**"，Results 节写 "**GPT-4o**（gpt-4o-2024-08-06）"。
  引用时按 Results 的带版本号口径，并提示该矛盾（用户看重这类核对）。

## 4. 结果

**测评设置**：对比 **AutoBA** 与 **ChatGPT**（人工调试）；**所有方法同一 LLM（gpt-4o-2024-08-06）**；
每步最多 5 次 debug，超出即记失败；共 **20 个任务**（ChIP-seq / RNA-seq / 单细胞 / 空间转录组 / 群体遗传 / Hi-C）。

**① ~5 步主流流程：三家打平**，失败主因均为 **Conda 依赖冲突**（论文自认"对人类专家也难"）。

**② 复杂 / 小众流程：差距拉开（Table 1 关键行）**

| 任务 | AutoBA | ChatGPT | BioMaster |
|---|:---:|:---:|:---:|
| 群体遗传 · SmartPCA | ✗ | ✗ | **✓** |
| 群体遗传 · Treemix | ✗ | ✗ | **✓** |
| 群体遗传 · ROH | ✗ | ✓ | ✓ |
| Hi-C · Pair parsing & cleaning | ✗ | ✗ | **✓** |
| Hi-C · **全预处理流程** | ✗ | ✗ | **✓** |
| RNA editing | ✗ | ✓ | ✓ |
| 单细胞 · 基于 count matrix 找 marker | ✓ | ✗ | **✗** |
| ChIP-seq · Functional Enrichment | ✗ | ✗ | **✗** |

**③ Hi-C（≥10 步）的机理对比（Fig.5，最有说服力的一段）**
- 给官方 4DN 流程也一样失败 → AutoBA/ChatGPT **规划不完整**，文件合并不了；
- 于是**给所有 agent 一份专家改好的正确 plan**（排除"规划"这个变量）再看：
  ChatGPT 栽在**文件路径处理**，AutoBA **不做产出校验 → 级联错误**；
  BioMaster 靠 Check Agent **逐点拦住**。

**④ 消融（Fig.6，仅定性、正文无数字）**
- 去 **Plan RAG** → plan 质量塌（流程不完整 / 次优）；
- 去 **Check Agent** → **短任务几乎无影响，长流程严重受损**（小偏差累积）；
- 弱化 **Tool RAG** 增强 → 简单任务无碍，**smartPCA / admixtools F4 明显变差**。

## 5. 本家审查：这篇的硬伤

1. **只有 ✓/✗，无量化成功率、无统计检验**，n=20 —— 证据强度明显弱于 Biomni（+402%）与 Paper2Agent（98.7±1.3%，双专家打分）；
2. **单一 LLM（GPT-4o）**，无第二模型验证泛化；
3. **消融是图形定性（Fig.6），正文无数字**；
4. **未对比新近 agent**（CellAgent 只在背景里提）；
5. **失败归因停在"Conda 依赖冲突"**，未给机制性解法，仅作失败记录；
6. **BioMaster 自己也失败 2 项**（单细胞 count-matrix marker、ChIP-seq 功能富集；后者三家全败且未深挖）；
7. **预印本排版**，非最终版。

## 6. 🔴 三范式综合（本序列最有价值的产出，可直接复用）

| 维度 | **Biomni** | **Paper2Agent** | **BioMaster** |
|---|---|---|---|
| 沉淀单位 | 314 通用资源（2500 篇论文挖出） | 每篇论文一个 **MCP**（tools+resources+prompts） | **无沉淀资产**，只有 2 个 RAG 知识库 |
| 面向 | 全领域**广度** | 单篇论文**深度** | 长多步流程的**鲁棒性** |
| 核心机制 | CodeAct + 检索式工具选择 | 六步管线 + 论文回测 | **多角色分工 + Check Agent 逐步校验** |
| 质量保证 | 人工实现 + 带测试用例 | 论文自己的数据当 ground truth（3% 容差 + 图感知哈希） | **产出存在性 / 非空 / 命名 / 格式校验**（工程级） |
| 失败模式 | 广而不深，具体方法无专门验证 | 深度依赖代码质量（100 篇仅 74 篇可 agent 化） | 无量化证据，依赖冲突即崩 |

> **一句话**：Biomni 解决「**会不会**」（能力覆盖）、Paper2Agent 解决「**准不准**」（忠实复现）、
> BioMaster 解决「**跑不跑得完**」（长流程不崩）——**是三个正交的失败模式，互补而非替代**。

## 7. 可复用的实验设计模板：**「喂正确 plan」解耦能力维度**

BioMaster 的 Fig.5(b) 给所有 agent 一份**专家改好的正确 plan**，把"规划能力"从"执行/校验能力"里剥离，
**Check Agent 的增益因此才是独立可归因的**。
⇒ 我们做 agent 消融 / 对比时同样可用：**先固定规划环节，只比执行与校验**（或反之），避免把两个变量的效果混在一起。

## 8. 对本家的启示：**校验下沉到每一步**

BioMaster 把"校验"做成**独立 agent + 每步强制执行**；MemOmics 的 `rail_review` / 产出物存在性验证
主要在**阶段末**。长流程的校验应**下沉到每步**（与铁律「自动沉淀门禁」「产出物存在性验证」同源，但粒度更细）。

## 9. 事实核验锚点（下次引用可直接指到的原文位置）

| 结论 | 原文位置 / 逐字线索 |
|---|---|
| Check Agent 是核心 | Methods *Check Agent* 节：检查文件存在 / 非空 / 命名·格式 vs plan；防 "false completions and cascading failures" |
| 检索只取 top-2 | Methods *Plan Agent* 节："the top two most relevant entries" |
| memory 仿 mem0 | Discussion："drawing inspiration from the **mem0** memory model to enhance memory control" |
| GPT-4o 口径矛盾 | Environment "OpenAI's **GPT-4**" vs Results "**GPT-4o** model (version 'gpt-4o-2024-08-06')" |
| 解耦实验 | Results *Hi-C* 段 "To make a fair comparison, we provided all agents with **expert-edited plans**" |

## 10. 抓全文的工具口径（本轮实测）

- `import fitz` 提取 → 44,903 字符 / 9 页，落盘 `data/BioMaster_fulltext.txt`；
  该 API 已 deprecation（提示改用 `import pymupdf`），功能相同。
- `execute_python` 的 stdout 有 ~10000 字符上限 ⇒ **长全文分 4 段** `print(t[a:b])` 读完（不要指望一次打印全文）。
- 本文**无 PMC 全文 XML 通道需求**（PDF 直接可读）；若遇出版社反爬，按
  `references/fulltext-acquisition-and-harvest.md` 的阶梯走。