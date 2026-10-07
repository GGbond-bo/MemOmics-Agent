# 论文 claim ↔ 开源代码 审计配方（模式 E）

> 首次实战 2026-10-04：用户给 `https://github.com/snap-stanford/Biomni.git`，断言
> 「这里就是 Biomni 的代码，但是里面的东西，并不像它所说的那样」→ 需核实并给出真实机制。
> 本文件 = 可复用配方 + 该次审计的**全量实测数字与代码出处**（下次不用重新 clone 数一遍）。

---

## 0. 一分钟版流程

```bash
git clone --depth 1 <repo> <新目录名>      # 不要 rm -rf 旧目录（护栏会拦）
python scripts/audit_agent_repo_claims.py <repo_root>   # 一条命令出全表
# 然后手读三处：README 的 Important Note / docs/known_conflicts.md / agent 主文件 + retriever
```

判据（必须全部进交付）：
1. **开源仓库 ≠ 论文系统 ≠ 线上平台** —— 找官方的 frozen / version 声明，它调和大部分差异。
2. **区分「论文夸大」与「我数错了」** —— 先手工复核自己的统计脚本（见 §4 AST 陷阱）。
3. **用户心智模型逐层对照** —— 给「用户词汇 → 代码实际机制」映射，先认观察、再纠机制。

---

## 1. 审计对象与仓库事实（Biomni，2026-10-04 实测）

| 项 | 值 |
|---|---|
| repo | `https://github.com/snap-stanford/Biomni.git` |
| HEAD | `400c1f36…` "Merge pull request #259 from snap-stanford/protocols_database"，2026-01-14 |
| 体积 | `git clone --depth 1` = **5.0MB**，数秒完成（github.com 当时可通） |
| 本地路径 | `E:/MemOmics-Agent/work/Biomni_src`（工作副本，非交付物） |
| 顶层 | `biomni/` `biomni_env/` `docs/` `tutorials/` `figs/` + README/DETAILS/CONTRIBUTION |

⚠️ `DETAILS.md` 是**第三方工具（Detailer）自动生成**的代码库分析，不是官方文档——
但里面那句 `No explicit test files detected; testing likely manual` 恰好独立佐证了 §2 的测试结论。

---

## 2. 论文声称 vs 代码实测（核心交付表）

| 指标 | 论文声称 | 代码实测 | 代码出处 |
|---|---|---|---|
| 工具 | 150 specialized tools / 25 domains | **224** 条工具描述 / **260** 个顶层函数 / **22** 个模块 | `biomni/tool/tool_description/*.py`（数 list 条目）、`biomni/tool/*.py`（数 `ast.FunctionDef`） |
| 软件 | 105 software | **113** | `biomni/env_desc.py` → `library_content_dict` |
| 数据库 | 59 databases | **33** + **76** | `biomni/tool/schema_db/*.pkl`(33) / `env_desc.py` → `data_lake_dict`(76，混了数据集不是纯库) |
| 测试用例 | 每个工具"带必须通过的测试用例" | **全仓 0 个** | `find . -name "test_*.py"` 只命中 `tutorials/examples/expose_biomni_server/test_mcp_server.py`（与工具质量无关） |

**"2500 篇论文 → 工具"链条可验证性**：仓库只有 3 个**管道脚本**，中间产物未入库 ⇒ **链条是断的**。

| 脚本 | 作用 | 关键参数 |
|---|---|---|
| `biomni/biorxiv_scripts/extract_biorxiv_tasks.py` | 从 bioRxiv PDF 抽 任务/数据库/软件 | `claude-3-haiku-20240307`，chunk 4000 / overlap 400 / max-paper-length 200000，`PaperTaskExtractor` |
| `biomni/biorxiv_scripts/generate_function.py` | **把任务描述直接生成 Python 函数** | `claude-3-7-sonnet-latest`，temperature 0.7，`FunctionGenerator` |
| `biomni/biorxiv_scripts/process_all_subjects.py` | 批量跑上述两步 | — |

