# 用户 Skill 体系设计（user-skill）

> 状态：v1 设计定稿 · 2026-08-12
> 目标：用户提供的脚本/经验 → 验证 → **询问确认** → 沉淀为"用户 skill"；画图等场景跨会话**参考复用**，但**绝不自动使用**（防污染）。

---

## 1. 设计原则（用户四点诉求 → 机制）

| 诉求 | 机制 |
|------|------|
| ① 用户提供脚本 → 测试运行后 → **询问**要不要沉淀 | 沉淀铁律：未询问 = 不沉淀；未验证 = 不沉淀（双重门禁） |
| ② 疑惑就问、不确定就问、确定需求再动手 | SOUL.md「疑惑必问」铁律：任何不确定先问，禁止猜 |
| ③ 用户指定脚本 → 按它画（或优化）；不满足 → CNS skill；**结束立马问沉淀** | 画图分流决策树（场景 B/C） |
| ④ 新会话画图 → 匹配用户脚本 → **不自动用**：与 CNS 对比、出两版或提醒询问 | 防污染铁律：用户脚本默认"候选"，启用权在用户 |

---

## 2. 架构

### 2.1 目录结构（两层，兼容现有 skill 发现机制）

```
hermes_home/skills/
├── plotting/                        ← 顶层分类：用户画图 skill 专属库（隔离）
│   ├── README.md                    ← 库规范（沉淀流程/询问铁律/分流策略）
│   └── <script-name>/               ← 每个用户脚本一个 skill（可被发现/注入）
│       ├── SKILL.md                 ← frontmatter 见 2.2
│       ├── scripts/<script-name>.R  ← 已验证脚本（唯一版本）
│       └── skill.json               ← source: user, category: user-skill
│
└── user-skill-<类别>/               ← 未来：用户提供的非画图沉淀（分析流程等）
```

- 发现机制：`list_skills` 单层枚举 `skills/<分类>/<skill>/SKILL.md` ✅ 本结构天然兼容
- 注入机制：`build_skills_system_prompt` 全量把 SKILL.md description 组装进 system prompt → agent 对话时可见 ✅

### 2.2 SKILL.md frontmatter 规范

```yaml
---
name: <script-name>
description: >-
  <一句话使用场景：图类型 + 风格 + 数据形态 + 触发词示例；禁止泛词>
metadata:
  hermes:
    category: user-skill          # ← 显示为"用户技能"（隔离标识）
    tags: [user, plotting]        # ← user = 用户提供，plotting = 画图类
source: user                      # user / adapted / verified
verified: 2026-08-12              # 最后验证日期
---
```

### 2.3 分类显示映射（server.py JSON_CATEGORY_MAP 新增）

```python
"user-skill": "用户技能",
"user-plotting": "用户画图",
```

---

## 3. 全链路（四场景）

### 场景 A：用户当前会话提供脚本
```
用户发脚本 → ① 运行验证（真实/模拟数据跑通；报错→修复→再验证）
→ ② 汇报验证结果 → ③ 【必问】"要沉淀到用户 skill 吗？"
→ ④ 用户确认 → 入库 plotting/<name>/（场景标注+verified+source:user）
→ ⑤ record_run 留档 → ⑥ 汇报触发词示例
```

### 场景 B：用户指定脚本画图
```
用户："用这个脚本画 XX" → ① 按其脚本执行（必要时仅优化参数/小修，不改风格）
→ ② 画完汇报 → ③ 【必问】"这个脚本要沉淀吗？"（未沉淀过时）
```

### 场景 C：无指定脚本的普通画图
```
识别画图意图 → ① 检索 plotting/ 有无匹配脚本
├─ 有匹配 → 【必问】"发现你之前用过 XX 脚本，用它画 / 用 CNS 标准版 / 出两版？"
│          → 按用户选择执行 → 结束后询问沉淀
└─ 无匹配 → ② 用 CNS 画图 skill（nature-figure / cns-visualization / scrna-cns-figure-design）
          → 画完汇报 → 【必问】"这次的图/经验要沉淀吗？"
```

### 场景 D：新会话画图意图
```
用户画图意图（如"画个 Nature 风格 UMAP 分面图"）→ ① 检索 plotting/ 匹配
→ ② 【必问】"之前用过 XX 脚本（效果不错），用哪个：旧脚本 / CNS 标准版 / 两版对比？"
→ ③ 不默认用用户脚本（防污染核心：启用权在用户）
→ ④ 按选择执行 → 结束后询问沉淀
```

**关键不变式**：用户脚本**永远不自动执行**——必须经用户明确选择。防污染三层：
1. 物理隔离（plotting/ 专属目录，不触碰 bioinformatics 等）
2. 词级隔离（description 禁泛词，防误触发）
3. 行为隔离（SOUL.md 铁律：候选不自动用）

---

## 3.5 数据流分流（两套去向，严禁混流）

```
用户提供脚本 + 经验记录 ──→ skills/plotting/<name>/（user-skill 库）
                          （先验证 → 询问用户 → 确认才写入；source: user）

skill 被触发运行产生的记录 ──→ 该 skill 自身目录（自进化，不进 user-skill）
   ├─ record_run  (record_success) → skill.json proven_params/proven_script
   │                                + SKILL.md Proven Scripts 表
   │                                + results/.../log/run_record_run_*.json 归档
   └─ record_error                  → <skill>/logs/error_log.md
                                     + SKILL.md Common Issues 表
                                     + results/.../log/run_record_error_*.json 归档
```

