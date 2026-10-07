---
name: memomics-internals-qa
description: "回答关于 MemOmics 自身机制/能力的问题（能做什么、辩论何时触发、L0/L1/L2、上下文隔离是代码层还是提示词、知识库怎么保证可靠、怎么自进化、边界在哪）时的实证方法学。触发：『MemOmics 能做什么』『你们的设计初衷』『辩论什么时候触发』『L0 L1 L2』『隔离怎么实现的』『知识库怎么建的』『你们的边界』『你自己审计一下』『这套东西真的在用吗』。核心：源码优先、file:line 取证、区分『自述 vs 实现』、诚实边界。"
when_to_use: "用户要求解释/评估 MemOmics 平台自身的设计、机制、门控、知识库、自进化或能力边界时。也用于给外部做平台介绍/汇报前的事实取证。⛔ 不要凭 SOUL.md 自述复述作答——那会被当场识破。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [self-audit, platform, internals, evidence, memomics]
    difficulty: medium
    language: Python
    category: bioinformatics
---

# MemOmics 机制问答（源码取证版）

用户会直接问「**辩论什么时候触发？L0/L1/L2 分别什么场景？L1 的上下文隔离是代码层吗？**」
「**你自己能做什么？设计初衷是什么？怎么解决的？**」「**这套东西真的在用吗？**」

这类问题只有一种正确答法：**回到磁盘和源码实证，再开口。**

## 一、铁律：源码优先，禁复述自述

| ❌ 错误答法 | ✅ 正确答法 |
|---|---|
| 复述 SOUL.md / README 的自我描述 | `read_file` / `search_files` 读实现，给出 **file:line** |
| 凭印象报数字（「我们有几百个 skill」） | 现场统计（索引条数 / 磁盘文件数），报**精确值 + 出处** |
| 只说设计意图 | 同时说**实现现状**（自述 vs 实现的差距） |
| 把「文档写了」当「代码做了」 | 找到拒绝分支/门禁代码才算数 |

> 用户会追问「**你看过原代码吗？别乱说**」。取证顺序反了会被当场质疑。

## 二、机制地图（哪个文件实现什么）

| 机制 | 实现位置 | 说明 |
|---|---|---|
| 辩论门控 L0/L1/L2 | `webui/enforcement.py::debate_gate()` | 读 analysis_level + stage + signals |
| 上下文隔离 | `memomics/bio_tools/debate_analysis.py::_call_llm_sync()` | 每角色一次独立 HTTP 调用 |
| L1 轻量采样 | 同上 `_debate_l1_lightweight()` | 同模型 + 温度池 |
| 知识库证据铁轨 | `memomics/bio_tools/save_knowledge.py` | 工具层拒绝写入 |
| 技能路由 / 注册表 | `webui/skills_registry.py` + `hermes_home/SKILLS_INDEX.md` | RED/YEL/GRN 触发级别 |
| 执行门禁（意图确认） | `webui/enforcement.py::arm_intent_confirm` / `set_awaiting_form` | 服务器层硬拦 |
| 自进化运行账本 | `skill_evolution` → `results/<sid>/log/run_record_*.json` | 原脚本永不修改 |
| 长任务包装器 | `memomics/bio_tools/task_run.py` | 面板可见 / 可取消 |

## 三、已实测的关键事实（2026-10，可直接引用）

### 3.1 门控与隔离

- **门控在代码层**：`debate_gate(es, stage, signals)` → `(level, reasons, force)`。
  硬信号（高影响 / 重试≥2 / 冲突 / 报错）**优先且不可降级**。
- **L0 有 8 条明确判据**：chat·lightweight 级 / 显式 `no_debate` / **活选项<2** /
  事实查询 / 只读观察 / 同议题已辩过 / 线性执行 / 匹配线性命令正则。
- **隔离是代码层物理切断**：每个角色一次独立 HTTP 调用，
  `messages: [{"role":"user","content":prompt}]` 只含它自己的 prompt，
  返回带 **`isolation_verified: True` + `messages_count: 1`** 可断言凭证。
  ⛔ 不是「同对话里说『你现在扮演反方』」那种提示词层角色扮演。
- L1 = 同模型 + **温度梯度**（`_TEMP_POOL`，反方 +0.1）+ 默认 `samples=3` ×
  正反各 1 次 + 1 次裁判（裁判前先做「裁判整理」digest）。

