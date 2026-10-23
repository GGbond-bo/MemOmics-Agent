# 实战范例：两篇 AI/agent 论文的 10 节输出骨架

> 来源会话：memomics-75ba0499（原文文本在 `results/memomics-75ba0499/data/lit_text/`）。
> 交付文件：`results/memomics-75ba0499/data/AI摘要_ChemCrow_ScienceBuddy.md`（两篇独立 10 节 + 对比速览表）。
> 下面只保留**可复用骨架与关键数字口径**，用于下次套模板。

---

## 范例 A：ChemCrow（工具增强化学 agent，2024）

- 文件：`10.1038_s42256-024-00832-8.txt`（1403 行）
- 元信息：Nature Machine Intelligence, Vol 6, May 2024, 525–535；DOI 10.1038/s42256-024-00832-8；Received 2023-09-13 / Accepted 2024-03-27 / Online 2024-05-08；共同一作 Andres M. Bran & Sam Cox；通讯 Andrew D. White(andrew@futurehouse.org) & Philippe Schwaller(philippe.schwaller@epfl.ch)；机构 EPFL LIAC / NCCR Catalysis / Univ. Rochester / FutureHouse / IBM Research Europe；代码 chemcrow-public(v0.3.24) & chemcrow-runs。
- 一句话定位：把 **18 个**专家工具接入 **GPT-4**（ReAct 循环 Thought/Action/Action Input/Observation）的化学 agent。
- 关键数字（全部可溯源）：
  - 工具 **18** 个（开源版 **12** 个）；use cases **14**（Appendix G）
  - GPT-4，**temperature = 0.1**
  - 真实合成 **4** 个（DEET + Schreiner's/Ricci's/Takemoto's 三个硫脲有机催化剂），全部成功
  - 发色团：目标 **369 nm**，RF 模型 **RMSE = 37 nm**，实测 **336 nm**
  - 专家评估者 **n=4**；人工评测样本 **n=56**；EvaluatorGPT **n=14**
  - 安全阈值：ControlledChemicalCheck 相似度 **> 0.35** 告警；ModifyMol 用 **50** 个稳健反应
  - Fig.4 任务难度分值：Paracetamol 1.54 / Aspirin 1.59 / DEET 1.87 / Ricci's OC 3.17 / Takemoto's OC 3.31 / Safinamide 3.61 / Atorvastatin 4.79
- 核心结论：专家评估偏好 ChemCrow（化学事实性/推理/完整度更优，复杂任务尤甚），**但 EvaluatorGPT 偏好 GPT-4**（因其回答更流畅完整）→ 重要警示：LLM-as-judge 不可替代专家评估。
- **发现的矛盾/口径不一致**：
  1. 正文「18 tools」 vs Methods 逐条枚举 **19** 个工具；Fig.1b 分 **5** 类 vs Methods 文字只提 **3** 类。
  2. Data availability 仅指向 GitHub，称"source data provided"，无独立公开数据集链接。

## 范例 B：ScienceBuddy（递归套递归自改进科研 agent，2026）

- 文件：`2609.17523v1.txt`（1831 行）
- **标题（必须从原文首页确认，不许猜）**：*ScienceBuddy: Recursive-in-Recursive Self-Improvement for Interactive Scientific Agents*
- 元信息：arXiv:2609.17523v1 [cs.AI]，**15 Sep 2026**；共同一作 Shuhan Xue/Jianyuan Zhong/Ziyuan Nan；通讯 Zhenfei Yin/Yingcheng Wu/Ling Yang（@phai-labs.com）；机构 PhAI Labs / 复旦中山医院 / Stanford / Oxford / Princeton 等；代码 Gen-Verse/ScienceBuddy；网站 Science-Buddy-Product。
- 一句话定位：交互式科研工作台 + **recursive-in-recursive**（内层进化 harness 固定模型 / 外层 GRPO 固定 harness）。
- 关键数字：
  - 工具 **224** / 模块 **22**；任务集 **895**（LitQA2 96 + DbQA 511 + ProtocolQA 108 + GWAS 180），**16** 子主题
  - 模型：任务 **Qwen3.5-4B**，辅助 **Qwen3.8-27B**，harness 编辑器 **GPT-6 Astra**
  - §4.2：测试准确率 **42.2%→73.3%**；harness 验证 38.9→44.4 / 34.4→46.7 / 61.1→70.0（三轮）；33.3% 错→对、2.2% 对→错
  - §4.3：validation **31.1%→51.1%（+20.0 pp）**；24 适应批次，最佳批 75.0%；选中 harness = 4 instruction + 9 scoped skills；288 段对话 / 每批 12 段
  - §4.4：**约 2 小时** RL；pass@4 覆盖 **48.3%→67.8%（+19.5 pp）**
- **发现的矛盾**：
  1. **硬矛盾**：§4.2 标题 "Two-Cycle" vs 正文与 Fig.8 图注 "three cycles"（k=0,1,2）。
  2. 正文称第 2 轮起点 34.4%，但 Fig.8(a) 数值序列 38.9/44.4/46.7/61.1/70.0 **无 34.4%**。
  3. 口径陷阱：§4.4 pass@4（固定 H0 纯模型）≠ §4.2 single-attempt（全过程），不可并读。
- 作者自述局限：reflector 固定（改进机制本身没变强）；未隔离单个 skill/反馈来源贡献；反馈是"bounded, reference-assisted"模拟用户非专家；研究者反馈≠科学 ground truth；当前专精生物医学。

## 对比速览表（收尾可选）
两篇以上时，末尾加一张 `| 维度 | 论文A | 论文B |` 速览（系统类型/规模/是否训练/模型/评测/关键结果/自述局限）——用户看到会认这是完整交付。

## 复用提示
- 「工作量与内容」「关键数字」两节是用户最看重的：**数字要密、要可溯源、要标注图号**。
- 「局限」节务必把「作者自述」与「我审计出的矛盾」分开两栏——这是本类任务区别于普通摘要的关键。