⇒ 结论：`tool/*.py` 里函数体那种"docstring 风格 + 函数内 import + 返回 research log"的形态，
正是 `generate_function.py` 的产物特征（LLM 生成），但**生成源清单（2500 篇的产物）不在仓库里**。

### 工具描述条目分布（224 条）
`database 40 · pharmacology 25 · genomics 19 · molecular_biology 18 · microbiology 12 · physiology 11 ·
bioimaging 10 · immunology 10 · genetics 9 · literature 8 · synthetic_biology 8 · bioengineering 7 ·
pathology 7 · systems_biology 7 · biochemistry 6 · cancer_biology 6 · cell_biology 5 · protocols 4 ·
biophysics 3 · glycoengineering 3 · lab_automation 3 · support_tools 3`

---

## 3. 运行时机制真相（三层，彼此独立）

| 层 | 代码位置 | 真实机制（与论文描述的差异） |
|---|---|---|
| **工具层** | `biomni/tool/*.py` | 224 条带描述的普通 Python 函数；**没有 skill 注册表、没有触发词、没有按意图路由** |
| **资源检索层** | `biomni/model/retriever.py` → `ToolRetriever.prompt_based_retrieval()` | **一次 LLM 调用**：把 tools / data_lake / libraries / know_how 编号成清单塞进 prompt，让模型只回 `TOOLS: [0,3,5]` 这种**索引列表**。默认 LLM = `ChatOpenAI(model="gpt-4o")`。prompt 原话 *"Be generous in your selection… When in doubt about a database tool, include it rather than exclude it"* ⇒ **宁滥勿缺的粗筛**。**全仓无 embedding / 向量库 / 语义检索**（grep `embedding|faiss|chroma|sentence_transformers` 仅命中 `env_desc.py` 的软件清单条目） |
| **Know-How 层** | `biomni/know_how/*.md` + `loader.py` + `a1.py` | 这才是最像 skill 的东西（best practices / protocols / troubleshooting）。**仓库只有 2 篇**：`sgRNA_design_guide.md`(15KB)、`single_cell_annotation.md`(7.6KB)。且 `a1.py:1352` 注释写明 *"This makes best practices always available, not just when retrieved"* ⇒ **全量注入 system prompt，不走检索**；`a1.py:219` 打印 `📚 Loaded N know-how documents` |

**agent 主循环**（`biomni/agent/a1.py`，134KB）：LangGraph **generate → execute → routing**，
靠 XML 标签 `<execute>` / `<solution>` 解析执行；`#!R` / `#!BASH` / `#!CLI` 前缀分流到 R / Bash；
另有 `execute_self_critic` / `routing_function_self_critic` 分支。
`biomni/config.py`：`use_tool_retriever: bool = True`、`llm = "claude-sonnet-4-5"`、`timeout_seconds = 600`。

⇒ **用户「触发 skill 再调工具」的直觉，机制上不成立**；其体验大概率来自 web 平台（见 §5 的 frozen 声明）。

---

## 4. 🔴 AST 量化陷阱（本次自伤一次）

**目标**：量化「有多少工具函数是真实现 vs 空壳」。

**第一版（错）**：只匹配 `import X` 形式的正则/AST → 得出 **182/260 = 70% 无真实动作**。
**根因**：漏掉 `from FlowCytometryTools import FCMeasurement` 之类的 `ast.ImportFrom`，
而 `analyze_flow_cytometry_immunophenotyping` 恰恰是**真实现**（读 FCS 文件 + 真实 gating）。

**修正版**：收集两种 import 节点 + `sys.stdlib_module_names` 过滤 → **50/260 = 19%**，
且其中多为「返回一份 protocol / 说明文档」的**合法函数**（如 `get_golden_gate_assembly_protocol`、
`get_oligo_annealing_protocol`），不是坏件。

