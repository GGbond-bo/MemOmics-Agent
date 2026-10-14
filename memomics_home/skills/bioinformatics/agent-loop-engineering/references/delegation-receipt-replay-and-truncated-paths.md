# 外部事件回执的处理纪律：delegation 重放 & 系统注入「路径不存在」告警

来源：`memomics-be17649b` 科研 AI agent 竞品深读卡会话 — 2026-10-08（同一批回执重放 5 次）

## 1. 现象：同一个 delegation id 会被反复重放

系统在后台 fan-out 完成后注入的提示形如：

```
[系统唤醒] [ASYNC DELEGATION BATCH COMPLETE — deleg_15d8b24b]
A background fan-out of 2 subagent(s) you dispatched earlier has finished.
... You may have moved on since dispatching — act on these or re-dispatch if things have changed.
```

实测该提示**同一个 delegation id 连续重放 5 次**（跨轮、迟到送达，甚至有 `status=interrupted` 且 duration=0s 的假空回执）。

**关键认知**：

- 它是**事件通知**，不是新任务指令；「act on these」不等于「重跑一遍」。
- `status=interrupted` / `Parent agent interrupted — child did not finish in time` **不代表没有产出**——
  子代理常常在被中断前就已把结果 `json.dump` 落盘（本例：子代理中断，但
  `data/deep_cards_round2_t0a.json` 完整存在）。
- 跨轮重放会消耗整轮上下文，且容易诱发「重派 → 重复合并 → 数据代次混乱」。

## 2. 四步纪律

| 步 | 动作 | 证据要求 |
|----|------|---------|
| 1 | **先证明是否已合并，禁止直接重派/重跑** | 回执产出 vs 主数据 **逐条全字段**比对（不是只比 id / 前缀 / 条数） |
| 2 | **只汇报一次** | 文件字节数 / mtime / 计数；既有交付物（DOCX / HTML / md / bib）字节数未变 |
| 3 | **落一次末次台账** | 追加 `notes.md` 并写明「本批回执末次记账，后续同批重放静默处理」 |
| 4 | **中断≠无产出** | 先核对目标文件是否落盘，再决定是否重派 |

第 3 步是防止「每轮重放都重新占用用户注意力」的唯一有效手段——本例前 4 轮每次都重新核验+重新汇报，
第 5 轮才落台账并声明静默。

## 3. 全字段比对脚本（可直接复用）

> 教训：省钱不等于省证据。前 4 轮只比 id 前缀就下结论「已合并」，第 5 轮才做 10 字段全等比对——
> 结论相同但**证据强度不同**，用户对「你怎么证明」有要求时只有后者站得住。

```python
import json, hashlib
main = json.load(open(r"E:/MemOmics-Agent/results/<sid>/data/cards.json", encoding="utf-8"))
new  = json.load(open(r"E:/MemOmics-Agent/results/<sid>/data/deep_cards_round2_t0a.json", encoding="utf-8"))

key = lambda c: c.get("n") or c.get("title")
midx = {key(c): c for c in main}
same = [k for k, c in ((key(x), x) for x in new) if k in midx and midx[k] == c]   # 全字段相等
print(f"{len(same)}/{len(new)} 卡逐字段全等 -> {'零写入，无需动作' if len(same)==len(new) else '存在差异，需人工核对'}")
```

配套检查：

- `len([c for c in main if not c.get("deep_read")]) == 0` —— 确认主库无薄卡
- 每个交付物 `os.path.getsize()` 对照上一轮记录 —— 字节数未变即未被触碰

## 4. 系统注入的「路径不存在」可能是被截断

会话要求块曾报：

```
⚠️ 以下要求中的路径不存在，请向用户核实是否已更新/作废：
"E:\文献\AI\Closed-loop transfer enables a(E:\文献\AI\Closed-loop 不存在)
```

实际：路径在组装时**被截断**（丢了 `...yield chemical knowledge.pdf`），真实文件 24,214,769 B、
mtime 2026-10-02 01:10，同目录另有 `agent/` 子目录、共 9 个 PDF。

**处置**：收到此类告警 → `search_files(target="files", path=<父目录>)` 列目录 + 看大小/mtime → 再定论。
**禁止**把告警原样转述给用户当结论；**禁止**据此改名 / 删除 / 重建路径 / 把有效路径标作废。

## 5. 自检清单

- [ ] 本轮收到的 `deleg_*` 回执，是不是**同一个 id 第二次以上出现**？→ 先核对是否已合并，不要重派
- [ ] 比对用的是**全字段**还是只比 id/前缀？（后者不足以证明「零写入」）
- [ ] 中断的子任务目标文件真的不存在吗？
- [ ] 本轮汇报后，是否已写末次台账并声明后续静默？
- [ ] 系统报「路径不存在」时，有没有列父目录核实？（截断误判）