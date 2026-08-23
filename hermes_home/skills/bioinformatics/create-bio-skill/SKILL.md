---
name: create-bio-skill
description: "当 skill_view 返回 not found 且没有相似 skill，或用户指定了特定包时触发。自动查询官方文档+文献，按 BioMinI 标准格式创建新的生信 skill（含 SKILL.md + 脚本模板 + MemOmics 强制规则）。创建后立即可用。"
when_to_use: "[create-bio-skill] 当 skill_view 返回 not found 且没有相似 skill，或用户指定了特定包时触发。自动查询官方文档+文献，按 BioMinI 标准格式创建新的生信 skill（含 SKILL.md + 脚本模板 + MemOmics 强制规则）。创建后立即可用。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [meta, skill, create, 生成技能, 创建技能, skill不存在, not found, 新建skill]
    difficulty: advanced
    language: Python
    category: General Utility
prerequisites:
  r_packages: []
  python_packages: []
---

# 生信 Skill 自动创建器

当分析需要的 skill 在 skill 库中不存在时，自动查询官方文档和文献，按 MemOmics/BioMinI 标准格式创建完整的新 skill。

## 🛑 Step 0: 创建前重复检测（必须执行，不可跳过）

> **在创建任何新 skill 之前，必须先检查是否已存在同功能 skill。**

1. 调用 `skill_search` 用用户提到的包名/功能关键词搜索
2. 检查搜索结果中是否有同名的 skill
3. 检查搜索结果中是否有功能重叠的 skill（如 CellChat vs cellchat-v2 vs cell-cell-communication）
4. **如果已存在 → 直接告诉用户**："这个 skill 已经有了: `skill_view(\"<name>\")`，不需要重新创建"
5. **如果功能类似但不完全相同 → 告诉用户差异**，让用户决定是否创建新 skill 还是扩展现有 skill
6. 只有确认**不存在同功能 skill** 时，才进入 Step 1

> **铁律: Step 0 未执行 = 不允许进入 Step 1。** 重复创建已存在的 skill 会污染 skill 库。

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 meta-skill 用于创建新 skill，创建的新 skill 必须包含下方全部规则。

### 规则1: 创建前必须查官方文档
- **绝对不能凭记忆创建 skill** — 必须先用 `web_search` + `web_extract` 查询该包的官方文档
- 至少查询 3 个页面：官方文档首页 + API 参考 + 教程/vignette
- 同时用 `search_papers_by_context` 搜索相关文献，提取方法参数
- 用户指定了某个包（如"我要用 scTour"）→ 必须查该包的官方文档

### 规则2: 创建的 SKILL.md 必须包含标准结构
每个新建的 skill 的 SKILL.md 必须包含以下结构，缺一不可：
1. **YAML frontmatter**（name/description/version/author/license/platforms/metadata/prerequisites）
2. **⛔ MemOmics 强制规则块**（7 条规则，逐字复制下方模板）
3. **分析步骤标题 + 概述**
4. **When to Use**（触发场景）
5. **Pipeline**（每步标注 Tool: terminal）
6. **Parameters**（关键参数 + 默认值 + 来源）
7. **Proven Scripts**（脚本模板引用 + 有效空表格，见规则2.6）
8. **Common Issues**（常见问题）
9. **References**（文献引用）

### 规则2.5: 创建新 skill 时**必须同时生成 `skill.json`**
> **⚠️ 历史教训**：`skill_evolution(action="record_run")` 的 `_record_success` 函数依赖 `skill.json` 存储 proven_params。如果 `skill.json` 不存在，`record_run` 会**静默失败**——返回 Success 但不落盘。这是所有新 skill 的共性缺陷源。2026-07-08 会话中 `sctour-trajectory-inference` 的 4 次 record_run 均因缺少 skill.json 而静默丢失。

### Step 7.5: 注册触发场景到 SOUL.md 和 SOUL-detail.md

新 skill 创建后，必须注册触发关键词以保证下次触发：

1. **SOUL.md 必触发列表**: 在 `<!-- AUTO_SKILL_INSERT_MARKER -->` 前插入:
   `| "<触发词>" | skill_view("<skill-name>") |`

2. **SOUL-detail.md 领域表**: 如果新 skill 属于已有领域，确认领域表覆盖

3. **SOUL-detail.md 场景触发表**: 如果有特定触发场景，追加到场景表

⛔ 未注册触发场景 → 后续分析无法自动触发此 skill。

---

创建 SKILL.md 后，**必须立即在同目录下创建 `skill.json`**，格式如下：

