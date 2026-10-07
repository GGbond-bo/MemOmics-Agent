# 工具调用体积预算 & skill 写入守卫（2026-09-24 实测）

## 1. 单次工具调用的体积预算 ≈ 8K token

**实测事故**：把 `read_file`（一个 199 行 / ≈12 KB 的 R 脚本，≈3–4K token）**与一个 terminal 调用同批发出**
→ 两者合计超上限 → 流式生成被服务端切断 → **两个调用一个都没送达**，整轮白烧，
回执只留一句 `The previous tool call (terminal, read_file) was too large and the stream timed out`。

**纪律**：
1. 读脚本正文**单独发一次调用**，不要与 terminal / write_file 等打包；
2. 只想知道某个常量或某段逻辑 → 用 `search_files`（定位行）或 `read_file(offset=, limit=)` 取片段，**不要整篇读**；
3. 改图 / 改参数时**只 patch 常量行**（与 SOUL 的图稿偏好记忆同理：不重读整脚本、不 vision 旧图）；
4. 同族：`write_file` 写大脚本要分块落盘；`rail_review(post)` 的 `code_executed` 不要整篇塞（改传脚本路径 + 关键片段）。

## 2. skill 写入守卫（背景 curation / 技能沉淀时最容易白跑）

| 守卫 | 报错关键字 | 处置 |
|---|---|---|
| **read-before-write** | `the current SKILL.md content has not been loaded in this review turn` + `_read_before_write_required: true` | 先 `skill_view(name)`（**不带 `file_path`**）→ **紧接着** patch。⚠️ 同轮**并行** view 多个 skill 只登记其中一个；view 支撑文件（`file_path=...`）**不算**加载 SKILL.md |
| **manually authored** | `records show it is not agent-created (created_by=None)` + `Manually authored skills are off-limits to autonomous curation` | 该 skill 在 curation 回合**不可写**（patch 与 write_file 都被拒）——**不要再试第二个参数组合**，改把同主题经验写到**agent 创建的伞形 skill**（如本 skill）。本次实例：`functional-enrichment` 被拒 → 同样的 GO 内容落到 `go-enrichment-visualization`（agent-created，写入成功） |
| **SKILL.md 超长** | `SKILL.md content is N characters (limit: 100,000)` | 改为写 `references/<topic>.md`（无长度限制，且自动出现在该 skill 的 `linked_files` 里，仍可被发现） |

**顺序建议**：先写 `references/` 与 `scripts/`（**不受** read-before-write 守卫限制，可批量），再 `skill_view(name)` → patch SKILL.md 补指针。
这样即使最后一步被拒，经验也已经在盘上了。

## 3. 卡死进程判定（与"内核 worker 不是任务"配对看）

`[系统唤醒] 任务卡死诊断` 点名 PID 时，先分清两类：

| 命令行特征 | 性质 | 动作 |
|---|---|---|
| 含 `_kernel_worker.py` / `_kernel_worker.R` / `webui/server.py` | 平台基础设施（按设计空闲待命，CPU 平 / 零 IO / RSS 数百 MB 是**健康**形态） | **绝不杀**，一句话说明即可 |
| 业务脚本（`Rscript xxx.R` / `python xxx.py`），且窗口内 **CPU/IO 零变化** | 真卡死 | 见下方判据 |

**真卡死的两种典型**：
- **R 层 O(n²) 假死**（实例：`simplify(measure="Wang")` / GOSemSim 在数千词条的 enrichResult 上）：进程存活、零 CPU、**RSS 缓慢上涨**（2.3 → 3.9 GB）。处置 = 强杀 → **改结构重跑**（拆脚本 / 换 Jaccard 去冗余 / 加 `nrow<=200` 守门），**不要原样重试**。
- **I/O 阻塞**：通常 CPU 平但**有磁盘活动**，先看日志尾部停在哪一步。

**强杀**：MSYS bash 下 `taskkill //F //T //PID <pid>` 会被吃掉参数（`//F` 变非法选项）→ 用 psutil 按进程树杀（`scripts/check_commit_memory.py --kill-tree <pid>`）。
⭐ **重跑前先核对产出清单**：已落盘的表/图**永不重算**，只补缺的那部分（单脚本架构下"卡死一步 = 全部重跑"，这正是要拆脚本的理由）。