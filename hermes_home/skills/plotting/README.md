# skills/plotting/ — 用户画图脚本沉淀库（隔离分类）

> **用途**：跨会话复用用户提供的画图脚本（用户觉得漂亮/专业的、nature-skill 里值得沉淀的、以及用户跑过的经验教训）。
> **隔离原则**：本目录只放画图脚本 skill，**严禁**写入/覆盖 `bioinformatics/` 等其他分类；其他分类的触发注入不受影响，防用户脚本污染通用 skill。

---

## 沉淀流程（5 步，缺一不可）

```
用户提供画图脚本
  → ① 实际运行验证（用真实/模拟数据跑通；报错则修复 → 再验证）
  → ② 场景标注（SKILL.md：触发词 + 输入要求 + 输出 + 验证状态 + 来源）
  → ③ 入库（本目录下建 <script-name>/，SKILL.md + scripts/ + skill.json）
  → ④ record_run 留档（skill_evolution action="record_run", skill="plotting/<名称>"）
  → ⑤ 汇报用户：已沉淀 + 触发词示例
```

**未验证的脚本不允许入库**（防错误脚本污染复用链）。验证失败的脚本：先修复→再验证→才能沉淀；修复过程记入 SKILL.md 的"验证状态"节。

---

## 目录结构（每个脚本一个子目录）

```
plotting/
├── README.md                    ← 本文档
├── <script-name>/               ← 如 my-umap-pub-style
│   ├── SKILL.md                 ← frontmatter + 场景/输入/输出/验证/来源
│   ├── scripts/<script-name>.R  ← 已验证的脚本（唯一版本，改动走验证→替换）
│   └── skill.json               ← 元数据（source 标 user/adapted；proven_params 记参数）
```

---

## SKILL.md 模板

```markdown
---
name: <script-name>
description: <一句话使用场景——必须含精准触发词：图类型 + 风格 + 数据形态，禁止"画图/绘图"等泛词>
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
- user（用户提供）/ adapted（基于 nature-skill 或其他改编）/ verified（官方已验证）
```

---

## skill.json 模板

```json
{
  "id": "<script-name>",
  "name": "<显示名>",
  "category": "plotting",
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

## 场景标注规范（决定意图识别是否命中）

| 要素 | 要求 | 反例（禁用） |
|------|------|-------------|
| 图类型 | 具体：UMAP 分面、火山图、富集气泡图、热图、生存曲线 | "图" |
| 风格 | 具体：publication/Nature 配色、灰底网格、无边框 | "好看/专业" |
| 数据形态 | 具体：Seurat 对象、ArchR proj、DESeq2 结果、矩阵 | "数据" |
| 用法 | 具体：按分组分面、标注基因名、双色渐变 | "画一下" |

**触发词命中规则**：用户说"画一个 Nature 风格的 UMAP 分面图"→ 检索 `plotting/` 下 description 含"UMAP 分面 + Nature 配色"的 skill 注入。

---

## 复用机制（意图识别）

1. **代码执行时**：MemOmics `_lookup_skill_context` 按代码关键词匹配 → 命中本目录 SKILL.md 注入上下文（proven script 直接可用）
2. **对话意图时**：用户描述画图需求 → agent 检索 `plotting/` 目录 description 匹配 → 选用最贴近的脚本（先确认数据格式匹配再跑）
3. **跨会话**：skill 目录常驻 hermes_home/skills/，新会话自动可发现

## 防污染清单（每次沉淀前自查）

- [ ] 只写入本目录，未触碰其他分类
- [ ] description 无泛词（画图/绘图/好看）
- [ ] 脚本已真实运行验证（非仅语法检查）
- [ ] 修复记录已写入 SKILL.md"验证状态"
- [ ] skill.json source 标注正确
