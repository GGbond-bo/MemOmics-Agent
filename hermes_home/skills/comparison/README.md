# skills/comparison/ — 用户比对脚本沉淀库（用户专属 · 隔离分类）

> **用途**：跨会话复用用户提供的**比对/对比流程类**脚本（单细胞组间对比、差异分析流程、多组比较、配对比较等）。
> **身份标识**：所有入库 skill 的 frontmatter 标 `category: user-skill` + `source: user`，列表显示为"用户技能"。
> **隔离原则**：只放比对/对比类脚本，**严禁**写入/覆盖 `bioinformatics/`、`plotting/` 等其他分类；用户脚本**永不自动执行**（启用权在用户）。
> **配套**：总索引 `skills/user-scripts/INDEX.md`；画图脚本走 `skills/plotting/`。

---

## 比对 vs 画图 vs 正式 skill 的判断（2026-08-22 用户定稿）

```
用户给了脚本
├─ 画图/出图 → skills/plotting/<名称>/
├─ 比对/对比流程/差异比较 → skills/comparison/<名称>/   ← 本库
├─ 统计检验/显著性计算（独立/配对比较、比例检验）→ skills/statistics/<名称>/
└─ 其他分析 → 按用途建类（skills/qc/、skills/clustering/ 等）

用户没给脚本 + 主题有文章/官网/教程 → create-bio-skill 创建正式 skill（注册后立即可用）
用户没给脚本 + 口头需求（如"算显著性"）→ AI 编写 → 验证 → 用户认可 → 按意图分类沉淀（统计类→statistics/）
用户说"之前那个脚本" → 查 skills/user-scripts/INDEX.md 回忆复用
```

> **comparison vs statistics 判定**：意图是"跑完整对比流程"（产出分析结论）→ comparison；意图是"算显著性/检验/比较"（产出统计量）→ statistics。

---

## 沉淀流程（6 步，询问是硬门禁，同 plotting/）

```
用户提供比对脚本
  → ① 实际运行验证（真实/模拟数据跑通；报错 → 修复 → 再验证）
  → ② 汇报验证结果
  → ③ 【必问】"要沉淀到用户 skill 吗？"  ← 未询问 = 不沉淀（SOUL.md 铁律）
  → ④ 用户确认 → 入库 comparison/<script-name>/（场景标注 + verified + source:user）
  → ⑤ record_run 留档（skill_evolution action="record_run", skill="comparison/<名称>"）
  → ⑥ 汇报触发词示例 + 登记到 skills/user-scripts/INDEX.md
```

**双重门禁**：未验证的脚本不允许入库；未询问用户不允许入库。

---

## 目录结构（两层，兼容 skill 发现机制）

```
comparison/
├── README.md                    ← 本文档
└── <script-name>/               ← 每个脚本一个 skill 目录（list_skills 单层枚举可发现）
    ├── SKILL.md                 ← frontmatter（category: user-skill, source: user）+ 场景/输入/输出/验证/来源
    ├── scripts/<script-name>.R  ← 已验证脚本（唯一版本，改动走验证→替换）
    └── skill.json               ← source: user, category: user-skill
```

SKILL.md / skill.json 模板与场景标注规范：同 `skills/plotting/README.md`（图类型→分析类型、风格→比对设计、数据形态→分组结构）。

---

## 防污染三层（每次沉淀/使用前自查）

1. **物理隔离**：只写入 `comparison/` 目录，未触碰 bioinformatics / plotting 等其他分类
2. **词级隔离**：description 无泛词（"比对"/"分析"等泛词禁用）——必含具体：比对类型 + 分组结构 + 数据形态（如"Seurat 对象 6 组 × 2 状态 差异比较"）
3. **行为隔离**：用户脚本仅作"候选"，使用前必询问（新会话/同会话一致）

沉淀前自查清单：
- [ ] 只写入本目录，未触碰其他分类
- [ ] description 无泛词
- [ ] 脚本已真实运行验证（非仅语法检查）
- [ ] 已询问用户并获得确认（硬门禁）
- [ ] 修复记录已写入 SKILL.md"验证状态"
- [ ] frontmatter category: user-skill + source: user + verified 日期
- [ ] 已登记到 skills/user-scripts/INDEX.md
