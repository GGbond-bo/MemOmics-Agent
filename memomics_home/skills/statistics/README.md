# skills/statistics/ — 用户统计检验脚本沉淀库（用户专属 · 隔离分类）

> **用途**：跨会话复用**统计检验/显著性计算类**脚本——组间独立比较、配对比较、细胞比例各组间显著性、效应量计算等。
> **身份标识**：所有入库 skill 的 frontmatter 标 `category: user-skill` + `source: user`（AI 按用户口头需求编写的标 `source: user-requested` 并注明原始需求），列表显示为"用户技能"。
> **隔离原则**：只放统计检验类脚本，**严禁**写入/覆盖 `bioinformatics/`、`plotting/`、`comparison/` 等其他分类；用户脚本**永不自动执行**（启用权在用户）。
> **配套**：总索引 `skills/user-scripts/INDEX.md`。

---

## 什么算"统计检验类"（归本库）

| 用户需求 | 例子 | 归哪个库 |
|---------|------|---------|
| 算显著性 / P 值 / 组间比较 | 衰老组独立比较、运动前后配对比较、细胞比例各组间显著性、t 检验/Wilcoxon/卡方/Fisher | **statistics**（本库） |
| 对比分析完整流程（含建模/差异分析全链路） | 6 组 DEG 全流程、细胞通讯对比流程 | comparison |
| 画图 / 出图 | 小提琴图、热图 | plotting |

**判定核心**：用户意图是"**算**显著性/检验/比较"（产出统计量）→ statistics；意图是"**跑完整对比流程**"（产出分析结论）→ comparison。

## 沉淀来源（两类同等沉淀，2026-08-22 用户确认）

1. **用户提供的脚本** — 以用户脚本为基准（不改风格），运行验证后沉淀
2. **用户口头需求 → AI 编写**（无脚本、无官方教程）— 如"算细胞比例显著性：衰老组间独立比较 + 运动前后配对比较"。AI 写脚本 → 实际跑通 → 汇报 → **用户认可** → 沉淀。SKILL.md frontmatter `source: user-requested`，描述里写原始需求原文。

---

## 沉淀流程（6 步，询问是硬门禁）

```
用户需求出现（给了脚本 或 口头需求）
  → ① 实际运行验证（真实/模拟数据跑通；报错 → 修复 → 再验证）
  → ② 汇报验证结果（统计量/结论）
  → ③ 【必问】"要沉淀到用户 skill 吗？"  ← 未询问 = 不沉淀（SOUL.md 铁律）
  → ④ 用户确认 → 入库 statistics/<script-name>/（场景标注 + verified + source:user|user-requested）
  → ⑤ record_run 留档（skill_evolution action="record_run", skill="statistics/<名称>"）
  → ⑥ 汇报触发词示例 + 登记到 skills/user-scripts/INDEX.md
```

**双重门禁**：未验证的脚本不允许入库；未询问用户不允许入库。

---

## 目录结构（两层，兼容 skill 发现机制）

```
statistics/
├── README.md                    ← 本文档
└── <script-name>/               ← 每个脚本一个 skill 目录（list_skills 单层枚举可发现）
    ├── SKILL.md                 ← frontmatter（category: user-skill, source: user|user-requested）+ 场景/输入/输出/验证/来源
    ├── scripts/<script-name>.R  ← 已验证脚本（唯一版本，改动走验证→替换）
    └── skill.json               ← source: user|user-requested, category: user-skill
```

SKILL.md / skill.json 模板与场景标注规范：同 `skills/plotting/README.md`（图类型→检验类型、风格→检验设计、数据形态→分组结构）。

## 沉淀示例（用户 2026-08-22 提出的典型需求）

- 需求："计算细胞比例各组间的显著性，衰老好用独立比较，运动前后配对比较"
- 沉淀：`statistics/cell-proportion-significance/`
- 触发词："算显著性" / "细胞比例检验" / "组间独立比较" / "配对比较" / "比例显著性"
- 下次同类需求：先查 INDEX → 复用旧脚本只改数据路径/分组参数

---

## 防污染三层（每次沉淀/使用前自查）

1. **物理隔离**：只写入 `statistics/` 目录，未触碰 bioinformatics / plotting / comparison 等其他分类
2. **词级隔离**：description 无泛词（"统计"/"显著性"等泛词禁用）——必含具体：检验类型 + 分组结构 + 数据形态（如"细胞比例 6 组 × 独立/配对 显著性检验"）
3. **行为隔离**：用户脚本仅作"候选"，使用前必询问（新会话/同会话一致）

沉淀前自查清单：
- [ ] 只写入本目录，未触碰其他分类
- [ ] description 无泛词
- [ ] 脚本已真实运行验证（非仅语法检查）
- [ ] 已询问用户并获得确认（硬门禁）
- [ ] 修复记录已写入 SKILL.md"验证状态"
- [ ] frontmatter category: user-skill + source: user/user-requested + verified 日期
- [ ] 已登记到 skills/user-scripts/INDEX.md