```json
{
  "name": "<skill-name>",
  "version": "1.0.0",
  "success_count": 0,
  "proven_script": "",
  "proven_params": [],
  "user_prefs": {
    "last_used_script": "",
    "preferred_params": {},
    "notes": ""
  }
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| `proven_params[].user_score` | int (0-10) | 🆕 用户认可打分。8-10=满意，4-6=一般，1-3=不满意但留档。**只有用户明确认可的脚本才有此字段** |
| `proven_params[].auto_score` | int (0-10) | 🆕 `rail_review(post)` 自动评的技术分。基于图质量(4) + 代码质量(3) + 性能(3) |
| `proven_params[].approved` | bool | 🆕 是否经用户确认。true → 参与排序推荐，false → 仅存 logs/ 供调试 |
| `user_prefs.last_used_script` | str | 🆕 最近一次使用的脚本路径，`query_logs` 优先返回 |
| `user_prefs.preferred_params` | obj | 🆕 用户偏好的参数组合，跨会话复用 |

创建方法：`write_file` 写入 `SKILL.md` 同目录下的 `skill.json`。

### 规则2.6: SKILL.md 的 Proven Scripts 表必须是有效空表格
`_record_success` 通过正则匹配 `## Proven Scripts` 后的 markdown 表格来追加行。**必须使用有效 markdown 表格**（含表头+分隔行+占位行），不能是纯注释或空段落。

```markdown
## Proven Scripts

> 经实际运行验证成功的脚本记录。`skill_evolution(action="record_run")` 自动追加至此表。
>
> 🆕 评分规则：`auto` 来自 rail_review 技术审查，`user` 来自用户认可。`query_logs` 按 approved → recency → score 排序推荐。

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|:----|:----|:----|:----:|:-----|:----:|:----:|:-:|
| <!-- 首次运行后自动填充 --> | | | | | | | |
```

注意：
- `auto` = rail_review 自动技术分 (0-10)
- `user` = 用户认可分 (0-10)，只有用户明确认可才填
- `✔` = approved，true=参与推荐，false=仅存档 logs/
- `<!-- 首次运行后自动填充 -->` 占位行是必需的，否则 `_record_success` 的正则匹配可能找不到表格行追加位置

### 规则3: 创建的脚本必须包含审查辩论铁律头
每个新建 skill 的 `scripts/run.py` 和 `scripts/reference_script.*` 必须在文件开头包含 MemOmics 审查辩论铁律注释块（逐字复制下方模板）。

### 规则4: 创建后必须验证 + 分析后审核

**4a. 创建后验证（基础检查）**
- 用 `skill_view(name="新skill名")` 确认可加载
- 确认 SKILL.md 的强制规则块完整
- 确认脚本模板的铁律头完整

**4b. 分析后审核（质量检查 — skill 创建后、交付用户前必须执行）**

创建 skill 后，必须对照以下 **6 项审核清单** 逐项检查。任何一项不通过 → 修正后重审，全部通过才能交付。

### 规则4c: 🔴 试运行门禁（真实数据验证 — 2026-08-10 新增）

> **规则4a/4b 全是静态检查，防不了"脚本写得规范但跑不出结果"。**
> 静态检查通过 ≠ skill 合格。**必须真实运行一次**。

创建后**必须**执行（不可跳过，任何一步失败 → 修正后重跑）：

```
Tool: execute_r / execute_python
1. 生成 synthetic 小数据（R: data.frame / Python: pandas.DataFrame，覆盖典型输入格式）
2. 执行 scripts/reference_script.*（真实调用）
3. 检查输出：
   a. 退出码 = 0（无报错）
   b. 产出物存在（图/表/结果文件，大小 > 0KB）
   c. 图非空白（rail_review 强制项）
4. 失败 → 修正脚本 → 重跑，直到通过
```

**通过标准**：输出文件真实存在 + 内容非空。**不通过 → skill 标记 `_UNTESTED_`，禁止交付**。

### 规则4d: 🔴 frontmatter 自动校验（防错分 — 2026-08-10 新增）

> **历史教训**：2026-08-06 审查发现 51/308 个 skill 的 frontmatter `category` 写错（scRNA 写成 GWAS、bulk 写成 scRNA、代谢组写成 Proteomics），根因是 LLM 套模板不填。静态审核单靠"自觉"不可靠。

创建后**必须**用脚本校验 frontmatter：

```
Tool: terminal（python 校验脚本）
1. 解析 SKILL.md frontmatter（yaml）
2. 校验规则：
   a. name 与目录名一致（小写）
   b. description 非空且含具体分析内容（>20 字符，非模板默认值）
   c. category ∈ 规则引擎合法集：
      {Transcriptomics, Proteomics, Metabolomics, Epigenomics, Genomics, Genetics,
       Spatial, Immunology, Microbiology, Drug Discovery, General Utility, ...}
      —— 按测序类型判定：代谢组(LC-MS/GC-MS/NMR)→Metabolomics；
      RNA→Transcriptomics；蛋白→Proteomics；ATAC→Epigenomics
   d. metadata.hermes.tags 含 ≥4 个关键词（包名/中文/英文/同义词）
3. 任一失败 → 自动修正后重验；修正不了 → 打回重写
```

