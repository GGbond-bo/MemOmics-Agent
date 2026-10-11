---
name: chinese-research-latex
description: "中国科研文档 LaTeX 模板集（ChineseResearchLaTeX）落地与写作编排：国自然标书 / 毕业论文 / 学术简历 / SCI 论文 四产品线的模板选型 → 公共包装配 → XeLaTeX 编译与 Word 导出 → 编排仓库内置 27 个写作技能（nsfc-* / paper-* / research-*）。触发词：写基金、国自然、标书、基金申请、写毕业论文、学位论文模板、学术简历、SCI论文、投稿信、期刊选择、LaTeX 模板。"
when_to_use: "[chinese-research-latex] 用户提出中文科研文档写作/排版需求时触发：① 写基金/国自然/省基金标书（立项依据、研究内容、摘要、预算、评审模拟）② 写毕业论文/学位论文/博士后报告（按学校模板）③ 写学术简历（中英文 CV）④ 写 SCI 论文/投稿信/选期刊/查引用一致性 ⑤ 把旧 Word/PDF/tex 材料迁进 LaTeX 模板 ⑥ 直接说 LaTeX 模板、XeLaTeX 编译、导出 Word。与 MemOmics 既有写作技能的分工见正文第五节（nature-writing 管英文稿件论证、academic-thesis-docx 管校内规范 DOCX、本 skill 管 LaTeX 模板落地与中文文档编译链）。"
trigger_keywords: ["写基金", "国自然", "标书", "基金申请", "写毕业论文", "学位论文模板", "毕业论文模板", "学术简历", "SCI论文", "投稿信", "期刊选择", "LaTeX 模板", "NSFC", "ChineseResearchLaTeX", "paper-sci", "XeLaTeX 编译"]
trigger_level: RED 必触发
---

# 中国科研文档 LaTeX 模板集（ChineseResearchLaTeX）落地与写作编排

**上游项目**：`huangwb8/ChineseResearchLaTeX`（MIT，v4.1.1）—— 国自然标书 / SCI 论文 / 毕业论文 / 学术简历的 LaTeX 模板 + 公共包 + 27 个 AI 写作 Skill。
**本机安装位置**：`E:/MemOmics-Agent/third_party/CRL`（393 MB，commit `b8b4142` = v4.1.1，2026-10-04；经 **Gitee 镜像** 克隆，GitHub git 协议在本机不可用）。
**本 skill 的职责**：把用户的写作意图 → 落到**正确的模板目录** → 用**官方构建入口**产出 PDF/DOCX，并编排上游技能。**不重写上游文档**。

---

## 一、触发边界

### ✅ 该用
| 用户说 | 走哪条产品线 |
|---|---|
| 写基金 / 国自然 / 青年基金 / 面上 / 地区基金 / 省基金标书 | `projects/NSFC_*`、`projects/GDNSF_*`、`projects/GXNSF_*` |
| 写毕业论文 / 学位论文 / 博士后报告（点名学校） | `projects/thesis-<校>-<类型>` |
| 写学术简历 / CV / 中英文简历 | `projects/cv-01` |
| 写 SCI 论文 / 投稿信 / 选期刊 / 引用一致性 | `projects/paper-sci-01`、`projects/paper-coverletter-01` |
| 把旧标书/旧论文/Word/PDF 迁进模板 | `transfer-old-latex-to-new`（上游 skill） |
| 编译 PDF / 导出 Word / 统计字数 | 官方构建入口（见第三节） |

### ⛔ 不该用（路由到别处，别抢）
- 纯英文稿件论证、章节起草、投稿材料 → `nature-writing` / `nature-polishing`
- 高校学位论文**规范合规 + DOCX 出稿**（读学校规范附件）→ `academic-thesis-docx` / `cn-degree-thesis-writing`
- 审稿人视角预审、修回信 → `nature-reviewer` / `pre-submission-reviewer` / `nature-response`
- 中文去 AI 味、查重 → `human-skill`（本 skill 只调用上游 `nsfc-humanization`）
- 文献检索/综述本体 → `literature-review` / `deep-research` / `nature-literature-pipeline`

