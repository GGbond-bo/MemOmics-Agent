---
name: literature-tracking-engine
description: |
  建/跑「文献追踪库」：多源零 key 检索（Europe PMC / PubMed / OpenAlex）→ 跨源合并去重 → 骨架词硬门槛 + 排除词过滤
  → 跨运行去重索引 → 六维打分（LLM）→ 日报 + A-E 分类笔记 + 可审计运行记录。
  自带可复用引擎 scripts/lit_track.py（无 MCP、无 cron、纯标准库 + PyYAML），适合「每天/每周帮我盯这个方向的新文献」
  「先做一次建库 + 本次检索」「别真的挂定时任务」这类需求。
category: research
when_to_use: "[literature-tracking-engine] 用户要建文献追踪/每日文献筛选/文献库，或要一次性检索并沉淀成库（含日报与笔记）。触发词：文献追踪、建文献库、每日文献、每天过一遍新文献、跟踪这个方向的新文章、文献筛选建库。"
trigger_level: RED
trigger_keywords: ["文献追踪", "建文献库", "每日文献", "每天过一遍新文献", "跟踪新文献", "literature tracking", "daily literature", "文献筛选建库"]
metadata:
  hermes:
    tags: [research, literature, tracking, multi-source, scoring, no-cron]
    related_skills: [nature-literature-pipeline, nature-academic-search, paper-download, literature-review]
---

# Literature Tracking Engine

把「帮我盯住某个方向的新文献」做成一个**可重复跑的本地库**：检索 → 过滤 → 打分 → 日报 → 归档，
而不是每次手搓一次性检索脚本。

> 与 `nature-literature-pipeline` 的分工（两者互补，不是替代）：
> 那个技能给的是**方法论与模板**（打分体系、推送格式、笔记模板、cron 说明，偏飞书/MCP 场景）；
> 本技能给的是**可直接运行的本地引擎**（无 MCP、无 cron、零 API key），并在 `references/` 里记录了真实源坑。

## 触发场景

| 用户说 | 动作 |
|--------|------|
| 「帮我建个文献追踪，每天把新文献过一遍」 | 建库（config + 目录 + 索引）→ 跑一次检索 → 产出日报/笔记 → 交付**未启用**的 cron 提示词 |
| 「先做一次建库 + 本次检索，别真的挂定时任务」 | 同上，**绝不注册 cronjob**；启用命令写进 `<library>/cron_prompt.md` 等用户确认 |
| 「看看这个方向最近有什么新文章」 | 只跑 `search`（回溯 7-120 天）→ 交付候选清单（不建库时可只在会话里返回） |
| 「上次那个文献追踪库再跑一次」 | `search --days 7` → 打分 → `digest`（`index.json` 自动跳过已见文献） |

## 库结构（每个主题一个库目录）

```
<library>/
├── config.yaml            研究画像 / 多查询词 / include·exclude·must_match / 六维权重 / 通道设置
├── index.json             跨运行去重索引（doi: / pmid: / t:归一化标题 → 首见日期+分数+分类+笔记路径）
├── runs.jsonl             每次运行的可审计记录（候选数、精读数、产物路径、源错误）
├── cron_prompt.md         每日任务提示词 + 启用命令（**默认不启用**）
├── scripts/lit_track.py   引擎（可从本技能 scripts/ 直接调用，不必复制）
├── raw/                   <日期>_candidates.json / <日期>_scored.json / <日期>_digest.md
├── notes/                 A_核心主线 B_章节支撑 C_工程背景 D_方法借鉴 E_暂存低优先（五类目录名不得简写）
└── log/                   检索日志（引擎启动时自动创建）
```

## 运行方式

