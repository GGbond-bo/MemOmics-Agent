---
name: competitor-agent-research
description: "调研/对比其他科研 AI Agent（Biomni/BiOmics 等）的能力与架构。触发词：'XX agent 差距'/'调研一下 XX 的能力和架构'/'竞品分析'/'biomini'/'Biomni'/'BiOmics'。方法论：身份确认→GitHub API 源码调研→论文 PDF 提取→能力/架构双维对比。"
when_to_use: "[competitor-agent-research] 用户问自己(MemOmics)与另一个科研/生信 AI Agent 的差距，要求从能力和架构上调研对比"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [agent-research, competitor-analysis, benchmark, 竞品分析, 能力对比, 架构对比]
    difficulty: medium
    language: Python
    category: Research
prerequisites:
  r_packages: []
  python_packages: [pypdf]
---

# 竞品科研 AI Agent 调研

用户要求调研/对比 MemOmics 与其他科研 AI Agent（如 Biomni、BiOmics）在**能力和架构**上的差距。
本 skill 提供可复用调研方法论 + 已调研竞品的知识库。

触发提示: "XX 和我的差距" / "调研一下 XX" / "能力和架构" / "竞品" / "biomini" / "Biomni"

## 调研流程（5 步）

### Step 1 — 身份确认（必做，防止音译歧义）
用户口述产品名常是模糊音译（"biomini" = Biomni）。先 web_search 中英文各一轮 + search_papers，
确认: 官方名 / 团队 / 论文(期刊+年份) / GitHub repo。**拿不到准确身份前不要写对比结论**。

### Step 2 — GitHub API 优先（git clone 常失败）
本机 git clone github.com:443 常连不上（2026-08 实测），但 **api.github.com 和 raw.githubusercontent.com 用 curl/urllib 可通**。
用 Python urllib + retry 抓:
1. `api.github.com/repos/<owner>/<repo>` → default_branch, stars, description
2. `api.github.com/repos/<owner>/<repo>/git/trees/<branch>?recursive=1` → 完整文件树（看模块划分、工具清单、协议库）
3. `raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>` → 逐个拉源码文件

### Step 3 — 论文 PDF 直接下载 + pypdf 提取
官方站点常有 paper.pdf。urllib 下载后 pypdf 提取全文，用关键词切片定位关键段落
（如 "150 specialized tools" / "ablation" / "outperformed"）。**数字和对比结论必须从原文提取，不能凭记忆**。

### Step 4 — 源码结构反推架构（比读论文快）
对 agent 主文件（可能 100KB+）用 regex 提取:
- `class \w+` → 核心类
- `def \w+` → 方法清单（架构特征一目了然: retriever/self_critic/plan/execute/memory/verif）
- 关键词计数 → 判断机制是否存在（如 self.critic=27次 → self-critic 是核心机制）

### Step 5 — 能力 vs 架构双维度对比（交付格式）
- **能力层**: 对方有的我有没有（工具数/数据库数/基准成绩/任务类型/交付物）；我有的对方有没有（长任务/发表级出图/自进化/多角色辩论）
- **架构层**: 环境(工具+软件+数据库) / 规划(模板驱动 vs 代码为中心) / 执行 / 质量控制 / 学习机制 / 编排框架
- 交付要求: 一句话定位差异本质（"他赢在广度和可验证，我赢在深度和落地"）→ 能力对照表 → 架构对照表 → 追赶优先级列表
- 引用来源标注（Science 论文/官网/GitHub/PubMed），用户会验证

## 工具陷阱（本机实测）

| 陷阱 | 现象 | 修复 |
|------|------|------|
| execute_python 的 /tmp ≠ bash 的 /tmp | execute_python 写 `/tmp/xxx` 后 bash `ls /tmp` 看不到 | 直接写显式路径（如 `MEMOMICS_HOME/results/<session>/`）再 read_file |
| web_extract 后端不可用 | DuckDuckGo search-only 后端无法 extract URL | 用 execute_code 内 hermes_tools.web_extract 或 urllib 直接抓 |
| git clone 失败 | github.com:443 连接超时 | 改用 GitHub REST API（api.github.com 通） |
| terminal 中 rm -rf 被拦截 | 安全护栏拦截删除 | 克隆到新目录名，不要 rm 旧目录 |

## Support Files
- `references/biomni-knowledge-bank.md` — Biomni (Science 2026) 架构/基准/与 MemOmics 对比知识库

## Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| 用户产品名音译歧义 | "biomini" 实为 "Biomni" | Step 1 身份确认，中英文各搜一轮 |
| 调研产出被质疑 | 结论无原文数字支撑 | 数字必须从论文 PDF / 源码提取并标注来源 |

## References

- Source: MemOmics built-in (2026-08-05, Biomni Science 2026 调研会话沉淀)
- Category: Research
