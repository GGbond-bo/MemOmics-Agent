---
name: figure-designer
description: "论文图设计顾问：对三张核心图（Motivated Example动机图/解决方案总览图/实验结果图）给设计范式、布局草图、标注指南、工具选型与QC审计建议。只给设计建议、不实际出图。触发词：设计图、图设计、图不好看、图不专业、选什么图、图型选择、布局建议、作图建议、figure design、choose the right chart"
when_to_use: "[figure-designer] 用户想表达某个结论但不知怎么设计图/图被说不好看不专业/要选图型或布局建议时使用。路由纪律：本技能只输出设计建议与QC审计，绝不代替出图；用户说'画个热图/帮我出图/生成图'一律按 SOUL.md 画图 Skill 选择策略走 nature-figure/cns-visualization/scipilot-figure-skill；说'设计图/图不好看/选什么图/布局'走本技能，给出建议后再让出图技能执行。"
trigger_keywords: ["设计图", "图设计", "图不好看", "图不专业", "选什么图", "图型选择", "布局建议", "图布局", "作图建议", "设计一张图", "figure design", "design a figure", "choose the right chart", "figure looks unprofessional", "plot design"]
trigger_level: YEL 讨论触发
metadata:
  version: "1.0.0"
  last_updated: "2026-08-16"
  status: active
  data_access_level: verified_only
  task_type: open-ended
  related_skills:
    - nature-figure
    - cns-visualization
    - scipilot-figure-skill
---

# Figure Designer（论文图设计顾问）

> 源自 [HKUSTDial/Supervisor-Skills](https://github.com/HKUSTDial/Supervisor-Skills)（CC BY-NC-SA 4.0），按 MemOmics 技能规范适配。

## 定位

顶刊论文 6–8 张图里，三张承担几乎全部叙事重量：**动机图（Figure 1）**、**方案总览图（方法部分）**、**实验结果图**。审稿人一分钟内扫这三张决定是否细读——图弱则论文被埋没。

本技能输入用户意图（想传达什么）+ 上下文（领域/方法/目标期刊），输出：
1. 推荐的设计范式（三选一，各自范式详见 `references/motivated-example.md`、`references/solution-overview.md`、`references/experimental-results.md`）
2. 布局草图（panel 划分 + 信息流方向）
3. 标注指南（标签层级、字号、颜色、图例位置）
4. 工具选型建议（见 `references/tools.md`）
5. QC 审计（对照通用设计规则清单，见 `references/design-rules.md`）

## 通用设计规则（审计依据）

- 每张图只有一个核心信息；一个 panel 只讲一件事
- 图要自明：脱离正文也能看懂（标注充分、图例完整）
- 颜色对色盲友好、全篇统一；信息密度适中，不堆砌
- 生物医学图的特殊性：亚群/分组标签位置、图外标签、z-score 色带、显著性标注等，沿用用户已确认的版式偏好（见记忆中的 [图稿] 条目）

## MemOmics 适配规则

- **只建议，不出图**。输出设计建议后，问用户是否让 `nature-figure`（发表级）/`cns-visualization`（生信快速图）/`scipilot-figure-skill`（通用数据图）执行
- 审查已有图时，用用户给的文件路径 read 图或让用户发图，不要凭空假设
- 引用用户已定稿的版式偏好（标签在图外、配色等），保持全篇一致
