# skills/plotting/ — 用户画图 Skill 沉淀库（用户专属 · 隔离分类）

> **用途**：跨会话复用用户提供的画图脚本（用户觉得漂亮/专业的、效果不错的）。
> **身份标识**：所有入库 skill 的 frontmatter 标 `category: user-skill` + `source: user`，列表显示为"用户技能"。
> **隔离原则**：只放画图脚本，**严禁**写入/覆盖 `bioinformatics/` 等其他分类；用户脚本**永不自动执行**（启用权在用户）。
> 完整设计见 `docs/user-skill-design.md`。

---

## 沉淀流程（6 步，询问是硬门禁）

```
用户提供画图脚本
  → ① 实际运行验证（真实/模拟数据跑通；报错 → 修复 → 再验证）
  → ② 汇报验证结果
  → ③ 【必问】"要沉淀到用户 skill 吗？"  ← 未询问 = 不沉淀（SOUL.md 铁律）
  → ④ 用户确认 → 入库 plotting/<script-name>/（场景标注 + verified + source:user）
  → ⑤ record_run 留档（skill_evolution action="record_run", skill="plotting/<名称>"）
  → ⑥ 汇报触发词示例
```

**双重门禁**：未验证的脚本不允许入库（防错误脚本污染复用链）；未询问用户不允许入库（用户专属权）。

---

## 数据流分流（两套去向，严禁混流）

| 数据 | 去向 | 机制 |
|------|------|------|
| 用户提供的脚本 + 经验记录 | **本库** `plotting/<name>/` | 验证 → 询问 → 确认写入（source: user） |
| skill 被触发运行产生的记录（成功/错误/参数） | **该 skill 自身目录**（自进化） | `record_run` → skill.json proven_params + 归档；`record_error` → `<skill>/logs/error_log.md` + Common Issues |

- 自进化由 `bio_tools/skill_evolution.py` 负责，**天然写 skill 自身目录**，无需手工搬运
- 严禁把 skill 运行记录写进本库；严禁把用户脚本塞进触发 skill 的 log
- 本库脚本被复用后的运行记录照常走"触发 skill 自进化"

---

## 画图分流决策树（SOUL.md「用户 Skill 使用铁律」）

```
画图意图出现
├─ 用户指定了脚本 → 按其脚本执行（仅参数/小修优化，不改风格）→ 结束【必问】沉淀
├─ 未指定，但 plotting/ 匹配到用户脚本
│     → 【必问】"发现你之前用过 XX 脚本，用它画 / 用 CNS 标准版 / 出两版？"
│     → 按用户选择执行 → 结束【必问】沉淀
└─ 未指定，无匹配 → 用 CNS 画图 skill（nature-figure / cns-visualization /
                      scrna-cns-figure-design）→ 结束【必问】沉淀
```

**核心不变式：用户脚本永远不自动执行**——匹配到只是"候选"，是否使用必须用户拍板（新会话同理）。

---

## 目录结构（两层，兼容 skill 发现机制）

```
plotting/
├── README.md                    ← 本文档
└── <script-name>/               ← 每个脚本一个 skill 目录（list_skills 单层枚举可发现）
    ├── SKILL.md                 ← frontmatter + 场景/输入/输出/验证/来源
    ├── scripts/<script-name>.R  ← 已验证脚本（唯一版本，改动走验证→替换）
    └── skill.json               ← source: user, category: user-skill
```

### SKILL.md 模板

```markdown
---
name: <script-name>
description: >-
  <一句话使用场景——必须含精准触发词：图类型 + 风格 + 数据形态，禁止"画图/绘图/好看"等泛词>
metadata:
  hermes:
    category: user-skill
    tags: [user, plotting]
source: user
verified: 2026-08-12
---

## 使用场景
- 什么时候用这个脚本（用户原话场景 + 可触发意图示例）
- 触发词示例："用那个XX风格画YY图" / "像上次那样出Z图"

## 输入要求
- 数据格式（矩阵/Seurat/ArchR 对象/列名约定）
- 必要参数

## 输出
- 图类型、格式（PDF/PNG/SVG）、尺寸、配色、字体风格
- 保存路径约定

## 验证状态
- 验证日期、数据来源（模拟/真实）、运行结果（成功/修复记录）
- 修复记录：错误 → 根因 → 修复

## 来源
- user（用户提供）/ adapted（基于 nature-skill 或其他改编）
```

### skill.json 模板

```json
{
  "id": "<script-name>",
  "name": "<显示名>",
  "category": "user-skill",
  "language": "R/Python",
  "source": "user",
  "description": "<与 SKILL.md frontmatter 一致>",
  "when_to_use": "<使用场景一句话>",
  "parameters": {},
  "proven_params": [],
  "proven_script": "scripts/<script-name>.R",
  "error_count": 0,
  "success_count": 1
}
```

---

## 场景标注规范（决定意图匹配质量）

| 要素 | 要求 | 反例（禁用） |
|------|------|-------------|
| 图类型 | 具体：UMAP 分面、火山图、富集气泡图、热图、生存曲线 | "图" |
| 风格 | 具体：publication/Nature 配色、灰底网格、无边框 | "好看/专业" |
| 数据形态 | 具体：Seurat 对象、ArchR proj、DESeq2 结果、矩阵 | "数据" |
| 用法 | 具体：按分组分面、标注基因名、双色渐变 | "画一下" |

---

## 防污染三层（每次沉淀/使用前自查）

1. **物理隔离**：只写入 `plotting/` 目录，未触碰 bioinformatics 等其他分类
2. **词级隔离**：description 无泛词（画图/绘图/好看/专业）——防误触发注入
3. **行为隔离**：用户脚本仅作"候选"，使用前必询问（新会话/同会话一致）

沉淀前自查清单：
- [ ] 只写入本目录，未触碰其他分类
- [ ] description 无泛词
- [ ] 脚本已真实运行验证（非仅语法检查）
- [ ] 已询问用户并获得确认（硬门禁）
- [ ] 修复记录已写入 SKILL.md"验证状态"
- [ ] frontmatter category: user-skill + source: user + verified 日期
