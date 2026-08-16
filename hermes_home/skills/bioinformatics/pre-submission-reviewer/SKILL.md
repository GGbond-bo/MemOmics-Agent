---
name: pre-submission-reviewer
description: "投稿前审查：以审稿人视角在投稿截止前对论文做五维全面体检（宏观逻辑/写作细节/英语语法/LaTeX格式/图表质量），CRITICAL/MAJOR/MINOR 分级 + 逐条改写建议 + AI腔禁用词与破折号检查。触发词：投稿前审查、投稿前检查、投前审、预审、查草稿、proofread、找问题、语法检查、图表质量"
when_to_use: "[pre-submission-reviewer] 论文已写完、临近投稿（1周内），需要投稿前全面体检时使用。路由纪律：nature-reviewer 判科学质量（Nature五轴：原创性/重要性/技术严谨性，用户说'Nature预审/预审科学质量'走它），academic-paper-reviewer 是模拟完整同行评审（用户说'审稿/模拟审稿人'走它），本技能只做写作/格式/语法/图表的机械体检（用户说'投稿前审查/查草稿/找问题/语法检查'走本技能）。"
trigger_keywords: ["投稿前审查", "投稿前检查", "投前审", "查草稿", "检查草稿", "投稿前体检", "找问题", "proofread", "check the draft", "find issues", "语法检查", "图表质量", "AI腔"]
trigger_level: YEL 讨论触发
metadata:
  version: "1.0.0"
  last_updated: "2026-08-16"
  status: active
  data_access_level: verified_only
  task_type: open-ended
  related_skills:
    - academic-paper-reviewer
    - academic-paper-writing
---

# Pre-Submission Reviewer（投稿前审查）

> 源自 [HKUSTDial/Supervisor-Skills](https://github.com/HKUSTDial/Supervisor-Skills)（CC BY-NC-SA 4.0），按 MemOmics 技能规范适配。

## 定位

投稿截止前 3–7 天，做一次以审稿人视角的全面体检。对全文或关键章节输出**五维结构化审查**：每个发现带严重级别（CRITICAL / MAJOR / MINOR）+ 具体改写建议。

## 五维审查

1. **宏观逻辑** — 论证链是否完整、贡献是否立得住、每段是否有主题句。详见 `references/logic-and-structure.md`
2. **写作细节** — 各章节（摘要/引言/方法/结果/讨论）的段落纪律与引用格式统一。详见 `references/section-guides.md`
3. **英语语法** — 非母语作者高频错误：冠词、主谓一致、时态一致、which/that、中式表达。详见 `references/grammar-rules.md`
4. **LaTeX 格式** — 引号/破折号/公式/引用命令/图表浮动体规范。详见 `references/latex-rules.md`
5. **图表质量** — 图的可读性、标注完整性、自明性；与 `figure-designer` 的 QC 清单衔接

## 机械规则（强制执行）

- 禁 em-dash（—），禁 AI 腔禁用词（"delve"、"showcase"、"it is important to note" 等），完整清单见 `references/forbidden-patterns.md`
- 每段首句必须是主题句；引用格式全文统一

## 输出格式

1. 按维度分组的发现清单（每条：位置 → 问题 → 严重级别 → 改写建议）
2. 汇总表（CRITICAL/MAJOR/MINOR 计数）
3. 修改优先级路线图（先 CRITICAL，后 MAJOR，再 MINOR）

## MemOmics 适配规则

- 读草稿用 `read_file(offset/limit)` 分段读，不要一次性吞全文（省上下文）
- 只做审查和建议，不直接改用户文件；用户要求改时才改
- 所有"论文里写了什么"的判断必须基于实际读到的内容，不编造