**通过标准**：脚本输出 4 项全 ✅。

### 规则4e: 🔴 注册 + 意图测试门禁（触发保障 — 2026-08-10 新增）

> **历史教训**：注册 ≠ 可触发。实测发现 `register_to_soul_md` 旧格式
> `| **名称** | skill | 描述。用户说"kw"时触发 |` 与触发表真实格式
> `| "kw1" / "kw2" | skill_view("skill") |` 不一致 → agent 触发解析不认。
> 且"画火山图"类常见意图未进关键词 → 用户意图命不中。静态注册不够，
> **必须用真实意图模拟测试**。

创建 skill 后**必须**运行意图测试（不可跳过）：

```
Tool: terminal
python scripts/verify_skill_trigger.py <skill-name> \
  --intents "典型用户意图1|意图2|意图3|...（≥5 条，覆盖：分析意图/画图意图/英文意图）"

通过标准（4 项全 ✅）：
  1. SOUL.md 注册行存在（管道式格式）
  2. 触发关键词 ≥ 4 个
  3. 意图命中 100%（未命中 → 补关键词到 SOUL.md 注册行，重测）
  4. SKILL.md name 与目录一致 + description ≥ 20 字
失败 → 修正注册行/关键词后重测，直到全过才能交付。
```

**注册格式（必须管道式）**：
```markdown
| "关键词1" / "关键词2" / "..." | `skill_view("<skill-name>")` |
```

### 规则3.5: 必须使用 skill_template_generator.py 生成（2026-08-10 新增）

> **历史教训**：`scripts/skill_template_generator.py` 已存在但创建时从未被调用——LLM 手写导致 frontmatter 错分/结构缺失。

创建 SKILL.md 时**必须**：

```
Tool: terminal（python 调用）
from scripts.skill_template_generator import generate_skill_md, register_to_soul_md
content = generate_skill_md(name=..., description=..., category=..., ...)
# → 用生成的 content 作为 SKILL.md 基础，再按官方文档补全
```

禁止纯手写 frontmatter（category/tags 由函数参数显式传入，防止模板默认值泄漏）。

| # | 审核项 | 检查内容 | 不通过 → 修正动作 |
|---|--------|----------|-------------------|
| 1 | **官网一致性** | SKILL.md 中的函数名、参数名、默认值是否与官方文档/API 完全一致？用 `web_extract` 重新拉取官方 API 页面逐条比对 | 不一致 → 修正 SKILL.md 和脚本中的函数/参数，重新 `skill_manage` 更新 |
| 2 | **文档/教程参考** | 是否参考了官方教程/vignette/example？References 中是否列出了官方文档 URL？是否参考了实例文档或教程？ | 未参考 → 补查官方教程页面，提取示例代码，更新脚本模板 + References |
| 3 | **安装包完整** | prerequisites 的 r_packages/python_packages 是否覆盖了所有依赖？是否包含隐式依赖（如 scTour 需要 scikit-misc 但不自动安装）？用 `check_env` 验证 | 缺失 → 补全到 prerequisites，在 Common Issues 中说明隐式依赖的安装方法 |
| 4 | **使用场景说明** | When to Use 是否明确写了「应该使用」和「不应该使用」两种场景？是否有量化阈值（如最小细胞数、最小基因数）？ | 不完整 → 补充「不应该使用」场景和量化阈值 |
| 5 | **查询官网留痕** | Step 1 查询的官网 URL 是否记录在 References 中？是否有 `web_search` + `web_extract` 的调用证据？ | 未留痕 → 补录官方文档 URL 到 References |
| 6 | **🔴 SOUL.md 注册** | 新 skill 是否已注册到 SOUL.md 技能匹配表？用 grep 确认。未注册 → 后续分析无法自动触发 skill_view | 未注册 → 在 AUTO_SKILL_INSERT_MARKER 上方插入 |
| 7 | **🔴 铁律 26 协议块** | 新 SKILL.md 末尾是否有终端完成后强制协议块？ | 缺失 → 追加协议块 |
| 8 | **🔴 SOUL-detail.md 注册** | 触发场景是否注册到 SOUL.md 必触发列表或 SOUL-detail.md？ | 缺失 → 追加触发条目 |
| 9 | **🔴 SOUL.md 注册** | 新 skill 是否已注册到 `hermes_home/SOUL.md` 的技能匹配表中？用 `grep` 搜索 skill name 确认存在。**这是最关键的一项**：未注册 → 后续分析无法自动触发 skill_view | 未注册 → 按 Step 7 格式在 `<!-- AUTO_SKILL_INSERT_MARKER -->` 上方插入新行 |

