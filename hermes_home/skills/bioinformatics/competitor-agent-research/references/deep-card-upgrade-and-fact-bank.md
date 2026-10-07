# 深度竞品卡升级 + 单行全文读法 + 五篇事实底稿

来源会话：2026-10-07「精读 5 篇科研 AI agent 论文全文，薄卡→深度卡，只输出我要的 JSON 字段」
论文编号 n = 34, 35, 36, 41, 45（text_dir = `results/memomics-be17649b/data/text/`）

---

## 1. 深度卡 10 字段 schema（覆盖薄卡字段集）

```json
{
  "<n>": {
    "architecture":     "400–800 字：agent/角色全名单 + 各自 I/O 与工具链专名 + 编排机制 + 阈值/超参数 + 人在回路位置",
    "inputs":           "数据形态（文件/表/结构/目标规格）",
    "outputs":          "交付物形态（结构/指标/报告/动作）",
    "models":           "底层 LLM/模型名+版本；无则「原文未披露」+( ) 内点明真实驱动机制",
    "benchmark":        "逐个列逐字数字；无量化则写「无量化评测」并引作者自陈句",
    "validation":       "验证方式：湿实验/DFT/消融/人评/重复运行/无",
    "key_claim":        "一句话主张",
    "novelty":          "第一性新意（机制级，非措辞级）",
    "limitations":      "「作者自陈：…」＋「我另读出：…」两段",
    "evidence_quote":   "≤200 字符连续逐字原文，必须 Ctrl-F 可命中"
  }
}
```

交付口径：用户要「只输出我要的 JSON 字段」时，正文只给 JSON（顶多加一行「已读/未读」声明）。

---

## 2. 单行全文的安全读法（避开 read_file 的静默截断）

仓库 `data/text/PMC*.txt` 是**单行巨文本**（`awk '{print length($0)}'` 显示第 6 行 39K–73K 字符）。
`read_file` 的 offset/limit 按行切片 → 直接读等于没读。

**可靠配方（本次 5 篇全部一次读全，无需 execute_python 字符切片）**
```bash
cd <text_dir>
wc -c PMC*.txt                       # 先判体量
awk '{print NR": "length($0)}' f.txt # 确认是否单行巨文本
for f in PMC13506882 PMC13140703 PMC13614041 PMC12855967 PMC10805810; do
  fold -s -w 700 $f.txt > /tmp/wrap/$f.w700.txt
done
```
然后逐文件 `read_file(path, limit=55..110, offset=…)` 分页读全。

### 🔴 宽度必须 ≤700：read_file 会静默截断长行
- 行尾出现 `... [truncated]`，**该行剩余部分无声丢失**（不是跳到下一行，是直接没了）。
- 实测：`fold -s -w 3000` → 每行被截；`-w 1400` → **仍被截**（同一位置）；`-w 700` → 正常。
- 后果：用 w3000/w1400 读 5 篇会丢掉每行约 1/3 内容，**卡片事实被污染而完全看不出错**（本次先误用 3000/1400，靠 sed 对比 `wc -c` 才发现）。
- 规则：**见到 `[truncated]` 就当行作废，减小宽度重排重读**。

---

## 3. 五篇事实底稿（含可 Ctrl-F 的 evidence_quote 锚点）

| n | PMCID | 论文 | 一句话定位 | evidence_quote（逐字，可 grep） |
|---|---|---|---|---|
| 34 | PMC13506882 | Agentic AI for trustworthy synthetic microbial genomics (Front Bioinform 2026, 观点文) | 9 角色 agent 的「验证优先」编排层，非新生成模型 | `The core perspective here is not a new generative model, but a role-based agentic validation architecture for synthetic microbial genomic data.` |
| 35 | PMC13140703 | ProteinMCP (Protein Sci 2026) | LLM(Claude Code) + 38 个 MCP 统一编排蛋白设计；自动把仓库转 MCP | `the entire workflow, encompassing the evaluation of multiple complex models, completes in approximately 11 min` |
| 36 | PMC13614041 | MAESTRO (ACS Cent Sci 2026) | 四 agent 迭代推理打破 ORR scaling relation | `the catalysts identified by the framework break the theoretical lower limit of ORR overpotential imposed by the conventional scaling relations` |
| 41 | PMC12855967 | PHIA (Nat Commun 2026) | ReAct + 代码生成 + 网络检索读可穿戴数据 | `PHIA achieves an exact match accuracy of 84%, significantly outperforming the Code Generation baseline (74% accuracy), Numerical Reasoning (22% accuracy)` |
| 45 | PMC10805810 | World Avatar 分布式 SDL (Nat Commun 2024) | 动态知识图谱 + 本体 + 自治 agent 连接两地机器人 | `we think of an occurrence of physical experimentation as a sequence of actions that dynamically generates information about a reaction experiment as it progresses in time` |