---

## 二、安装状态与再安装（幂等）

```bash
# 健康检查（reporoot/python/XeLaTeX/包状态）
bash memomics_home/skills/bioinformatics/chinese-research-latex/scripts/crl.sh check

# 重新安装（GitHub 不可用 → Gitee 镜像；不删任何已有文件）
bash memomics_home/skills/bioinformatics/chinese-research-latex/scripts/crl.sh install
```

- 克隆源：`https://gitee.com/huangwb8/ChineseResearchLaTeX.git`（GitHub 直连报 `schannel: failed to receive handshake`，加 `GIT_SSL_BACKEND=openssl` 也无效）
- 安装公共包（**需已装 TeX 发行版**）：`python scripts/install.py install --mirror gitee [--packages bensz-nsfc,bensz-paper,bensz-thesis,bensz-cv]`

---

## 三、产品线 → 模板 → 官方构建命令（权威口径：`docs/manual-setup-guide.md`）

| 产品线 | 模板目录 | 构建命令（包内工具，**不要直接裸跑 xelatex**） |
|---|---|---|
| 国自然 | `projects/NSFC_Young`、`NSFC_General`、`NSFC_Local` | `python packages/bensz-nsfc/scripts/nsfc_project_tool.py build --project-dir projects/NSFC_Young` |
| 省基金 | `projects/GDNSF_General`、`GDNSF_Regional_Young`、`GXNSF_General` | 同上（NSFC 工具链） |
| SCI 论文 | `projects/paper-sci-01` | `python packages/bensz-paper/scripts/paper_project_tool.py build --project-dir projects/paper-sci-01` |
| 投稿信 | `projects/paper-coverletter-01` | 同上（未声明参考文献命令时自动跳过 biber/citeproc） |
| 字数统计 | 任意 `paper-*` | `python packages/bensz-paper/scripts/paper_project_tool.py count-words <tex...>` |
| 学位论文 | `projects/thesis-*`（14 个：安师大/国科大/哈工大/吉农/江科大/江西理工/南大/西北大/南方医/中山/西电等） | `python packages/bensz-thesis/scripts/thesis_project_tool.py build --project-dir projects/thesis-nju-master` |
| Word 初稿 | `projects/thesis-*`、`projects/paper-*` | `... thesis_project_tool.py docx --project-dir projects/thesis-smu-master` |
| 简历 | `projects/cv-01` | `python packages/bensz-cv/scripts/cv_project_tool.py build --project-dir projects/cv-01 --variant all` |

- **编译器必须是 XeLaTeX**（Overleaf: Menu → Compiler → XeLaTeX）。
- DOCX 导出：表格边框/公式/MathML 已做后处理；复杂表格、算法、代码块、TikZ 会在 `.latex-cache/docx/main_docx_quality_report.md` 提示人工复核。
- 仓库级规则（上游 `AGENTS.md`）：任务产物统一落 `./.bensz-api/task-{yyyymmdd-hhmm}-{描述}/{skill}/input|output|log/`；不得污染仓库根目录。

---

## 四、上游 27 个写作技能（本 skill 的“武器库”）

按需 `read_file` 上游技能规范：`E:/MemOmics-Agent/third_party/CRL/skills/<name>/SKILL.md`。

