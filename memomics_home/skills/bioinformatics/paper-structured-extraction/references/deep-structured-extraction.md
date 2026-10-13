# 深度结构化提取：完整模板与技术细节

来源会话记录：多次任务要求"深度结构化提取论文的关键信息，输出中文结构化摘要（每篇独立分节）；禁止编造：所有数字必须来自原文"。
- 会话 1：AI-agent 类论文（Paper2Agent / ScienceBuddy），源文本 `results/<sid>/data/lit_text/*.txt`。
- 会话 2：Paper2Agent（Nature 2026, 10.1038/s41586-026-11044-y）+ CASSIA（Nat Commun 2025, 10.1038/s41467-025-67084-x），同一 `lit_text/*.txt` 目录。本会话首次系统化两件事：**给每个数字标原文行号**、**逐篇列出"我发现的原文自相矛盾"**（见 §F）。

---

## A. 10 节模板逐节要点

### 1. 元信息（表格）
固定字段：标题｜作者（含共一/通讯标注）｜通讯作者+邮箱｜机构（带角标解释）｜期刊或类型+年份（含 Received/Accepted 日期）｜DOI 或 arXiv 号｜代码仓库 URL｜数据可用性（数据集编号/链接）｜许可（如 CC BY-NC-ND 4.0）／网站。
- 作者与机构照抄原文角标；arXiv 号形如 `arXiv:2609.17523v1 [cs.AI] 15 Sep 2026`。
- 原文没给的项目（如完整 GitHub URL、许可）写「原文未报告」。

### 2. 一句话定位（≤40 字）
一句话压缩全篇贡献。用于快速筛选/索引。

### 3. 研究思路
写清：核心设计哲学（作者的世界观转变）、系统/实验架构（组件与分层）、关键策略（如 tutorial-first、agentic exploration）、训练/优化范式、与已有工作的差异（相较哪些先例、多给了什么）。
- 若论文有命名范式（如 "recursive-in-recursive"），原样保留并解释两层含义。
- 差异段要具体点名先例（executable papers / Papers with Code / Binder / Meta-Harness / DGM …），别写空泛的"优于现有工作"。

### 4. 解决什么问题
痛点一句话 + 为什么现有方案不够。原文常用"passive artefacts / 技术壁垒"式表述。

### 5. 工作量与内容
- 团队/机构；构建的产物清单（工具数、模块数、agent 数）；
- 任务/数据规模（样本数、题数、subtopic 数）；
- 训练或演化轮次（cycles、steps、RL updates、epochs）——常藏在 Methods/Appendix；
- 模型清单（任务模型 / 辅助模型 / 编辑器）与硬件；
- LOC/参数量等若未报告，写「原文未报告」。

### 6. 怎么测试
- 评测设计（对照基线、是否接触原文/仓库、打分方式）；
- 专家打分与评分者间一致性（如 96.7%）；
- 统计方法（paired t-test / bootstrap 10,000 重采样 / 95% CI / mean±s.e.m.）；
- 消融变体（逐一列出）；
- 对抗/鲁棒性测试（out-of-scope 置换、注入错误配置数）。

### 7. Benchmark 与数据集（表格）
| 名称/来源 | 规模 | 说明 |
逐行列出每个基准、数据集、案例，含来源（LAB-Bench / Biomni-Eval1 / bioRxiv / 10x / Zenodo / GWAS Catalog）与规模。

### 8. 关键结果数字
按"表 + 分块"组织；主对照表（方法 × 指标）；随后分块列出构建成本、耗时倍数、拒答率、案例统计量。**每个数字后不解释、不美化**。

### 9. 局限（拆两小节）
- **① 作者自述局限与免责边界**：作者明确承认的局限 + 明示的免责（如"human-in-the-loop 仍必要""benchmark 只测忠实执行度而非分析有效性""性能依赖输入 marker 质量"）。
- **② 我发现的原文自相矛盾**：逐条列，每条 `描述A（出处） vs 描述B（出处）`，末尾注"已如实并列，未作统一"。类型学见 §F。区分"作者说的"与"你判断的"。

### 10. 可复用信息
可复用组件（流水线步骤、子 agent 角色、模板/脚本）、开源地址、许可、前瞻主张（如建议期刊设 "agent availability" 栏目）、**对做同类系统的借鉴点**（本节最有用，可直接喂给下一班人）。

---

## B. 模板变体

- **AI-agent / 方法论文**：第 3 节重"系统架构+流水线+agent 角色"；第 6 节重"对照基线+消融+对抗"；第 8 节重"构建成本 + 检出率/拒答率"。
- **实验研究论文**：第 5/6 节重"分组设计+队列+验证实验"；第 8 节重"P 值/log2FC/效应量+独立队列复现"。
- **综述**：第 3 节重"概念框架"；第 6/8 节弱化为"文献检索与归类标准"。

模板节名与顺序保持一致，用户要"每篇独立分节"时**不要**合并成跨篇对比表；可选在全部之后追加一段跨篇对比。

---

## C. 源文本精读技术（PDF→txt dump 场景）