**审核执行方式**：
- 在 terminal 中逐项执行检查，每项检查输出 ✅ 通过 / ❌ 不通过 + 原因
- 6 项全部 ✅ → 审核通过，skill 可交付
- 有 ❌ → 修正后重新审核该项，直到全部通过
- 审核结果调 `skill_evolution(action="record_run")` 记录（skill_name/quality_score/notes）

- 验证 + 审核全部通过 → 继续正常分析流程

---

## When to Use

### 触发条件
1. `skill_view` 返回 `{"success": false, "error": "Skill 'xxx' not found"}`
2. `skills_list` 搜索后没有相似 skill，或用户明确指定了某个包
3. SOUL.md 规则0.1 触发

### 不触发
1. skill 库已有对应 skill
2. 找到相似 skill 且用户同意使用相似 skill
3. 用户没有指定包，且找到的相似 skill 完全满足需求

---

## Pipeline

### Step 1: 查询官方文档（硬门禁，不可跳过）

> **🔴 这是硬门禁。web_extract 失败 → 不允许进入 Step 2。必须换源重试，直到成功提取官方文档内容。**

```
Tool: web_search + web_extract (MANDATORY, max 3 retries)

1. web_search(query="<包名> official documentation tutorial")
2. web_extract(urls=[官方文档URL, API参考URL, 教程URL])
3. 提取：包名、主要函数、参数列表、默认值、输入输出格式、示例代码
4. 记录：提取时间、文档版本号、API 函数名列表（用于 Step 9 一致性比对）

🔴 失败处理：
   - 第 1 次 web_extract 失败 → 换一个 URL（GitHub README / PyPI / CRAN / Bioconductor）
   - 第 2 次失败 → 尝试搜索 "<包名> GitHub repository"
   - 第 3 次失败 → 标记 skill 为 "_UNVERIFIED_"，在 SKILL.md top 添加警告注释，
     并告知用户："官方文档无法获取，创建的 skill 可能不准确"
   - 任何时候失败 → 不允许凭记忆编造函数签名和参数
```

**Step 1 输出必须包含**（缺少任何一项 → 不允许进入 Step 2）：

| 输出项 | 说明 |
|--------|------|
| `extraction_timestamp` | 文档抓取时间 (ISO 8601) |
| `source_urls` | 成功抓取的官方 URL 列表 |
| `doc_version` | 文档版本号（如果有） |
| `api_functions` | 提取到的 API 函数名列表 |
| `parameter_table` | 函数名 → 参数名 → 类型 → 默认值 对照表 |

此表将用于 Step 9 的一致性比对。

### Step 2: 查询文献
```
Tool: search_papers_by_context + download_pdf + extract_params_from_pdf
- search_papers_by_context(species, tissue, direction, assay)
- 选 1-2 篇最相关的，download_pdf 下载
- extract_params_from_pdf 提取方法参数
- 提取：方法名、关键参数、参考引用
```

### Step 3: 生成 SKILL.md
```
Tool: write_file
- 按标准格式生成 SKILL.md（含 frontmatter + 7条强制规则 + 8章正文）
- frontmatter 的 name/description/tags 根据包功能填写
- Pipeline 步骤根据官方文档的教程填写
- Parameters 根据官方 API + 文献填写
- References 根据文献填写
- Proven Scripts 必须是有效空表格（见规则2.6），不可用纯注释
```

### Step 4: 生成 `skill.json`（**必须创建，不可跳过**）
```
Tool: write_file
- 写入同目录下的 skill.json，格式见规则2.5
- 这是 `skill_evolution(action="record_run")` 正确落盘的前提
- 不创建 → 后续所有 record_run 调用静默失败
```

### Step 5: 生成脚本模板
```
Tool: write_file
- scripts/run.py：含审查辩论铁律头 + 步骤注释 + TODO 参数区 + 主流程区 + 结果保存区
- scripts/reference_script.R 或 .py：含铁律头 + 完整函数实现（基于官方文档示例代码）
```

### Step 6: 注册到 skill 库
```
Tool: skill_manage
- skill_manage(action="create", name="<skill名>", content="<SKILL.md内容>")
- 脚本也通过 skill_manage(action="write_file")写入，不要用 write_file 直接写 skills 目录
- 注意：write_file 写入 skills 目录会触发安全扫描，含 injection 模式的内容会被阻断
```

### Step 7: 验证 skill 可加载
```
Tool: skill_view
- skill_view(name="<skill名>")
- 确认 success=true
- 确认强制规则块完整
- 确认脚本模板的铁律头完整
```

### Step 8: 🔴 注册到 SOUL.md 技能匹配表（必须执行，不可跳过）

> **这是 create-bio-skill 的强制步骤。新 skill 不注册到 SOUL.md，后续分析无法自动触发 skill_view。**

