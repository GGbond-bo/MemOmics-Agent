# 委派回执「迟到重放」实测案例与去重协议

> 案例来源：竞品定位交付（31 篇科研 AI agent 全文精读）会话，2026-10-02 派发 / 2026-10-07 收到回执。

## 一、案例时间线（为什么会骗人）

| 时间 | 事件 |
|---|---|
| 2026-10-02 01:45 | 派发 3 个子代理（batch deleg_58d8c19a），n=1..12 / 14..24 / 26..45 |
| 2026-10-02 | 结果**当天已合并**进 `data/cards.json`（31 张全文精读卡） |
| 2026-10-07 18:13 | round2 引文逐字审计（`cards_v1_snapshot.json` 存证） |
| 2026-10-07 18:58 | 回执第一次到达 → 核对后判「无需重复合并」，写入 `notes.md` |
| 2026-10-07 20:31 | **同一回执第二次到达**（`Dispatched:` 仍显示 10-02 01:45） |

⛔ 20:31 这次若照单全收，会把 16 张早已合并的卡再合一遍 → 污染 store、浪费 ~1 小时。

## 二、Δ=0 验证法（去重的唯一可靠依据）

```python
# 用 scripts/extract_llm_json.py 解析子代理 summary
from extract_llm_json import extract_items, delta_report
new, rep = extract_items(open(SUMMARY, encoding="utf-8").read(), id_key="n")
store = json.load(open("data/cards.json", encoding="utf-8"))
print(delta_report(new, store,
      ["architecture","models","benchmark","validation","key_claim",
       "novelty","limitations","inputs","outputs","evidence_quote"]))
```

实测输出：

```
total_old: 70461   total_new: 70461   delta: 0
verdict: ALREADY_MERGED (Δ≈0，无需重复合并)
```

**判读**：Δ=0 说明子代理产出与磁盘现状**逐字段完全一致** → 早前轮次已合并。
此时正确动作 = **不合并**，只落审计件（解析结果 + 现状快照），把结论追加到 `notes.md`。

## 三、子代理自报 ≠ 最终态（必须对产物验证）

同一批 summary 里子代理自报：

- `subagent-summary-0`：「**n=11 and n=12 full texts were NOT read**」「n=10 only via abstract」
- `subagent-summary-2`：「n=36 仅取到摘要/开头」「n=36、n=41 的 doi/团队/底层模型 因截断未取到」

**实查结论**：全是**撞 `max_iterations` 时的中间态自述**。磁盘快照显示这批卡早已含完整 10 字段
（1342–2296 字符/卡），n=36/n=41 的元数据也在后续轮次补齐。

→ 规则：**凡「未完成/未读/缺失/截断」类自报，一律先查磁盘产物，再决定要不要补做。**
不要照着自报重跑子代理——那是纯浪费。

## 四、回执自带的截断（另一条独立风险）

回执正文本身会被框架截断（本例 3 份 summary 中 **2 份被腰斩**：summary-0 仅 5,176 字符、
summary-2 无闭合围栏）。缓解手段：

- 回执提示里会给 `Full subagent output saved to:` 与 **live transcript** 路径
  （`cache/delegation/live/<deleg_id>/task-N.log`），优先去那里取全文；
- live log 也可能只有流式片段（本例 task-0.log 无 ```json 围栏）→ 说明**该子代理确实没产出完整 JSON**，
  属真实缺口，此时才需要补派。
- **先分辨「回执被截断」还是「子代理没做完」**：看 live log 里有没有闭合围栏。
  有围栏 → 内容确实产出过，但**别指望从 live log 取全**（见下）；无围栏 → 真缺口，补派
  （且下次派发时在 context 里要求「先输出已完成部分并闭合 JSON」）。

### 四b、live transcript 的硬限制（2026-10-07 第二次回执实测修正）

⛔ **live log 不是全量记录**：`cache/delegation/live/<deleg_id>/task-N.log` 会把 assistant 的长回复
截断成 `…(+N chars)`，只保留前后若干字符。实测对照：

| 文件 | 大小 | 该批实际产出 |
|---|---|---|
| `deleg_15d8b24b/task-0.log` | 26,194 B | 5 张深度卡 JSON ≈ 80 KB（落盘件 82,375 B） |
| `deleg_15d8b24b/task-2.log` | 19,126 B | 同上 |
| `deleg_15d8b24b/manifest.json` | 1,389 B | 只有 goal / log 路径 / status，**不含产出内容** |

→ 后果：拿 live log 做「回执 ↔ store」的逐字 diff，**必然假报"内容缺失"**。本会话第一版脚本正是
想从 live log 解析出 JSON 再 diff，结果 `parsed: 0`（没有一份完整围栏），白跑两轮才发现方向错了。

**live log 可靠的两个用途**（其余别用）：
1. 判断**有没有闭合 ```json 围栏** → 分辨"回执被截断"还是"子代理没做完"；
2. 看子代理**读/跑了什么**（`tool` 行的文件名、命令、退出码在 log 里是完整的）→ 核实它是否真读了全文
   （本例 log 显示 5 篇都用 `fold -s -w 700` 重排后分页读完，可据此确认 n=34..45 那批确实读全）。

