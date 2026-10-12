# 上游 27 个写作技能速查（ChineseResearchLaTeX v4.1.1）

> 来源：上游 `README.md` 的 `<!-- SKILL-LIST -->` 官方表格（版本号同步自各 `skills/*/config.yaml`）。
> **详细规范一律以 `<安装目录>/third_party/CRL/skills/<name>/SKILL.md` 为准**——本文件只做选型索引，不复制流程细节。
> ⚠️ 标 `🚧` 的是上游自述「开发中，未充分测试」，优先用 `✅` 的。

| 技能 | 阶段 | 版本 | 功能 | 状态 |
|------|------|------|------|------|
| make-latex-model | 🔧 模板开发 | v3.1.2 | 全仓库模板落地与高保真对齐（支持 NSFC/paper/thesis/cv 四线） | ✅ |
| complete-example | 🔧 模板开发 | v1.4.1 | 智能示例生成与补全（填空白章节） | ✅ |
| transfer-old-latex-to-new | 🔧 模板开发 | v2.1.0 | 模板迁移与重构编排（旧材料 → 当前结构） | ✅ |
| research-literature-search | 📚 文献调研 | v1.0.4 | 多源文献检索、规范化、canonical 去重 + manifest 审计包 | ✅ |
| research-literature-review | 📚 文献调研 | v2.0.0 | 消费 search manifest 的可审计专家级综述 | ✅ |
| research-citation-check | 📚 文献调研 | v1.1.0 | 综述引用语义一致性检查 | ✅ |
| research-topic-extractor | 📚 文献调研 | v1.1.0 | 结构化综述主题提取 | ✅ |
| research-guide-updater | 📚 文献调研 | v1.1.0 | 项目指南优化与写作规范沉淀 | ✅ |
| research-plan | 📚 文献调研 | v0.2.0 | 文献驱动的科研分析策略规划 | 🚧 |
| research-literature-radar | 📚 文献调研 | v0.2.0 | 分层发现、筛选并长期归档重要文献 | 🚧 |
| research-literature-interpretation | 📚 文献调研 | v0.2.0 | 导师式解读单篇文献（机制/证据边界/可迁移启发） | 🚧 |
| research-idea | 📚 文献调研 | v0.15.0 | 基于证据地图与价值筛选评估科研方向 | 🚧 |
| nsfc-code | ✍️ 标书 | v1.0.0 | NSFC 申请代码推荐（5 组 code1/code2 + 理由，只读） | ✅ |
| nsfc-abstract | ✍️ 标书 | v2.1.2 | 标题建议 + 中英文摘要（中文≤400 字；英文≤4000 字符） | ✅ |
| nsfc-budget | ✍️ 标书 | v0.1.2 | 预算说明书 + `budget.pdf` | 🚧 |
| nsfc-justification-writer | ✍️ 标书 | v1.3.0 | 立项依据语义写作 + 可读性复核 + 可逆写入 | ✅ |
| nsfc-research-content-writer | ✍️ 标书 | v1.0.0 | 研究内容编排写作 | ✅ |
| nsfc-research-foundation-writer | ✍️ 标书 | v0.1.2 | 研究基础编排写作 | 🚧 |
| nsfc-qc | ✍️ 标书 | v1.2.1 | 只读质量控制（文风/引用/篇幅/逻辑 + 缩写注册表） | ✅ |
| nsfc-ref-alignment | ✍️ 标书 | v0.1.1 | 参考文献与正文引用一致性核查（只读） | 🚧 |
| nsfc-reviewers | ✍️ 标书 | v1.4.1 | 多专家评审模拟（默认 3 组、最多 5 组，含函评/会评） | ✅ |
| nsfc-length-aligner | ✍️ 标书 | v0.3.1 | 篇幅对齐（检查差距 → 扩写/压缩） | 🚧 |
| nsfc-humanization | ✍️ 标书 | v1.2.0 | 分词/句法/段落/章节四层去 AI 味 | ✅ |
| paper-write-sci | 📝 SCI | v0.11.2 | SCI 写作与修订（风格化写作/数字审查/逻辑审查/PDF+Word 闭环） | 🚧 |
| paper-explain-figures | 📝 SCI | v0.2.0 | 解读 Figure 含义 → Markdown 报告 | 🚧 |
| paper-select-journal | 📝 SCI | v0.3.1 | 投稿期刊筛选（稿件画像 + 期刊核验 + 近 3 月相似论文） | 🚧 |
| paper-know-journal | 📝 SCI | v0.3.0 | 期刊投稿指南调研（作者指南/形式要求/费用/社区评价） | 🚧 |

## 命名迁移（旧 Prompt 兼容）
| 历史名 | 当前名 |
|---|---|
| `get-review-theme` | `research-topic-extractor` |
| `guide-updater` | `research-guide-updater` |
| `check-review-alignment` | `research-citation-check` |
| `make-research-plan` | `research-plan` |
| `systematic-literature-review` | `research-literature-review` |
| `make_latex_model` | `make-latex-model` |
| `migrating-latex-templates` | `transfer-old-latex-to-new` |

## 与 MemOmics 工具的分工（避免重复劳动）
| 上游技能 | MemOmics 里更该用哪个 |
|---|---|
| `research-literature-search` / `-review` | `search_papers` / `literature-review` / `deep-research`（本机已有检索链，无需上游 manifest 体系） |
| `paper-explain-figures` | `nature-reader` / `paper-summary` |
| `nsfc-humanization`、`nsfc-qc` | 可直接借其检查清单；中文去 AI 味本机另有 `human-skill` |
| `make-latex-model` / `transfer-old-latex-to-new` | 无对应 MemOmics 技能 → **本 skill 直接调用**（这是本 skill 最不可替代的部分） |