```
Tool: skill_evolution(action="register_skill")
1. 从 SKILL.md 的 When to Use / metadata.tags / 用户输入中提取关键词
2. 调用：
   skill_evolution(
     action="register_skill",
     skill_name="<skill名>",
     keywords='"关键词1" / "关键词2" / "关键词3"',
     trigger_level="RED 必触发",
     category="<分类标签>"
   )
3. 该 action 会自动将触发行写入 SOUL.md 的 AUTO_SKILL_INSERT_MARKER 上方
4. 验证：grep 'skill_view("<skill名>")' hermes_home/SOUL.md 应有输出
```

**关键词提取规则（🔴 硬门禁）**：
- 包名本身（如 `scTour`、`CellChat`）
- 功能短描述（如 `深度伪时间`、`VAE轨迹`）
- 从 SKILL.md 的 When to Use 和 metadata.hermes.tags 提取
- 用 ` / ` 分隔多个关键词
- **🔴 至少 4 个关键词（含中英文各至少 1 个）** — `_register_skill` 会程序化检查，不足 4 个 → 直接返回 `KEYWORD_GATE_FAILED`，**拒绝注册**
- **推荐 5-8 个关键词** — 太少会导致命中率低，下次用户换一种说法就触发不了
- **必须覆盖的 4 类关键词**：
  1. 包名/工具名（如 `scTour`、`SenCat`）
  2. 中文功能描述（如 `深度伪时间`、`衰老分类`）
  3. 英文功能描述（如 `VAE trajectory`、`senescence scoring`）
  4. 同义词/缩写/变体（如 `伪时间`=`拟时序`、`scoring`=`classification`）
- **系统自动扩展**：`_expand_keywords` 会自动从复合词派生短词（如 "衰老分类" → 追加 "衰老"、"senescence scoring" → 追加 "senescence"），并自动过滤通用停用词（"scoring", "细胞" 等），确保高命中率 + 低误报率

**🔴 交付前自检**：调用 `skill_evolution(action="register_skill")` 若返回 `KEYWORD_GATE_FAILED` → 回到本步骤补全关键词

### Step 9: 🔴 交付门禁（程序化阻断，不可跳过）

> **这是硬门禁。任何一项 ❌ → 不允许交付 skill。必须修正后重新过门禁，直到全部 ✅。**

```
Tool: skill_evolution(action="verify_delivery_gate")

1. 调用 skill_evolution(action="verify_delivery_gate", skill_name="<skill名>")
   该函数自动检查以下 6 项，返回 {"passed": True/False, "blocked": [...]}
2. passed=False → blocked 列表中的每一项必须修正 → 修正后重新调用 verify_delivery_gate
3. passed=True → 门禁通过，继续下一步

6 项自动检查清单：

1. 官网一致性检查
   - web_extract(urls=[官方API页面]) 重新拉取官方文档
   - 逐条比对：函数名、参数名、参数类型、默认值是否与 SKILL.md 和脚本中的一致
   - 输出：✅ 一致 / ❌ 不一致 + 差异列表

2. 文档/教程参考检查
   - 确认 Step 1 查询了官方教程/vignette/example 页面
   - 确认 References 中列出了官方文档 URL
   - 确认脚本模板中的代码参考了官方示例代码
   - 输出：✅ 已参考 / ❌ 未参考

3. 安装包完整性检查
   - check_env 检查 prerequisites 中列出的包是否可导入
   - 检查隐式依赖：在官方文档中搜索“requires”/“dependency”/“install separately”
   - 确认 Common Issues 中说明了隐式依赖
   - 输出：✅ 完整 / ❌ 缺失 + 缺失包列表

4. 使用场景说明检查
   - 确认 When to Use 包含「应该使用」和「不应该使用」两种场景
   - 确认有量化阈值（如最小细胞数、最小基因数、数据类型要求）
   - 输出：✅ 完整 / ❌ 不完整

5. 查询官网留痕检查
   - 确认 References 中有官方文档 URL
   - 确认有 web_search + web_extract 的调用记录
   - 输出：✅ 已留痕 / ❌ 未留痕

6. 🔴 SOUL.md 注册检查
   - `grep 'skill_view("<skill名>")' hermes_home/SOUL.md` 必须命中
   - 确认注册行格式正确、关键词完整
   - 输出：✅ 已注册 / ❌ 未注册 → 调用 skill_evolution(action="register_skill") 补救

6 项全部 ✅ → skill_evolution(action="record_run", notes="审核通过")
有 ❌ → 修正后重新审核该项
```

---



### Step 10: 🆕 首次使用自进化（skill 创建后的经验累积）

> **新 skill 创建后，必须在首次分析使用后收集经验，否则 skill 永远没有 proven_params。**
> 这是 create-bio-skill 区别于普通 skill 创建工具的核心能力。

