# 模式 C 配方：批量论文全文精读 → 结构化竞品卡（JSON）

来源：2026-10-02 会话「精读 11 篇科研 AI agent 论文全文，产出中文竞品卡」。
任务输入：`results/<sid>/data/cards_source.json`（31 条记录，含 n/title/venue/year/doi/pmcid/**text_file**）
+ `results/<sid>/data/text/PMC*.txt` 全文。

## 竞品卡 JSON schema（snake_case，逐篇一份）

```json
{
  "n": 1,
  "name": "系统专名（无专名时写「无专名 + 主题简称」）",
  "title": "原文标题",
  "venue": "期刊",
  "year": 2026,
  "doi": "10.xxxx/yyyy",
  "pmcid": "PMCxxxxxxx",
  "team": "机构/团队 + 通讯作者",
  "category": "六选一：假设生成 | 端到端自动化 | 数据分析agent | 领域专用agent | 基础设施与框架 | 综述与观点",
  "goal": "系统要做成什么（一句话）",
  "architecture": "agent 分工、编排框架、记忆/反思/错误恢复机制、检索结构",
  "inputs": "输入形态",
  "outputs": "输出交付物",
  "models": "底层 LLM 清单（含默认模型、judge、embedding 等）",
  "benchmark": "逐字可引用的成绩；无则写明「正文未给可引用逐字成绩」",
  "validation": "消融/人类评审/湿实验/多队列等验证证据",
  "key_claim": "原文核心主张",
  "novelty": "相对前作的首次性（first to ...）",
  "limitations": "作者自陈 + 你从方法推断的，分开写",
  "evidence_quote": "≤220 字符、连续逐字、可 grep 的原文句",
  "memomics_implication": "对 MemOmics 的可操作启示"
}
```

## 全文精读配方（实测）

```python
base = "E:/MemOmics-Agent/results/<sid>/"
def load(n):
    return open(base + FILES[n], encoding="utf-8", errors="ignore").read()
import re
t = load(1)
for kw in ["Abstract","Introduction","Results","Discussion","Methods","Limitation","Conclusion"]:
    print(kw, [m.start() for m in re.finditer(kw, t)][:10])  # 章节头偏移
print(t[14000:34000])   # 按字符区间读，一次 15–25k
```

**坑**：PMC txt 常只有 ~5 个换行（整篇挤在几行里）→ `read_file` 的 offset/limit 完全失效，
必须 `print(t[a:b])`。清单里的 `abstract/methods/results` 字段是 ~1600 字符预览，**落卡一律回 text_file 原文**。

**预算**：11 篇全读 ≈ 45+ 次 execute_python，会撞迭代上限。一个调用里读 2 篇；命中上限时交已读卡 + 标注未读项。

## 已读论文实测要点（可复用的事实底稿）

| n | 系统 | 期刊/年 | 关键 benchmark（逐字） | 底层模型 |
|---|------|---------|------------------------|----------|
| 1 | Robin | Nature 2026 | Finch 在 BixBench 170 题 22.8±1.7% vs 无 harness Claude 3.7 Sonnet 1.6±1.2%；统计子集 47.9±1.5%，生信子集 15.3±2.0%；rubric 依从 RNA-seq 86%、flow 100% | o4-mini(假设) + Claude 3.7 Sonnet(judge) + Gemini 2.5 Pro(造 judge prompt)；Crow/Falcon=PaperQA2 |
| 2 | 无专名分层多 agent | Adv Sci 2026 | 无量化 benchmark；~17 h/研究、32.5M tokens、~$114/项目；消融 d-RAG 后最新文献年份 2019 vs 2025、幻觉引用 6 vs 0 | Claude 4 Sonnet / o3-mini / o1 / Grok-3 / Pixtral Large / Gemini 2.5 Pro |
| 4 | Agentomics | Bioinformatics 2026 | 超越所有 agent：蛋白工程 75.92、药物发现 34.29、调控基因组 60.15 百分位；20 数据集中 11/20 超人类 SoTA；60 runs 成功率 100%；8h 花费 $9.4±5.0 | GPT-5.1-Codex-Max |
| 5 | BioMaster | Patterns 2026 | 49 任务/102 工具完成 47/49(95.9%) vs SingleAgent 24(49.0%)、AutoBA 13(26.5%)、ChatGPT 12(24.5%)；Hi-C SCC>0.99 | OpenAI o1-2024-12-17；另测 GPT-oss-120B |
| 6 | ChemGraph | Commun Chem 2026 | 单 agent 13 任务精度热图；多 agent 后 GPT-4o 达 100%，小模型反超单 agent GPT-4o | GPT-4o/4o-mini、Claude-3.5-haiku、Qwen-2.5-14B |
| 7 | CASSIA | Nat Commun 2025 | 970 细胞类型：fully correct +12–41%，combined correct +9–20%（vs 次优）；默认模型 GPT-4o（~$0.02/注释） | GPT-4o(默认)/Claude 3.5 Sonnet/LLaMA-3.2-90B |
| 8 | SPARK | Nat Med 2026 | 18 队列/>5,400 患者；1,115 去相关参数；BRCA 亚型 AUROC 0.898、ER 0.863、HPV/p16 0.828、MSI 达 0.933、PD-L1(LUAD)强/LUSC 最高 0.719 | o1(创意生成) + o3-mini(非推理) + Claude Sonnet 3.5(编码) |
| 9 | DeepRare | Nature 2026 | 6,401 病例/2,919 病：HPO Recall@1 57.18%、Recall@3 65.25%，超次优 +23.79%/+18.65%；多模态 Recall@1 69.1% vs Exomiser 55.9%；专家对推理链一致率 95.4%；Recall@1 64.4% vs 医师 54.6% | DeepSeek-V3(默认 host)；消融 Claude-3.5/R1/GPT-4o/Gemini-2.0-flash |
| 10 | GeneGenie | Brief Bioinform 2026 | **仅读到摘要**：GeneTuring 16 模块/1600 QA；Gemini 2.5 Pro 答对 1158 题（72.375%） | 未读全文 |
| 11 | MCP-native 层级 AI scientist | Front AI 2026 | **本次未读取全文** | — |
| 12 | Streamline agentic bioinformatics | Brief Bioinform 2025 | **本次未读取全文** | — |

> n=11、n=12 未完成全文精读，卡内不得编造架构/数字；如需补齐，重新执行本模式并优先读这两篇。

## 第二批实测（2026-10-02 晚，n = 14,15,16,17,19,20,21,22,23,24，10 篇全读完）

| n | 系统/主题 | 期刊·年 | category | 逐字 benchmark / 关键数字 | 底层模型 |
|---|-----------|---------|----------|---------------------------|----------|
| 14 | Digital materials ecosystem | Chem Sci 2026 | 综述与观点 | 无量化（Perspective）；转述 DigHyd：ML 回归 R²=0.87，CaMgFe2 2.64 wt%、Mg2Fe 4.13 wt% | 未指定（讨论 DIVE/Eunomia/DigHyd） |
| 15 | 双车道 agentic 化学动力学 | Chem Sci 2026 | 综述与观点 | 无量化；倡议建 Mechanism Development Benchmark（offline replay + shadow mode） | 未披露（概念性） |
| 16 | PANGAEA GPT | Front AI 2025 | 基础设施与框架 | 无量化（作者自陈 proof-of-concept，「lacks rigorous quantitative empirical validation」） | 未披露（LangChain/LangGraph） |
| 17 | PGxAI-Recommender | NPJ Digit Med 2026 | 领域专用agent | 抽取 91.9%（22 篇/35 字段/3 标注者/2310 判断）、多数共识一致 94.7%；推荐专家均分 9.0 vs 基线 6.2–7.8；配对 CPIC 胜率 0.83；Friedman χ²=46.71 p<0.001 | GPT-4.1（temp=1e-5）；基线 GPT-5/Claude Opus 4/Grok 4/GPT-o3 |
| 19 | LLM+agent in chemistry 综述 | Chem Sci 2025 | 综述与观点 | 无量化；转述 CACTUS +60%、ChatMOF ~90%/~70%、Eunomia CoVe +20% precision | 未指定（讨论 GPT-4/Gemma/Mistral） |
| 20 | LLM agents in bioinfo/biomed | Brief Bioinform 2025 | 综述与观点 | 无量化；转述 RL-GenRisk >40%、RDguru top-5 63.87%、BioDiscoveryAgent +46% | 未指定（讨论 GPT-4/LLaMa/Gemini/PaLM） |
| 21 | LLM agents biological intelligence | Brief Bioinform 2026 | 综述与观点 | 无单一量化（作者称同域同数据集比较「currently infeasible」）；综合 >60 系统 | 未指定（表中提 GPT-4/InternLM2/Qwen/Mistral 等） |
| 22 | BioRAGent | Brief Bioinform 2025 | 数据分析agent | 自建 14 任务（11 单跳+3 多跳）：overall 0.92 vs GPT-4o 0.35/ChatGPT-4o 0.44/GeneGPT 0.46；多跳 0.87 vs 仅工具 0.51；用户 same-or-better 80%/76% | BioRAGent(GPT-4o)；judge=GPT-4o mini；消融 GPT-3.5/Llama-3.3-70B |
| 23 | 三支柱范式综述 | Brief Bioinform 2026 | 综述与观点 | 无原始评测；转述基础模型跨平台迁移性能显著下降、无 sequential testing 累积 type-I error | 未指定（讨论 scGPT/Nicheformer/EpiAgent/Biomni/ClinicalAgent） |
| 24 | iDesignGPT | Nat Commun 2026 | 领域专用agent | 六公共挑战：TRIZ 中位 L3、专利相似度 0.40 vs GPT-4o 0.49/Deepseek-r1 0.51、耦合率 28%（最低）；GoAERO 进 22 份获奖前 25%；coverage +11.4%、diversity +18.5%、novelty 0.50→0.62；Delphi 6 专家 | GPT-4o-2024-08-06 + GPT-4o-mini-2024-07-18（fastGPT） |

**规律**：综述/观点类（14/15/19/20/21/23）一律「无量化自测」，其数字只能写成「转述被引系统的结果」并标清；
只有实做系统（17/22/24）才有自建 benchmark，且**自建 benchmark 的 overall 数字常与引言/消融口径不一致**
（本次 BioRAGent 0.92 是 14 任务 overall、0.87 是多跳 overall）——落卡时按任务口径分开写，别混。

## evidence_quote 机械校验（落卡前必跑，见 `scripts/verify_evidence_quotes.py`）

```python
import re
def norm(s): return re.sub(r"\s+", " ", s or "").strip()
def chk(f, q):                      # f = data/text/PMC*.txt
    t = norm(open(base + f, encoding="utf-8", errors="ignore").read())
    print(len(norm(q)), f, "FOUND" if norm(q) in t else "MISSING")
```
本次 10 条 quote 全部 FOUND 后才交卡；≤220 字符内只保留**一段连续逐字**原文，跨句省略必 MISS。