| 阶段 | 技能 | 用途 |
|---|---|---|
| 📚 文献调研 | `research-topic-extractor` → `research-literature-search` → `research-literature-review` → `research-guide-updater` | 提主题 → 多源检索（rls.v1 manifest）→ 专家级综述 → 优化项目指南 |
| 📚 配套 | `research-citation-check`、`research-plan`、`research-idea`、`research-literature-radar`、`research-literature-interpretation` | 引用语义核对 / 策略规划 / 方向评估 / 长期追踪 / 导师式解读 |
| ✍️ 标书 | `nsfc-code`、`nsfc-abstract`、`nsfc-justification-writer`、`nsfc-research-content-writer`、`nsfc-research-foundation-writer`、`nsfc-budget`、`nsfc-length-aligner`、`nsfc-ref-alignment` | 申请代码 / 中英文摘要（中文≤400字、英文≤4000字符）/ 立项依据 / 研究内容 / 研究基础 / 预算 / 篇幅对齐 / 引用核查 |
| ✍️ 质量 | `nsfc-qc`、`nsfc-reviewers`、`nsfc-humanization` | 只读 QC（文风/引用/篇幅/缩写注册表）/ 多专家评审模拟（函评+会评）/ 四层去 AI 味 |
| 📝 SCI | `paper-write-sci`、`paper-select-journal`、`paper-know-journal`、`paper-explain-figures` | 写作与修订 / 选刊 / 期刊投稿指南调研 / 解读 Figure |
| 🔧 模板开发 | `make-latex-model`、`complete-example`、`transfer-old-latex-to-new` | 模板高保真对齐（判断改 projects 还是 packages）/ 示例填充 / 旧材料迁移 |

推荐编排（上游官方工作流）：

```mermaid
graph LR
    A[research-topic-extractor<br/>提主题] --> S[research-literature-search<br/>检索]
    S --> B[research-literature-review<br/>综述]
    B --> C[research-guide-updater<br/>优化指南]
    C --> D[nsfc-* 系列<br/>各部分写作]
    D --> E[nsfc-qc + nsfc-humanization<br/>质检去AI味]
    E --> F[nsfc-reviewers<br/>评审模拟]
```

**上游技能与本机的关系**：这些 skill 是 Claude Code / Codex 格式（`~/.claude/skills`），**MemOmics 不自动加载它们**。做法：`read_file` 其 `SKILL.md` 取流程，用 MemOmics 自己的工具执行；只有用户明确要装到 Claude Code/Codex 时才跑：
`python -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/huangwb8/skills/main/skills/alpha/install-bensz-skills/scripts/bootstrap_install.py').read())" --source research`

---

## 五、🔴 开工前置：grill-me 拷问（用户明确要求：每次都考虑一次）

**凡涉及“方案/结构/取舍”的写作任务（标书立项依据怎么写、论文投哪个刊、简历怎么组织、模板选哪个学校版本），动手前必须过一轮 `skill_view("grill-me")` 轻量拷问**——5 个攻击面：假设 / 边界 / 反例 / 成本 / 替代。

- 目的是**在写之前**逼出：目标期刊或基金代码、创新点与已有工作的差异、篇幅硬约束（≤400 字摘要、8 页标书）、截止时间、复核人是谁。
- **纯机械动作跳过**：编译 PDF、导出 DOCX、统计字数、格式对齐 —— 这些是线性操作，不拷问（否则会被判“为流程而流程”）。
- 拷问结论要落进 `notes.md` 或写入标书的“关键假设”段，不要只停在对话里。

---

## 六、环境依赖与前置检查

| 依赖 | 用途 | 本机状态 |
|---|---|---|
| Python 3 | 全部官方工具与安装器 | ✅ 3.12.10 |
| **TeX 发行版（TeX Live / MiKTeX）+ XeLaTeX** | 编译 PDF；公共包装入 `TEXMFHOME` 也需要 `kpsewhich`/`mktexlsr`/`texhash`/`initexmf` | ❌ **未安装** —— 编译与公共包安装会被阻断 |
| Pandoc（DOCX 导出链） | `docx` 子命令 | 需现场探测 |

**缺 TeX 时怎么办（不允许静默失败）**：
1. 如实告知：**模板库可用（可读可改 .tex），PDF/DOCX 产不出**；
2. 给选项让用户定：① 装 TeX Live/MiKTeX（约 4–7 GB，Windows 需管理员）② 只做内容与结构化写作，编译交给 Overleaf（上传 Overleaf 包：`*-Overleaf-*.zip`）③ 走 DOCX 路线（`academic-thesis-docx`）；
3. **未经用户同意不装大体积发行版**；装则按铁律 29：装到用户环境/项目内，不污染系统。

---

## 七、执行规程（MemOmics 侧）