```
Tool: skill_evolution(actions) + memory_bridge

首次分析完成后（skill 被实际执行用于分析）：
1. skill_evolution(action="record_run", skill_name="<skill名>", ...)
   → 将成功运行记录追加到 SKILL.md Proven Scripts 表
   → 自动触发 memory_bridge.store_script_score() 写入 holographic 外置记忆

2. 询问用户："这次分析结果满意吗？(1-10 分)"
   → 用户打分 → memory_bridge.record_feedback(fact_id, helpful=True/False)
   → 影响 trust_score，后续 _query_logs 按 trust_score 排序返回

3. 如果用户提供了自定义脚本（放在 figure_scripts/ 或 user_scripts/）
   → skill_evolution(action="record_run", custom_script=True)
   → memory_bridge.store_script_score(approved=True) 标记为用户认可

4. 自进化检查：
   - 是否有参数需要调整？→ _record_success(params_used=...) 记录优化参数
   - 是否有新的错误模式？→ _record_error(...) 记录到 error_log.md
   - 是否有新的经验？→ memory_bridge.store_skill_exp(...) 写入外置记忆

5. 验证经验跨会话持久化：
   - 关闭当前会话 → 新开会话
   - skill_evolution(action="query_logs", skill="<skill名>")
   - 确认返回的 proven_params 和 holographic 结果一致
```

**Step 10 目的**：确保 create-bio-skill 创建的 skill 不是"空壳"——首次使用后立即积累经验，
下次再被调用时 _query_logs 能返回历史经验，形成正向循环。

---


### Step 10: 首次使用自进化

> **新 skill 创建后首次用于分析 → 必须收集经验。否则 skill 永远是空壳。**

```
1. skill_evolution(action="record_run", skill_name="<name>", ...)
   → 追加 Proven Scripts → 自动写 holographic 外置记忆
2. 询问用户满意度 (1-10) → memory_bridge.record_feedback()
3. 用户自定义脚本？→ record_run(custom_script=True, approved=True)
4. 自进化检查: 参数调整? 新错误? 新经验? → store_skill_exp()
5. 验证: 新会话 → query_logs → 确认经验可召回
```

## SKILL.md 模板

新建 skill 的 SKILL.md 必须按以下模板生成（`<...>` 为占位符）：

```markdown
---
name: <skill-name>
description: "<一句话描述功能+触发场景>"
version: 1.0.0
author: MemOmics (auto-created)
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [<功能标签>, <测序类型>, <分析步骤>]
    difficulty: <beginner/intermediate/advanced>
    language: <R/Python/R+Python>
    category: <transcriptomics/epigenomics/spatial/proteomics/meta>
prerequisites:
  r_packages: [<R包列表>]
  python_packages: [<Python包列表>]
related_skills: [<相关skill>]
---

## ⛔ MemOmics 强制规则（不可违反，优先级最高）

> 本 skill 已集成到 MemOmics-Agent 自进化生信分析平台。使用本 skill 前，必须先通过 skill_view 加载本文件。以下规则覆盖所有默认行为。

### 规则1: 写代码前 → 必须先 search_knowledge + skill_view
- **每个分析步骤写代码前**，必须先调 `search_knowledge(species=..., tissue=..., direction=..., query="<步骤名> 参数")`
- 知识库有匹配 → 用知识库的参数和模板
- 知识库无匹配 → 用 search_papers_by_context 搜文献，提取方法和参数，存入知识库
- **绝对不能跳过直接写代码**

### 规则2: 8步循环（每步必须走完整循环）
```
1. search_knowledge 查本步骤的方法和参数
2. skill_view 加载本 SKILL.md（获取脚本模板+审查规则+参数范围）
3. check_env 检查环境（缺包自动安装）
4. rail_review(pre) 前置审查（参数合理吗？包齐了吗？数据准备好了吗？）
5. 写这一步的代码（基于 skill 模板，只写这一步，不写后续步骤）
6. terminal 执行（分步执行，禁止 && 连接多步骤）
7. debate_analysis 多方辩论（正方/反方切断上下文独立生成 + LLM裁决）
8. rail_review(post) 后置审查（图有没有？结果合理吗？跟知识库对应吗？）
```

### 规则3: 代码分段执行 — 写一步跑一步
- ❌ **禁止**一次性写完全部代码用 && 连接执行
- ✅ **必须**分步：写一步 → 执行 → 检查结果 → 辩论 → 下一步

### 规则4: 关键参数多参数尝试 + 辩论
- 涉及数值参数时，**至少尝试 2-3 个值**
- 每次参数变更后调 `debate_analysis` 辩论"这个参数合理吗？结果有没有变好？"
- 辩论格式（多角色对抗 v3）：
  - 正方 3 位专业编辑（各自独立，互相不知道）：生物学编辑 / 统计学编辑 / 生信编辑
  - 反方 4 位专业编辑（各自独立，互相不知道，也看不到正方）：生物学编辑 / 统计学编辑 / 生信编辑 / 历史经验编辑
  - 裁判编辑：看到所有 7 方论点，给出裁决 + 置信度（高/中/低）
  - 上下文隔离：每个编辑独立 HTTP API 调用，messages 只有自己的 prompt
  - 分科知识库：生物学编辑用 biology_kb / 统计学编辑用 statistics_kb / 生信编辑用 bioinfo_kb / 历史经验编辑用 history_errors
  - 辩论结果自动归档到 results/.../log/debate_*.json
- **不确定的参数就辩论**，不要自己拍脑袋
- **辩论最多 3 轮**：3 轮后选最优参数结果

### 规则5: 执行后审查（强化版）
- 每步执行完调 `rail_review(post)` 审查，审查内容**全部强制**：
  - **图片检查**：
    - 图有没有生成？没生成 → 强制重新执行
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

### 规则N: 运行记录只是参考，不能跳过审查
- skill_evolution(action="query_logs") 返回的历史运行日志仅供参数参考
- 即使有 quality_score=9.0 的历史日志，仍必须执行 rail_review(pre)、debate_analysis、rail_review(post)
- 禁止因"之前跑过"而跳过任何审查步骤
- 禁止直接用历史日志里的脚本运行而不经本次审查
- 运行日志是"参考"不是"免审凭证"

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

# <分析步骤标题>

<功能概述>

## When to Use
<触发场景>

## Pipeline
<每步标注 Tool: terminal>

## Parameters
<关键参数 + 默认值 + 来源>

## Proven Scripts

> 经实际运行验证成功的脚本记录。`skill_evolution(action="record_run")` 自动追加至此表。

| 物种 | 组织 | 方向 | 日期 | 质量评分 |
|:----|:----|:----|:----:|:--------:|
| <!-- 首次运行后自动填充 --> | | | | |

## Common Issues
<常见问题>

## References
<文献引用>

---

## ⛔ Terminal 完成后强制协议（铁律 26 · 新 skill 模板自带）

```
1. rail_review(phase='post')
2. debate_analysis(topic="{分析描述}", context="参数+结果", knowledge_base_info=<KB>)
3. save_conclusions(module="{模块}", topic="{分析名}", ...)
   → 写入 {module}/conclusions.md + conclusions.json