```python
mods = set()
for sub in ast.walk(fn):
    if isinstance(sub, ast.Import):
        for a in sub.names: mods.add(a.name.split(".")[0])
    elif isinstance(sub, ast.ImportFrom):
        if sub.module: mods.add(sub.module.split(".")[0])
third_party = {m for m in mods if m not in sys.stdlib_module_names}
```

**教训**：
- 任何量化结论，**先手工抽 1–2 个样本函数体读一遍**再出口。
- 说错了要在**同一轮回复里显式纠正**并给出修正后的数（本会话即如此，用户接受度很高；
  对"悄悄改口"接受度很低）。交付里保留"我上一版判断有错"这一节。

**修正后的第三方 import 直方图**（260 个函数）：
`numpy 65 · pandas 47 · scipy 43 · skimage 18 · matplotlib 17 · Bio 12 · cv2 12 · sklearn 4 ·
FlowCytometryTools 4 · requests 3 · scanpy 3 · trackpy 2 · DeepPurpose 2 · statsmodels 2 · nibabel 2 ·
cobra 2 · pykalman/community/gseapy/networkx/flowkit/pyliftover/msprime/popv/scvi/harmony/accelerate/cooler 各 1`
⇒ 主体是 numpy/pandas/scipy 自算，**真软件集成很薄**，这是比"空壳率"更重要的观察。

---

## 5. 官方自陈的硬伤（逐条引原文，交付必带）

1. **frozen 声明**（README `Important Note`）：
   *"This release was frozen as of April 15 2025, so it differs from the current web platform."*
   → 用户用的是 web 平台，与这份代码**本就不是一个东西**。**这是最有力的调和证据，先找它。**
2. **工具质量自陈**（README 贡献节）：*"many current tools are not optimized - fix and replacements are welcome!"*
3. **部分工具开箱即坏**（`docs/known_conflicts.md`）：`hyperimpute`、`langchain_aws`、
   `cnvkit`（需独立 py3.10 环境，支撑 `analyze_copy_number_purity_ploidy_and_focal_events`）、
   `panhumanpy`（需专属环境，支撑 `annotate_celltype_with_panhumanpy`）**默认不安装**，
   且部分需**手动取消代码注释**才能启用。
4. **安全自陈**：*"Currently, Biomni executes LLM-generated code with full system privileges."*

---

## 6. 常见误解澄清（「2500 篇论文是不是就是它的 skill？」）

| 用户词汇 | 论文/代码实际概念 |
|---|---|
| "触发对应的 skill" | 不存在。→ 一次 LLM `prompt_based_retrieval()` 按**编号索引**选资源 |
| "调用里面的工具" | 成立，但是**普通 Python 函数**，agent 自己写代码调用，无注册表/无触发词 |
| "2500 篇论文整理出来的东西" | 是**可执行管道的输入**（3 个脚本），**产物未入库**，无法审计 |
| "像 skill 的东西" | 最接近的是 `know_how/`，但**只有 2 篇**且**全量注入** system prompt |

**一句话定位**：Biomni 靠「一次 LLM 粗筛 + know-how 全量注入」，规模与精度都被卡住；
MemOmics 的 skill 体系（触发词 + 触发级别 + 注册表 + 自进化日志）**结构化程度明显更高**——
这正是对方 know-how 只有 2 篇、检索只能"宁滥勿缺"的结构性原因。

---

## 7. 可复用的写码要点

- 数"agent 能看到的工具"要数 **tool_description 的 list 条目**，不是数函数定义——两者会不一致。
- `env_desc.py` 里的 `data_lake_dict`（数据）与 `library_content_dict`（软件）用 `ast.literal_eval` 取 key 计数即可。
- 判断某仓"有没有测试"用 `find -path ./.git -prune -o -name "test_*.py" -print`（不要 `grep -r test`，噪声大）。
- `git log --oneline | wc -l` 在 `--depth 1` 下恒为 1，**不能用来判断仓库活跃度**。