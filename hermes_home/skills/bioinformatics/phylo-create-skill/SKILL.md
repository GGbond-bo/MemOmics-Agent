---
name: "phylo-create-skill"
display-name: "Create Skill"
id: "skill_80991743e52842abb92207cd7ff8c29e"

category: General Utility
when_to_use: "[phylo-create-skill] Create, test, package, and present reusable skills for Phylo's Biomni platform and bioinformatics workflows."
starting-prompt: "Help me design a skill for..."
---
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。以下规则覆盖所有 Biomni 默认行为。

### 规则1: 拿到数据 → 必须调 search_knowledge
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 web 搜索文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 7步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. check_env 检查环境
3. rail_review(pre) 前置审查
4. source/import 预写脚本（禁止 inline 代码）
5. terminal 执行（分步执行，禁止 && 连接多步骤）
6. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
7. rail_review(post) 后置审查
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时（如 resolution, n_pcs, min_features, FDR threshold等），**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式（多角色对抗 v3）：
  - 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
  - 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
  - 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
  - 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
  - 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
  - 辩论结果自动归档到 results/.../log/debate_*.json
- **不确定的参数就辩论**，不要自己拍脑袋

### 规则5: 执行后审查

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

  - **图片检查**：
    - 图有没有生成？没生成 → **强制重新执行**
    - 图片是否空白（全白/全黑/全单一色）？空白 → **强制重新出图**
    - 图片是否有 NA/缺失值（>10% 像素是 NA）？有 NA → **强制重新出图**
    - 图片大小是否过小（<5KB）？过小 → **强制重新出图**
    - 图片数量是否足够？（每步至少 1 张图，关键步骤至少 2-3 张）
  - **代码质量检查**：
    - 代码行数是否合理？（过短可能偷懒，过长可能未分段）
    - 代码是否有注释？
    - 代码是否分段执行（禁止 && 连接多步骤）？
  - **结果合理性**：
    - 数值范围是否合理？
    - 跟知识库对应吗？
  - **参数和结论辩论**：
    - 有参数的选择 → **必须调 debate_analysis 辩论**
    - 有结论输出 → **必须调 debate_analysis 辩论**
    - 不通过 → 修复重跑
    - 通过 → **必须调 skill_evolution(action="record_run")** 记录成功经验（skill_name/script_name/species/tissue/direction/params_used/result_summary/quality_score/notes） → 创建目录存储(figures/results/scripts/data) → 下一步
    - **不通过 → 修复后重跑 → 成功后调 skill_evolution(action="record_run")**；如果是脚本报错 → **调 skill_evolution(action="record_error")** 记录根因+修复方案

### 规则6: 结果存储结构
```
results/<模块>/<方法>/
  ├── scripts/     # 分析脚本
  ├── figures/     # PNG + SVG 图表
  ├── data/        # RDS/H5AD 中间数据
  └── results/     # CSV/TSV 结果表
```


### 规则7: 脚本出错/成功 → 必须调 skill_evolution（自进化）

| 时机 | action | 调 | 不调 |
|------|--------|----|------|
| 脚本报错+你分析根因+修复后 | record_error | ✅ R/Python 脚本报错，你找到根因并修复 | ❌ trivial 错误（打字错误、路径不存在） |
| 脚本成功+结果通过 rail_review | record_success | ✅ 分析步骤完成，图生成，审查通过 | ❌ 闲聊/方法咨询/非分析任务 |
| 修复后脚本验证稳定有效 | update_script | ✅ 同一错误修复了，重跑成功 | ❌ 只改参数没改脚本；未验证就更新 |

---



# Phylo Create Skill

A skill-creator tailored for Phylo's Biomni platform and the bioinformatics domain, with biology-specific interviewing, domain patterns, and eval scaffolding baked in. The core loop is: draft → test → review → improve → package → present.

---

## Process Overview

1. **Capture intent** — understand what the skill does and when it should trigger
2. **Interview** — ask bio-specific clarifying questions (databases, file formats, agent vs. standalone)
3. **Draft SKILL.md** — write the skill instructions and frontmatter
4. **Test** — run 2–3 representative prompts and review output quality
5. **Iterate** — revise based on gaps or mismatches
6. **Package & present** — create the skill folder under `/mnt/results/skills/<slug>/` and call `CreateSkill`

You don't need to go in strict order. If the user already has a draft, jump to testing. If they just want to vibe without evals, that's fine too.

If the user did not explicitly ask you to create a skill, ask first before creating one. Offer skill creation when the workflow is genuinely reusable:
- repeated or likely to recur
- procedural, with stable steps
- worth saving as knowledge for future tasks

---

## Step 1: Capture Intent

Extract from the conversation first — tools used, corrections made, input/output formats observed. Then confirm:

1. What should this skill enable Biomni to do?
2. What kind of user prompt triggers it? (bioinformatics jargon, file uploads, database names, etc.)
3. Does it run inside a Biomni agent session (E2B sandbox, tool call) or standalone?
4. What's the expected output — a file, a report, a protocol, code, a database query result?

---

## Step 2: Bio-Specific Interview

Ask targeted questions before drafting. Typical gaps in bio skills:

### Data & Formats
- What file formats are involved? (FASTA/FASTQ, VCF, BAM/SAM, BED, GTF, AnnData `.h5ad`, CSV, JSON, PDF protocol)
- What's the expected input size? (a handful of gene names vs. a whole-genome VCF)
- Does the skill need to handle multi-sample or batch inputs?

### Databases & APIs
- Which biological databases does the skill query?
- Are there licensing or access constraints on any databases (e.g., OMIM, DisGeNET, DepMap require licenses)?
- Does it need to cross-reference multiple databases and reconcile identifiers (gene symbol → Ensembl ID → UniProt accession)?

### Compute & Environment
- Does the skill run heavy computation (alignment, docking, ML inference) that needs E2B sandbox resources?
- Does it need Modal or another async runner for long jobs?
- Does it produce files the user downloads (BAM, ZIP of results, PDF report)?

### Agent Architecture (if Biomni-facing)
- Is this a new Biomni tool (defined in the A2 agent's tool registry)?
- Does it need to write back to the user's session storage (S3, Firestore)?
- Should it produce SSE streaming output or a single blocking result?

### Scientific Correctness
- Are there common failure modes that would silently produce wrong biology? (e.g., ignoring strand, mixing GRCh37/GRCh38 coordinates, using non-canonical gene symbols)
- Should the skill sanity-check its own outputs before returning them?

---

## Step 3: Write the SKILL.md

Every bio skill SKILL.md should include:

### Required sections
- **YAML frontmatter** — `name`, `description` (include biology keywords that would trigger it)
- **Scope** — one sentence on what it does and what it explicitly does NOT do
- **Inputs** — file formats, identifier types, expected ranges
- **Outputs** — format, where it's saved (S3 path / local / chat)
- **Workflow steps** — numbered, imperative, with biological context for why each step matters
- **Scientific caveats** — genome build assumptions, known edge cases, licensing flags

When generating a reusable skill package, the top-level file must live at:

```text
/mnt/results/skills/<slug>/SKILL.md
```

Put any supporting files in the same folder tree. Do not write generated skill packages at the root of `/mnt/results`.

### Optional sections (add when relevant)
- **Database reference table** — which DBs are queried, what identifiers they accept, rate limits
- **File format handling** — how to parse/validate the format before processing
- **Error handling** — what to do when a gene isn't found, a database is down, coordinates are out of range

### Description writing tips for biology skills
The description must contain enough domain vocabulary to trigger reliably. Include:
- The names of specific databases, tools, or file formats involved
- The scientific task type (variant annotation, pathway analysis, docking, protocol generation, etc.)
- The Biomni context if applicable ("Biomni tool", "agent session", "lab automation")

Make descriptions slightly pushy: instead of "Annotates VCF files", write "Annotates VCF files with ClinVar, gnomAD, and COSMIC data. Use this skill whenever someone uploads a VCF, asks about variant pathogenicity, or wants to know if a mutation is in a cancer database — even if they don't say 'annotate'."

---

## Step 4: Test Cases

After drafting, propose 2–3 test prompts that mirror real user requests. Good bio skill test prompts are:

- **Specific enough** to trigger the skill ("Annotate this VCF with ClinVar data" not "help me with variants")
- **Biologically realistic** — use real gene names, real database names, plausible file names
- **Representative of the range** — one simple case, one with a tricky edge (multi-sample, missing ID, big file), one that could go wrong scientifically

Share test prompts with the user before running: "Here are three prompts I'd like to test. Do they match what real Biomni users would say?"

Run each one manually (since there are no subagents — do them sequentially). For each run:
1. Follow the skill's instructions as if encountering the task fresh
2. Record: did it produce the right output? Did it catch biological errors? Was the output format correct?

---

## Step 5: Evaluate & Iterate

### What to look for in bio skill outputs

**Scientific correctness**
- Are gene/protein identifiers resolved consistently?
- Are genome coordinates in the right build?
- Are database citations accurate (no hallucinated PMIDs, no made-up ClinVar accessions)?

**Completeness**
- Does the output include all the fields the user needs?
- Are edge cases (no results found, ambiguous gene name, deprecated ID) handled gracefully?

**Format fidelity**
- If the skill outputs a file (FASTA, VCF, report PDF), is it properly formatted?
- If it outputs a protocol, does it follow a standard lab format?

**Biomni integration (if applicable)**
- Does the skill correctly reference Biomni tool schemas?
- Does it produce the right SSE event structure?
- Are S3 paths and session IDs handled correctly?

Ask the user to review outputs and flag:
- Any scientifically wrong result (even subtle errors matter in biology)
- Missing context a researcher would expect
- Formatting that doesn't match what Biomni renders

Revise the skill and re-run. Repeat until you're both happy with it.

---

## Step 6: Package & Present

Once satisfied, create the generated skill package under:

```text
/mnt/results/skills/<slug>/
```

The package must include:
- `SKILL.md` at the folder root
- YAML frontmatter with at least `name` and `description`
- concise instructions focused on when to use the skill and how to run the workflow

After the package is written, call the `CreateSkill` tool with:

```json
{
  "folder_paths": ["skills/<slug>"]
}
```

Call `CreateSkill` as the final action. The tool validates the generated skill, surfaces the preview UI for `SKILL.md`, and lets the user add the skill to personal skills.