4. skill_evolution(action="record_run")
5. 更新 task_plan.md
```

⛔ 创建新 skill 时，此协议块自动包含在 SKILL.md 末尾。
```

---

## 脚本模板

### R 脚本模板（scripts/run.py / reference_script.R）

新建 skill 的脚本必须在开头包含以下铁律头：

```r
# ============================================================
# 🔒 MemOmics 审查与辩论机制 + 自进化日志
# ============================================================
# 此脚本由 MemOmics Agent 执行。原脚本永远不被修改。
#
# 执行前必须:
#   1. rail_review(action="pre")  — 检查环境/参数/数据
#   2. skill_evolution(action="query_logs", script_name="本脚本名",
#      species="物种", tissue="组织", direction="方向")
#      → 查同类运行日志，有则参考已有参数和经验，无则按原脚本执行
#   3. debate_analysis(topic, context) — 参数不确定时多角色辩论
#
# 执行后必须:
#   1. rail_review(action="post") — 检查输出/质量/图表
#      ★ 强制审查项（任一不通过则重新执行）:
#        a. 图片是否生成？无图 → 重新执行
#        b. 图片是否空白（全白/全黑/全单一色）？空白 → 强制重新出图
#        c. 图片是否有 NA/缺失值（>10%像素是NA）？有NA → 强制重新出图
#        d. 图片大小是否过小（<5KB）？过小 → 强制重新出图
#        e. 图片数量是否足够？（每步至少1张图，关键步骤至少2-3张）
#        f. 代码行数是否合理？是否分段执行（禁止&&连接）？
#        g. 数值范围是否合理？跟知识库对应吗？
#   2. 如果通过 → skill_evolution(action="record_run",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", params_used="参数JSON", result_summary="结果",
#      quality_score=8, notes="经验总结")
#      → 记录成功运行日志，供后续同类型分析参考
#   3. 如果失败 → skill_evolution(action="record_error",
#      script_name="本脚本名", species="物种", tissue="组织",
#      direction="方向", error_message="报错", root_cause="根因",
#      fix_applied="修复方案")
#      → 记录错误日志，修正后重跑
#
# ★ 参数和结论辩论铁律:
#   - 有参数选择 → 必须调 debate_analysis 辩论
#   - 有结论输出 → 必须调 debate_analysis 辩论
#   - 辩论格式：正方(支持) vs 反方(质疑+替代) → 裁判决断
#   - 最多3轮，3轮后选最优结果
#
# 日志存储: skill 目录下 .run_logs/ 目录，按 物种_组织_方向_日期 命名
# ============================================================

# ============================================================
# 🔒 MemOmics 审查铁律 — 执行本脚本前后的强制步骤
# ============================================================
# 执行前必须: rail_review(action="pre")  — 环境检查 + 参数校验 + 代码审查
# 执行后必须: rail_review(action="post") — 结果质量评估 + 图表检查 + 数值检查
#   ★ 强制: 图片空白/NA/过小 → 重新出图 | 图片不够 → 补图 | 代码未分段 → 重写
#   ★ 强制: 有参数有结论 → debate_analysis 辩论
# 参数有争议: debate_analysis(topic=..., context=...) — 多角色辩论
# 执行失败:   skill_evolution(action="record_error") — 记录错误
# 修复成功:   skill_evolution(action="update_script") — 替换脚本
# ============================================================
```