1. **确认四要素**：文档类型（基金/毕业论文/简历/SCI）· 目标单位或期刊 · 模板（哪所学校/哪个基金类型）· 交付形态（PDF / DOCX / 仅 .tex）。
2. **选模板**：查上表 → 确认 `projects/<模板>` 存在（不存在则 `transfer-old-latex-to-new` 或 `make-latex-model` 新建）。
3. **改内容只动 `extraTex/`**：正文写 `extraTex/**/*.tex`，元数据在 `main.tex` / `extraTex/@config.tex`；**不动 `packages/`**（那是公共层，改它会连带影响其它模板，须走 `make-latex-model` 并跑回归）。
4. **编译**用包内官方工具（第三节命令），产物落 `.latex-cache/`；失败时看官方 wrapper 的报错，再退回 `xelatex → bibtex → xelatex → xelatex` 原生命令排查。
5. **交付**：PDF/DOCX + `count-words` 字数 + 质量报告（DOCX 时）；
6. 收工走铁律 26 协议（rail_review(post) / record_run）。

---

## 八、坑位（实测）

| 现象 | 根因 | 修法 |
|---|---|---|
| `git clone` 报 `schannel: failed to receive handshake` | 本机 GitHub git 协议 TLS 不通（curl 正常） | 用 **Gitee 镜像** `https://gitee.com/huangwb8/ChineseResearchLaTeX.git` |
| terminal 里 `rm -rf` 被拦（`[⚠️ 操作需确认]`） | 平台删除安全门禁 | 不删旧目录；克隆到独立目录再 `mv`（见 `scripts/crl.sh install`） |
| 直接跑 `xelatex main.tex` 报字体/宏包缺失 | 公共包未装入 `TEXMFHOME`，且跳过了官方 wrapper 的环境准备 | 先 `python scripts/install.py install --mirror gitee`，再用包内 `*_project_tool.py build` |
| DOCX 里出现 `$\gamma$` 源码 | 走了旧导出链（未过 MathML 中间态） | 用官方 `docx` 子命令，别自己 pandoc |
| 改了 `packages/` 后别的模板一起坏 | 公共层被直接改 | 改前先判断层级（`make-latex-model`），改后跑该包覆盖模板的回归 |
| Overleaf 报错 | 编译器不是 XeLaTeX / 缺字体 | 传 `*-Overleaf-*.zip`，Menu → Compiler 选 XeLaTeX |

---

## 九、验证与收工

```bash
bash .../chinese-research-latex/scripts/crl.sh check          # 安装与工具链状态
python -m webui.skills_registry --build                       # 改了触发词后重建索引
python scripts/verify_skill_registration.py chinese-research-latex
python scripts/check_skills_gate.py                           # 提交门禁
```

上游版本升级：`cd third_party/CRL && git -C . pull`（Gitee 源）或重跑 `crl.sh install`；模板 zip 也可直接从 release 下载（`NSFC_Young-v4.1.1.zip` 等）。

相关参考：`references/upstream-skills-map.md`（29 技能逐条触发词/输入输出）、`references/product-lines-and-build.md`（产品线细节与 DOCX 后处理规则）。

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| - | - | - | 2026-10-12 | SKILL.md | - | - |  |
| - | - | - | 2026-10-12 | registration | - | - |  |


| - | - | - | 2026-10-12 | gate-run | - | - |  |
| - | - | - | 2026-10-12 | gate-diagnose | - | - |  |
| - | - | - | 2026-10-12 | gate-diagnose | - | - |  |
| - | - | - | 2026-10-12 | gate-diagnose | - | - |  |
| - | - | - | 2026-10-12 | gate-rerun | - | - |  |
| - | - | - | 2026-10-12 | gate-final | - | - |  |
| - | - | - | 2026-10-12 | crl.sh | - | - |  |
## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| [skills-gate] FAIL —— 2 failed, 896 passed (91.6s) | 索引重建后 paper-structured-extraction 被解析为 R | 待办：① 定位第 2 个失败（怀疑 test_webui_picker_and_prompt_ind |