✅ **要 diff 就 diff 自己落盘的解析件** `data/deep_cards_deleg_<id>.json`（合并当时顺手落盘、完整结构化）。
这正是「合并时把解析结果落盘」这条习惯的价值所在 —— 它让后续任何一轮的**回执重放判定**都能做到逐字节。

## 五、交付物重建时的解释器探测（不要直接 pip install）

构建脚本（`md2docx.py` 等）依赖 `python-docx`，**不一定在项目 `.venv` 里**。
铁律 29：先查用户环境，用户同意才装。做法是先**探测哪个解释器已经能 import**：

```bash
for P in ".venv/Scripts/python.exe" "python"; do
  echo "--- $P"; $P -c "import docx,sys;print('docx OK',sys.executable)" 2>&1 | tail -1
done
```

哪个能 import 就用哪个跑构建，**不要**为了一次出 DOCX 去 install 包（用户环境常已装）。
本例：系统 Python 有 `python-docx`，项目 `.venv` 没有 → 直接用系统 Python 重建 DOCX。

## 六、合并后收尾清单

1. `grep -rl "<旧标签>" deliverables/` — 残留旧标签扫描（DOCX / HTML / MD 三处口径一致）
2. 多批次合并的条目**按真实合并日期分别标注**，别用一个"最新轮次"标签盖住全部
3. 证据行去重键用 `(doi, claim[:80])`，不是单 `doi`（单键会丢掉同一文献的逐字佐证行）
4. 新证据行逐条做**字节级子串断言**（`claim in 原文全文`），打印命中率，不通过不入库
5. 快照 + 审计日志落 `data/` 与 `log/`，结论写 `notes.md`（跨轮锚点，防再次重放时重复劳动）

---

## 七、案例 B：第二次回执重放（deleg_15d8b24b，2026-10-07）

### 时间线

| 时间 | 事件 |
|---|---|
| 2026-10-07 19:14:45 | 派发 3 子代理（batch `deleg_15d8b24b`）：n=4..8 / 9,10,11,12,33 / 34,35,36,41,45 |
| 2026-10-07 19:19:32 | 三任务全部 completed（291 s） |
| 2026-10-07 20:36 | 合并完成、交付定稿（DOCX 769,470 B / HTML 1,180,780 B / evidence.csv 97 行数据） |
| 之后 | 系统再次推送 `[ASYNC DELEGATION BATCH COMPLETE]`，`Dispatched:` 仍是 19:14:45，`(4m47s ago)` 是错的 |

### 5 项检查实测结果（全零差异 → 判重放）

| 检查 | 结果 |
|---|---|
| 0 容器形状 | `cards.json` = **list[dict]**（31 元素，键在元素里，不是 dict） |
| 1 证据源 | `data/deep_cards_deleg_15d8b24b.json`（82,375 B，sha256 `3f21f997…`）↔ `cards.json`（sha256 `b241dc85…`） |
| 2 逐字段归一 diff | **150/150 字段一致，完全一致卡 15/15，总字符Δ = 0** |
| 3 独有串探针 | 15 卡 × 4 串 = **60/60 命中**（`OntoReaction` / `ROGI` / `TSEMO` / `MCPCreator` / `FastMCP` / `CPAR` / `0.36 V` …） |
| 4 闭环不变量 | 首发批 16 张 + 本批 15 张 = **31 == store 总卡数**；`deep_read_round` 分布 = 16 @ 2026-10-02 / 15 @ 2026-10-07 |
| 5 交付物指纹 | 769,470 B / 1,180,780 B / 246,520 B / 98 行 **逐位吻合会话锚点** |

### 教训

1. **两个批次正好拼满全集**（16 + 15 = 31）：这类「各批卡数之和 == store 总数」的不变量是**发现漏批的最快手段**，
   比逐卡点检便宜得多；再叠加 `deep_read_round` 分布等于各批卡数，闭环就算坐实了。
2. **大小写陷阱**：探针 `GeNomad` 未命中而 `geNomad` 命中 —— 探针一律先 `.lower()` 再判。
3. **别把中间态当结论**：本轮先 `glob` 列目录 → 才发现 live log 被截断 → 才转向落盘解析件。
   若一开始就凭「live log 里没找到完整 JSON」下结论，会误判成"需要重新派发子代理"，纯浪费一轮。
   **先花一次调用把证据源形状摸清，再写比对逻辑。**
4. **比对脚本要一次成型**：脚本里一处 f-string 拼错直接 `SyntaxError`，白跑一轮。
   §二 的 5 项检查已实现为 `scripts/verify_batch_replay.py`，**直接跑它**，不要临场手搓。
5. **汇报口径**：说清 diff 的是「落盘解析件 ↔ store」，并如实说明**为什么没用回执原文 / live log**
   （被截断）。把前者包装成后者的逐字 diff 属于夸大证据 —— 用户审计的是证据链强度。