### Python 脚本模板（scripts/run.py / reference_script.py）

同样的铁律头，用 `#` 注释格式（与 R 相同）。

---

## Parameters

| 参数 | 说明 |
|------|------|
| 包名 | 用户指定的包名或从分析需求推断的包名 |
| 官方文档 URL | web_search 搜索结果中官方文档的 URL |
| 物种/组织/方向 | 从 update_results_dir 获取，用于文献搜索 |
| 测序类型 | RNA/ATAC/spatial/bulk，决定 skill 的 category |

## 📦 R 包安装规则：GitHub 包统一用 `pak`

> 🆕 2026-07-14: 用户明确要求 R GitHub 包安装优先使用 `pak::pak()`。
> `pak` 已在系统预装 (v0.9.4)，比 `remotes::install_github()` 更快更稳，使用不同的 GitHub API 策略可绕过某些网络限制。

**规则**：所有 GitHub R 包安装必须使用：
```r
pak::pak("user/repo")           # 替代 remotes::install_github("user/repo")
pak::pak("user/repo@branch")    # 指定分支
pak::pak("user/repo@v1.0")      # 指定版本
```

**禁止**使用 `remotes::install_github()`（除非 pak 不可用）。

**创建的新 R skill** 的 `prerequisites` 部分和安装指令中必须使用 `pak::pak()` 语法。

## Common Issues

1. **web_search 搜不到官方文档** → 尝试搜 GitHub 仓库 + Bioconductor/CRAN/PyPI 页面
2. **skill_manage create 失败** → 检查错误信息，修复后重试 skill_manage；不要用 write_file 直接写 skills 目录（会触发安全扫描阻断）
3. **创建后 skill_view 找不到** → 检查目录名和 SKILL.md frontmatter 的 name 字段是否一致
4. **包不存在于 CRAN/Bioconductor/PyPI** → 搜 GitHub，如果确实不存在则告知用户
6. **🔴 KEYWORD_GATE_FAILED** → `_register_skill` 返回关键词不足的错误。原因：提取的关键词少于 4 个。修复：回到 Step 8，补充中英文关键词，至少覆盖：包名/中文描述/英文描述/同义词 四类。
7. **🔴 DELIVERY GATE FAILED** → `_verify_delivery_gate` 返回 blocked 列表。逐项修正：缺官方 URL → 补 References；缺脚本 → 生成 scripts/run.py；缺 skill.json → 按 Rule 2.5 创建；缺 Proven Scripts 表 → 按 Rule 2.6 补全。修正后重新调用 verify_delivery_gate。
8. **🔴 首次使用后 query_logs 返回空** → 确认 Step 10 已执行 record_run + record_feedback。确认 skill.json 存在且有 proven_params 数据。
5. **KEYWORD_GATE_FAILED** -> `_register_skill` 拒绝注册 (<4 关键词)。回到 Step 8 补全 4 类关键词。
6. **DELIVERY GATE FAILED** -> `_verify_delivery_gate` blocked。逐项修正后重试。
7. **首次使用后 query_logs 返回空** -> 确认 Step 10 已执行 + skill.json 存在。
8. **skill_evolution record_run 静默失败** → `record_run` 返回 "Success recorded" 但数据未落盘。检查：`skill.json` 是否存在？SKILL.md 是否有有效的 Proven Scripts 表格？两者缺一都会导致 `_record_success` 写操作被 `try/except pass` 吞掉。修复方法：创建 `skill.json` 并补全 Proven Scripts 表，然后手动归档到 `results/.../log/run_record_*.json`。

## References

- BioMinI skill 格式规范（基于 275 个现有 skill）
- MemOmics 强制规则 v2.0（7 条规则 + 强化版审查）
- `references/cuttag-analysis-tools.md` — CUT&Tag 生信工具链文献调研 (2026-07-14)，供未来创建 CUT&Tag skill 使用