- 自进化链路（`bio_tools/skill_evolution.py`）已存在且**天然写 skill 自身目录**，无需改造
- agent 职责：**不要**把 skill 的运行记录/错误日志写入 user-skill 库；**不要**把用户脚本塞进触发 skill 的 log
- 用户脚本进入 user-skill 后若被复用，其运行记录照常走"触发 skill 自进化"——但库本身只存用户提供物

---

## 4. SOUL.md「用户 Skill 使用铁律」（新增小节）

| 时机 | 动作 |
|------|------|
| 任何不确定/疑惑时 | **先问用户，禁止猜测**；确定用户需求后再动手（疑惑必问铁律） |
| 用户提供脚本/经验 | 先运行验证 → **询问用户**是否沉淀 → 用户确认才写入 `skills/plotting/`（未询问 = 不沉淀） |
| 画图且用户指定脚本 | 按用户脚本执行（仅参数/小修优化）；结束后**立即询问**是否沉淀 |
| 画图且未指定脚本 | 用 CNS 画图 skill（nature-figure 等）；结束后**立即询问**是否沉淀 |
| 新会话画图且匹配到用户脚本 | **绝不自动使用**：向用户说明"发现之前用过的脚本 XX"，询问用旧脚本/CNS/出两版，按用户选择执行 |
| 沉淀写入时 | 只写 `skills/plotting/`；source: user；场景标注精准（禁泛词） |

---

## 5. 测试矩阵（多场景/多意图）

### 5.1 意图识别测试（_classify_intent）
| 输入 | 期望 |
|------|------|
| "画个 Nature 风格的 UMAP 分面图" | analysis（置信≥0.3） |
| "帮我把火山图换成柱状图，CNS 配色" | analysis |
| "今天天气怎么样" | chat |
| "把结果用 PPT 汇报一下" | 报告类 |

### 5.2 skill 发现/分类测试
| 输入 | 期望 |
|------|------|
| 建测试 skill `plotting/_test-script/SKILL.md`（category: user-skill） | list_skills 归入"用户技能" |
| 建测试 skill `plotting/_test-script/SKILL.md`（category: user-plotting） | 归入"用户画图" |
| description 含"画图"泛词 | 检查词级隔离规则生效（README 自查项） |

### 5.3 注入测试
| 输入 | 期望 |
|------|------|
| build_skills_system_prompt() | 输出包含 user-skill 描述行 |

### 5.4 四场景模拟（规则检查 + 决策模拟）
| 场景 | 输入 | 期望行为 |
|------|------|---------|
| A | 用户发脚本 | 先验证 → 必问沉淀 |
| B | 指定脚本画图 | 按其脚本 → 必问沉淀 |
| C | 画图无指定 | 有匹配→必问选择；无匹配→CNS skill |
| D | 新会话画图 | 匹配→必问，不自动用 |

---

## 6. 实施清单

- [x] 探索：发现机制（单层枚举）、注入机制（全量 description）、意图识别（画图关键词已覆盖）、CNS skill 清单（nature-figure 等）
- [x] SOUL.md：新增「用户 Skill 使用铁律」小节（含数据流分流）
- [x] server.py：JSON_CATEGORY_MAP 加 `user-skill`/`user-plotting` 映射；list_skills scan_dirs 登记 plotting/
- [x] skills/plotting/README.md：更新为完整规范（分流策略 + 询问铁律 + 防污染三层 + 数据流分流）
- [x] 测试：5.1-5.4 全跑通过（详见测试记录）
- [x] 提交 git

## 7. 测试记录（2026-08-12）

| 用例 | 结果 |
|------|------|
| 5.1 意图识别：画 UMAP 分面 → analysis 0.60 ✅；火山图换柱状图 CNS 配色 → analysis 0.75 ✅；天气 → chat 0.90 ✅ | 画图意图 2/2 |
| 5.1 观察项：'把结果用 PPT 汇报一下' → analysis 0.50（期望 report；既有行为，非本次回归） | 记录不修 |
| 5.2 分类显示：`_test-user-plot`（category: user-skill）→「用户技能」✅；`user-plotting` →「用户画图」✅ | 2/2 |
| 5.3 注入：build_skills_system_prompt 含两个测试 skill 的 description ✅（需设 HERMES_HOME） | 1/1 |
| 5.4 规则存在性 9 项 ✅；四场景 9 分支（门禁拦截 4 项均正确拒绝/阻塞）✅；分流机制确认（record_run→skill.json proven、record_error→logs/error_log.md）✅ | 全过 |
| 架构坑：list_skills 只扫 SKILLS_DIR + bioinformatics/，plotting/ 不在浏览索引 → 已修复 scan_dirs | 修复 |
| 架构坑：独立进程测注入需设 HERMES_HOME（server.py 顶部才设置） | 记录 |

**遗留**：运行中的 8899 server 需重启才加载新 scan_dirs/分类映射（manifest 会在下次调用自动重建 snapshot）。