```bash
cd <library>                                  # 引擎默认 root = 当前目录（也可 export LIT_TRACK_ROOT=<library>）

# 1) 检索：首次建库用大窗口，日常用小窗口
python <skill>/scripts/lit_track.py search --days 120 --pool 30     # 首次建库（拉基线）
python <skill>/scripts/lit_track.py search --days 7   --pool 30     # 日常（跨运行自动去重）

# 2) 打分（LLM 的活）：读 raw/<日期>_candidates.json → 写 raw/<日期>_scored.json
#    只需打分维度 + tier；top 篇另补 takeaway/methods/key_results/commentary/tags/note_sections

# 3) 出日报 + 笔记 + 更新索引
python <skill>/scripts/lit_track.py digest --date <YYYY-MM-DD> --top 5
python <skill>/scripts/lit_track.py status
```

产出：`raw/<日期>_digest.md`（日报）、`notes/<tier>/<Author><Year>_<关键词>.md`（笔记）、
`index.json` / `runs.jsonl` 更新。

## 六维打分（0-100，打分是 LLM 的事，引擎只做校验）

| 维度 | 上限 | 度量 |
|------|:----:|------|
| topic | 35 | 与核心研究问题契合度（**<10 直接否决**） |
| method | 20 | 方法学价值（实验设计 / 分析技术） |
| journal | 15 | 期刊/来源质量 |
| network | 10 | 关注作者/机构相关度（不是名气） |
| applied | 10 | 实用价值（protocol / 数据集 / benchmark） |
| archival | 10 | 长期存档价值（综述性 / 奠基性） |

展示为 `⭐ 总分/10`。引擎会**校验各维上限并重算总分**（防打分虚高），并打印被截断的维度告警。
跑 2-3 次后校准：top 长期 90+ → 过松；没有一篇过 60 → 关键词太窄。

## 过滤链（三道，缺一道就进噪声）

1. `must_match_any` 骨架词硬门槛：标题+摘要必须命中 `skeletal muscle` / `satellite cell` / `sarcopenia` …
   —— 只靠 include/exclude 词表挡不住跨领域串味（实测：巨噬细胞社论、重症肌无力综述、高原鱼类 small RNA
   都会因为出现 `muscle` / `骨骼肌无力` 被召回）。
2. `exclude` 排除词（cardiac / smooth muscle / drosophila / zebrafish …）+ `strong_keep` 白名单豁免。
3. `index.json` 跨运行去重（doi → pmid → 归一化标题 三键）。

## 交付偏好（本用户，实测）

- **默认不挂 cron**。用户说「别真的挂定时任务」时：交付「库 + 本次检索 + 启用说明」，把
  `cronjob(action="create", ...)` 命令与 prompt 写进 `cron_prompt.md`，等用户点头再挂。
- 汇报用中文，先给结论再给路径：候选数 → 精读数 → top 5（标题 / 期刊 / ⭐ / 分类）→ 产物路径 → 下一步建议。
- 源失败**照实报**（`candidates.json.errors`），不隐藏、不编造命中数。
- 首跑要把「进了候选池但被门控否决的噪声样本」单列出来并给排除词建议 —— 用户会关心词表怎么调。
- ⛔ 纯检索/只要清单的场景（用户说「只做检索/不做分析/不用再问」）：零文件、零入库，只回 Markdown 清单。

## 反模式

- ❌ 把「追踪」做成一次性检索脚本 → 下次用户说「再跑一次」就得重写。用引擎 + 持续累积的 config/index。
- ❌ 只检索不建索引 → 每跑一次都重复推送同一批经典文献。
- ❌ 让引擎替 LLM 打分（或让子代理打分不复核）→ 分数虚高、维度超上限。引擎只校验，不复算语义。
- ❌ 用户没明确要定时就自动注册 cronjob。
- ❌ 把日报/笔记写进知识库或 wiki（默认 `write_wiki: false`，只写 `raw/` 与 `notes/`）。

## 支持文件

| 文件 | 用途 |
|------|------|
| `scripts/lit_track.py` | 引擎本体：`search` / `digest` / `status` 三个子命令，纯标准库 + PyYAML，零 API key |
| `templates/literature-track-config.yaml` | 配置模板（换主题只改这个文件，不动代码） |
| `references/multi-source-search-quirks.md` | 三个源的检索语法与真实坑（PubMed 参考文献 DOI 陷阱、Europe PMC 日粒度过滤、OpenAlex 倒排摘要、元数据漂移兜底） |