1. **先量体**：`wc -c` / `wc -l` 看体量（本类论文 dump 常见 45–170 KB、1000–4400 行）。
2. **分块读**：`read_file` 带 `offset`/`limit`，每次 400–500 行，逐段推进到文件末尾。**务必读到文末**——Methods、Appendix、References 之后的附录里常有 tolerance（如"3% 浮点容差""Hamming<20"）、子集准确率、数据集 counts、模型版本。
3. **验证关键串**：对拟写入的核心断言用 `search_files(target=content, path=<该 txt>)` 复核。
4. **grep 兜底**：`search_files` 对含特殊字符的串（版本号 `Qwen3.5-4B`、`|` 交替模式）可能返回 0，即使正文里确实存在；遇 0 改用 `read_file` 直读该区域，**不要**据此写"原文未报告"。

---

## D. 交付约定（本类任务）

- 交付物 = 结构化摘要本体：**回复里给出完整 10 节**（本类任务允许长回复）。
- **同时落盘**：写入 `results/<sid>/data/paper_structured_summaries.md`（或用户指定路径）。
- 回复末尾附「交付物/执行说明」：新建文件路径与字节数、哪些项标了「原文未报告」、哪些数字标了「建议核对原图」、以及唯一的待复核项。

---

## E. 常见造假陷阱（自查清单）

| 陷阱 | 正确做法 |
|---|---|
| 图里才有、正文没写的 before/after 数 | 标注「读自 Fig.X，建议核对原图」 |
| 把"约 45 min / US$14"写成"US$15"或"~1h" | 照抄原文 |
| 未给的数据链接/许可凭常识补 | 写「原文未报告」 |
| 多篇合并成一张对比表 | 每篇独立分节 |
| 把论文相关工作叙事当已核实领域史 | 标"原文所述" |
| grep 为 0 就判"没有" | 直读复核 |
| 默认用户给的题名 = 原文题名 | 两个都写、标差异（§F 第 6 类） |
| 数字不带出处行号 | 能标就标「第 X–Y 行」 |

---

## F. 矛盾类型学（"我发现的原文自相矛盾"逐类对照）

同一篇论文内部数字不一致是常态，不是例外。**逐类扫、逐条并列、每条标两处出处**，绝不挑一个或做平均。本会话在 2 篇论文里就抓到 8 处，类型如下（附实例，供下次快速对照）：

| # | 类型 | 本会话实例 | 处理 |
|---|---|---|---|
| 1 | 图注样本量 vs 正文样本量 | CASSIA CS 评测：正文"randomly selected a total of **95** cell types" vs Fig.5b 图注"(**n = 100**)" | 两数并列 + 各自出处 |
| 2 | 图注概括性断言 vs 正文具体数字 | CASSIA 非模式生物：Fig.4d 图注"CASSIA consistently achieves **>85%** accuracy across shark, cat, tiger, and pangolin" vs 正文穿山甲 **41/54（=75.9%）** | 明确指出图注与正文矛盾（76% < 85%） |
| 3 | 图注区间 vs 正文平均值/单值 | CASSIA 癌细胞检出：正文"**72.5%** … vs GPTCelltype **20%**" vs Fig.4b 图注"CASSIA achieves **57–100%** … 其他 **0–40%**" | 区间与均值口径不同，两者都写 |
| 4 | 正文同一节内前后不一致 | Paper2Agent Scanpy：先写"applied it to … **four** publicly available single-cell datasets"，几行后写"applied it to **seven** diverse single-cell datasets"，Methods 拆成"**3** PBMC + **4** additional"（=7） | 三处数字并列，指出正文自相矛盾 |
| 5 | 同一概念三处口径不同 | CASSIA 质量分样本量：正文"more than **500** cell types" / Fig.5a "(**n = 530**)" / Annotation Boost 段"42 (out of **586**)" | 三口径并列，注明原文未阐明关系 |
| 6 | 用户给定标题 vs 原文实际标题 | 任务书《paper2Agent: Automatic generation…》vs 原文"Reimagining research papers as interactive and reliable AI agents"；《CASSIA: A multi-agent framework…》vs 原文"CASSIA: a multi-agent large language model for automated and interpretable cell annotation" | 两个标题都写、标差异 |
| 7 | 页首 DOI vs 参考文献 DOI / 两个 Zenodo 编号 | CASSIA：Code Availability 写 `zenodo.1726168934` vs Reference 34 写 `zenodo.17261689` | 两编号并列（"Article in Press" 版常见） |
| 8 | 正文点名先例的数字跨度与前文不同口径 | CASSIA：主 benchmark"+**12–41%**"（fully correct）/"+**9–20%**"（combined）vs 非模式生物段"+**14–77%**" | 标注各百分比指代的不同子集 |

另注：Paper2Agent 的 **Biomni 在 30 条开放式任务上（72.2%）反超 Claude+Repo（56.7%）**，而 tutorial/novel 上 Biomni 明显落后——正文并列给出未解释，属"作者未解释的交叉"，可归入第 3/8 类提醒用户。

**输出格式**：在每篇的第 9 节开一个「我发现的原文自相矛盾」子块，逐条 `N. 描述（出处A） vs 描述B（出处B）`，末尾可加一句"已如实并列，未作统一"。

---

## G. 行号溯源（本会话新增的硬要求）

源文本为 txt dump 时，交付里给每个数字/关键断言标 `（第 X–Y 行）`：

- **价值**：把"禁止编造"从口头承诺变成可机械验证的事实——用户与自己都能秒级回原文核对。
- **做法**：分块 `read_file` 时记下每段的起止行号；落盘文件与回复正文都带行号；元信息、关键数字、benchmark 表三处尤其要带。
- **收尾**：末尾写明"所有数字均可回到原文（行号已标注）"。行号缺失的少数项（如只能从图目测）另标「读自 Fig.X，建议核对原图」。