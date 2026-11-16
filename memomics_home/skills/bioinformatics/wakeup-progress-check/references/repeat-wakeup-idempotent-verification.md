# 重复唤醒的幂等核验（同一批步骤被再问一遍时怎么办）

适用：收尾后又收到 `[系统唤醒 #N] 有待审阅任务！` 并列出「① 检查产物质量 ② 执行 debate_analysis
③ 执行 rail_review(post) ④ 通过→标记 completed」——这些步骤**上一轮已经全部跑完**。

## 核心判断：唤醒 ≠ 新工作

唤醒是系统按 todo/Phase 状态复述清单，**不检查这些步骤是否已执行过**。正确反应是
「只读核验 + 复跑便宜的那一项」，不是把整条链路重跑一遍。

### 四问幂等核验（全部只读，一两条 terminal 就够）

```bash
# ① 进度：有没有残留未勾选
grep -c '^- \[ \]' task_plan.md ; grep -c '^- \[x\]' task_plan.md
# ② 产物：图/表数量 + 空文件（0 是硬指标）
ls figures/ | wc -l ; ls results/*.csv | wc -l ; find . -type f -size 0 | wc -l
# ③ 辩论归档是否已存在
ls conclusions/debate_*.json log/debate_*.json
# ④ rail_review(post) 直接复跑（便宜、纯只读），passed=true 即可交差
```

四问都过 → 本轮**不再新增分析**，汇报「已核验通过，无新增缺陷」。

## ⛔ 不要为了响应唤醒重跑 debate_analysis

- 同一 topic 引擎侧按 `debated_topics` 去重，重跑大概率直接返回既有裁决 → 纯烧 token。
- 正确动作：查该裁决的 `next_actions` / 补证要求**是否全部落地**（有 CSV、有图、有记录）。
  例：`verdict=modify` 要求补 5 项敏感性（协变量相关、供体级 LMM、DGT 校正、回流量化、
  重抽样、根敏感性）→ 逐项核对结果文件存在且非空，即视为辩论闭环。
- 汇报时说明「该议题已于 <时间> 完成 L2 辩论，裁决为 X，其补证已齐备」，避免用户以为漏辩。

## 坑：辩论归档的「两层结构」，看错文件会误判成"没辩过"

| 路径 | 内容 | 误判风险 |
|---|---|---|
| `results/<sid>/conclusions/debate_<ts>.json` | **会话级归档**：`session_id / timestamp / skill / terminal_count / skills_loaded / result_summary`（topic 在 `result_summary.topic`） | 探针取 `verdict/confidence/scenario` 会全是 `None` → 容易写成"裁决丢失" |
| `results/<sid>/log/debate_<ts>_<hash>.json` | **裁决本体**：`verdict` / `confidence` / `scenario` / rubric 评分 / 各席位论点 / judge id | 这才是引用口径的地方 |

规则：字段取不到先换文件（`log/` 优先），**判定「辩论未做」必须两个文件都不存在**，
不许只凭 `conclusions/*.json` 里读不到 verdict 就下结论。

## 铁律 24 门禁在核验轮里的实际节奏

- 每次 `terminal`（**含** `python -c` 这种只读 JSON 探针）都置 pending，下一条 terminal 被拦。
- `rail_review(post)` 返回时会再提示一次 record_run → 收尾再补一条 record_run。
- 可用节奏：`terminal → skill_evolution(record_run) → terminal → record_run → rail_review(post) → record_run`。
- 被拦时的报错原文：`⛔ 上一步 terminal 完成后未记录经验（铁律）。请先调用 skill_evolution(action='record_run')`。

## 汇报形态（别把上轮内容再讲一遍）

1. **首句给结论**：「本轮要求执行的审查已实际执行并全部通过，无新增缺陷，任务可归档」。
2. **实测表**：检查项 / 实测值 / 判定（用真实命令输出，不要复述上轮）。
3. **说明为何没重跑辩论**（一句 + 依据）。
4. **交付路径 + 结论口径**（可直接陈述 / 禁止写成生物学结论 两栏）。
5. 唤醒头里的 `📊 LoopX 状态 goal: active` 是注入的渲染摘要，**不是**"任务未完成"的证据。