### 关键逐字数字（写入 benchmark 字段时照抄）
- **n=34**：无量化评测；作者自陈 *"clarifies the proposed workflow logic rather than reporting empirical performance"*。9 角色 = objective specification / generation / biological plausibility / taxonomic coherence / functional annotation / contamination & memorisation / benchmarking / reproducibility & provenance / governance；动作四选一 `pass / revise / reject / escalate`；溯源 `JSON-LD via RO-Crate` 或 `W3C PROV`；工具 CheckM2 · Bakta · MOB suite · geNomad · VirSorter2 · GTDB-Tk；治理三级释放（开放/受控/降级-扣留）；模型「人类监督的自主」。
- **n=35**：适应度建模 **11 min**（人工 1–3 天），5 折 CV 最优 EV+OneHot(Ridge) **Spearman ρ=0.57**，ESM2-650M+SVR 亦强；binder(PD-L1) 6 designs，最优 **pLDDT 0.94 / ipTM 0.80 / dG −42.0 / ipAE 0.23**；nanobody(BoltzGen) 50 designs → **2 通过(0.99) vs 48 失败(0.48)**，Design_06 **pTM 0.731 / ipTM 0.497 / 4 H-bonds**；ipTM–pAE 相关 **−0.95**；MCP 转换「near 100%」；对 BioinfoMCP/Paper2Agent/PRIME/Biomni 六项全 ★★★。四层架构 = UI / Orchestration(Claude Code + Skill Parser·Context Manager·Tool Invoker) / MCP Server Layer / Computation；通信 Stdio JSON-RPC，注册于 `~/.claude.json`，包装用 FastMCP；`MCPCreator` 八步流水线。
- **n=36**：火山图理论下限 **0.36 V**；代表催化剂 **0.31 V**；4 策略 × 10 runs × 100 步；random/historyless 打破 0.36 V **<1 次/run**，有 in-context learning 者 **100 步中平均 >3 次**；DFT 复算 11 个 → **6 个确认 <0.36 V，其中 5 个带 H-bond 表面氧**；真阳性 H Bader **0.605 e** vs 假阳性 **0.577 e**；BO 基线 **≈0.408 V**（6 loops）；UMA(OOD) MAE **8.83 meV/atom · 47.73 meV/Å · 结合能 0.346 eV**，与 DFT **Spearman ρ=0.9698**；默认 LLM **GPT-4.1 mini**（另测 GPT-5 mini、Gemini-3.1-flash-lite）；DFT 设置 VASP 5.4.4 / PAW / GGA-RPBE / cutoff 350 eV / k 点 3×3×1；四节点四 agent（design/calculation/reflection/summary ← Design/Reflect/Summary/Exploration report）；五类可改几何组件（中心金属/一壳/二壳/轴配体/功能团）。
- **n=41**：客观精确匹配 **PHIA 84% vs CodeGen 74% / NumericalReasoning 22% / custom CoT GPT-4 53.6% / PH-LLM 0%**；超越两个常用基线 **282% 与 14%**；开放式 **83% 评 Fair 或更好**、获 Excellent 概率**两倍**；总体推理 Likert **68 vs 52**、领域知识 **63 vs 38**；错误率 **0.192 vs 0.395**；恢复率 **11.4% vs 0%**；危害 <0.1%、>99% 无害；规模 650 小时人评 / >6000 响应人评 / 16000 自动 / 代码评 595 响应·50h·7 名数据科学家；基座 **Gemini 1.0 Ultra**；few-shot = sentence-T5 嵌入 + K-means 20 簇取质心；合成数据由 **30,000 真实用户** 经 **CPAR** 生成 **56 用户（随机取 4）**；ReAct 三阶段 Thought/Act/Observe，工具仅 Python(Pandas) 沙箱 + Google Search。
- **n=45**：剑桥+新加坡两台机器人，羟醛缩合（苯甲醛+丙酮，NaOH → 苯亚甲基丙酮）；设计变量 4（丙酮/NaOH 摩尔当量、停留时间、温度），目标 2（成本+产率）；**65 个数据点**，**最高产率 93%**，**3 天**出 Pareto front；环境因子 **26.17**、时空产率 **258.175 g L⁻¹ h⁻¹**；新加坡 HPLC 运行约 10 h 后故障 → **>3500% 产率**异常点被 agent 剔除并邮件通知；两实验室 2 个控制条件验一致性；本体栈 OntoCAPE / OntoReaction / OntoDoE / OntoLab / OntoVapourtec / OntoHPLC / OntoSpecies / OntoAgent（基于 SAREF）；agent = ROG / ROGI / DoE / Schedule / Post-Processing；TSEMO 多目标优化；三层架构（真实世界 / 动态知识图谱 / 自治 agent）；**非 LLM 系统**。

---

## 4. 本次教训（已回写 SKILL.md C9）
1. 深度卡 ≠ 拉长句子，而是**专名 + 数字**的密度；`architecture` 400–800 字，把工具名/类名/阈值写全。
2. C6 的「≤3 句压缩」只适用于 N≥8 的一次性大 JSON；**N 小且点名深度卡时要反过来扩写**。
3. `models` 缺 LLM 时写「原文未披露」，并点明真实驱动机制（老一代 SDL 是 TSEMO + 本体，不是 LLM）。
4. `benchmark` 无量化时写「无量化评测」+ 引作者自陈句，绝不估。
5. 用户说「只输出我要的 JSON 字段」→ 正文只给 JSON，不加总结小节。
6. 单行全文用 `fold -s -w 700` 重排后 read_file 分页读；**`[truncated]` 是静默截断警报**。