📖 行号级判据表与汇报话术 → `references/gating-and-isolation-implementation.md`

### 3.2 知识库

- **三道证据铁轨**（`save_knowledge.py`，工具层**拒绝写入**，非文档建议）：
  ① `verified=unverified` → 拒（force 仅限 bootstrap）
  ② `data_driven` / `domain_convention` **无 evidence** → 拒
  ③ 名称/分类含非法字符、路径非法 → 拒（防路径穿越）
- **五级目录**：`物种 / 组织 / 方向 / 类别 / assay`，作用是**防参数跨组织串味**
  （实测骨骼肌与人海马的 QC 阈值不同）。
- **闭环**：分析产出 → 带证据回写 → 下次检索复用 → **辩论时再被引为论据**
  （`debate_analysis` 的 `auto_kb=True` 按物种+组织+方向自动注入）。
- **检索**支持中英文语义映射（人/人类/患者 → Homo_sapiens）。

📖 铁轨代码取证与构成分析 → `references/kb-evidence-rails.md`

### 3.3 规模数字（必须现场统计，别背）

```bash
# 技能数：读索引而不是猜
read_file("hermes_home/SKILLS_INDEX.md")        # 表头含 RED/YEL/GRN 计数
# 磁盘 SKILL.md 数
search_files(target="files", pattern="SKILL.md")
# 运行账本 / 辩论归档 / 结果会话
search_files(target="files", pattern="run_record_*.json")
search_files(target="files", pattern="debate_*.json")
```

> 报数字时必须区分**口径**：索引登记条数 ≠ 磁盘文件数 ≠ 经真人验证的数。
> 例：索引 388 条 vs 磁盘 476 个 SKILL.md —— 两个数字都对，但含义不同，要说清。

## 四、诚实边界（必须主动说，别等用户抓）

这是**审自己**，与「对比页只说优点」是两回事：

| 边界 | 说法 |
|---|---|
| 原创层次 | 建在 Hermes 框架之上；**真正的原创在 enforcement / skills_registry / skill_evolution / KB 铁轨 四层** |
| 技能含金量不均 | 索引 388 条不代表 388 条都经真人验证；相当一部分由 `create-bio-skill` 自动生成 |
| 形式校验 ≠ 科学校验 | rail_review 验「文件在不在、非空、代码完整」，**验不出统计口径选错**（如把技术重复当生物学重复算 log2FC） |
| 知识库证据质量 | 铁轨拦得住「空手入库」，拦不住「证据质量差」——实测有条目 evidence 字段填的是运行日志行，不是文献引用 |
| 文献知识体量 | 需现场统计 `paper_*` 与 `*_empirical` 占比，别把自进化日志混算成文献知识 |
| 辩论是同模型多角色 | 不是真异构，能抓明显方法学错误，**抓不到同源偏差** |

## 五、发言纪律（两个场景别搞混）

| 场景 | 要求 |
|---|---|
| **对比他人方案**（Biomni / Paper2Agent / BioMaster / Co-Scientist 等）的汇报页 | 用户明确要求「**不要说缺点，说优点**」→ 只列设计初衷/解法/工作量 |
| **被问「你自己的边界/能做到什么」** | **必须给诚实边界**（§四）——用户要的是可审计自评，不是自夸 |

⛔ 不要把「对比页只说优点」错误泛化成「审自己也不说缺点」。

## 六、交付形式

- 机制对比/介绍 → 通常要 **`.pptx` + `.html` 双版本**（见 `interactive-html-deliverables` §七）。
  用户对这类 deck 的硬要求：**表格优先、页内极简、逐页指定结构**。
- 纯文字答疑 → 结论先行，配 **dsh-ui 表格**（方案对比）或 **mermaid**（流程类）。
- 流程类内容（分析管线 / 机制链路）→ 默认出 **mermaid 流程图**放解释文字**前面**。
- 数字一律带出处（`file:line` 或命令），用户会抽查。

## Support Files

- `references/gating-and-isolation-implementation.md` — `debate_gate()` 行号级判据表（L0 八条跳过 / L1 / L2 触发条件 / 预算降级）、L1 温度池采样与裁判整理、**隔离的代码证据**、对外汇报话术模板
- `references/kb-evidence-rails.md` — 三道证据铁轨的源码取证（行号 + 拒绝分支）、五级目录与三知识域、规模构成统计口径、证据质量边界