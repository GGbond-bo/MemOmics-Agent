# 产物不是 JSON card store 时的重放判定（Markdown 摘要 + 知识库 YAML）

适用：子代理做的是**文献/资料结构化提取**（每份产出是 Markdown 结构化摘要），主代理合并成
**一份 Markdown 交付物** + 若干 **知识库 YAML 条目**（`save_knowledge` 落盘）。
此形态下 §二 的 5 项 diff、⓪ 溯源字段、0-ter 散件三形状**全部无对象可跑** ——
本文给出**等价强度**的替代证据链，并附一次探针取完所有数字的脚本。

> 首次实测：2026-10-12，`results/memomics-75ba0499`（9 篇科研 AI agent 文献 → 合读交付物 + KB `ai_agent/`）。
> 两条回执同轮到达：`deleg_e78e9cbd`（3 任务）+ `deleg_8e3e2dac`（2 任务）。

---

## 一、四条替代证据（一次探针取完，⛔ 不要逐项分轮核对）

| 项 | 判据 | 本例实测值 |
|---|---|---|
| ① 落盘件 mtime 时序 | 该批**全部**子代理落盘件 mtime **早于**交付物 mtime ⇒ 交付物必然已消费该批 | Biomni_结构化摘要.md 18,694 B@17:54 · paper_structured_summaries.md 25,566 B@17:53 · _结构化提取_两篇论文.md 23,674 B@17:55 · AI摘要_paper2Agent_CASSIA.md 44,224 B@18:00 · AI摘要_ChemCrow_ScienceBuddy.md 32,186 B@17:59 **全部 < 交付物 18:32** |
| ② 交付物内容覆盖 | 该批**专有专名 + 精确数字**在交付物里子串命中（⛔ 不用语义词，见 §二 检查 3 的口径卫生） | 9 个系统名（Biomni/Co-Scientist/DeepRare/ChemGraph/BioMaster/Paper2Agent/CASSIA/ChemCrow/ScienceBuddy）+ §8 矛盾表 + §11 辩论记录全命中 |
| ③ 产物形态健康 | 交付物行数/字节 + KB YAML 逐条字段长度 | 交付物 **251 行 (`wc -l`)** / 23,801 B / sha256 `4e726baa022760bc`；KB **12 条 YAML** 全通过（同域另有 `00_INDEX.md` ⇒ 目录共 13 件） |
| ④ 闭环计数 | 子代理任务数 == 落盘件数 == 交付物覆盖条目数 | 5 任务 ↔ 5 落盘件 ↔ 9 篇（合读）↔ 12 条 KB 条目（9 篇 + 3 条横向综合） |

四条同向 ⇒ **判迟到重放，零写入收场**（数据/交付物/KB 一个字节不动，只追加台账行）。

## 二、KB YAML 字段健康阈值与「先 print 键」纪律

本库（`memomics/knowledge_base/`，`save_knowledge` 落盘）条目的**实际顶层键**：

```
type, domain, name, subcategory, last_updated, source, verified, quality,
auto_trigger, content, evidence, conflict_status, contradiction_count,
contradictions[], citation_caution
```

- 「一句话定位 / 研究思路 / 解决问题 / 工作量 / 测试方式 / 关键数字 / 局限 / 可复用点」
  **是 `content` 正文里的中文小节标题**，⛔ **不是 YAML 键**。
- 健康阈值（实测口径）：`content ≥ 800 字` 且 `evidence ≥ 40 字` ⇒ 通过；
  另查 `conflict_status` / `contradiction_count` 已写（原文数字自相矛盾的条目必须带）。
- 🔴 **踩点（2026-10-12）**：拿自编键名当「必需字段」扫描 ⇒ **12/12 全报缺字段**，纯假阳性。
  与 §二 ⓪-d「廉价启发式在本库假阳性率高」同源、与检查 0「形状没确认前不许写比对逻辑」同一纪律，
  只是从 JSON store 延伸到 YAML 条目。
- 本例健康画像（12 条）：content 3,371–7,018 字 / evidence 284–436 字 / verified 12/12 /
  conflict_status 12/12（`unresolved` 7、`none_found` 5）/ 矛盾合计 19 条 / 无截断无空字段。

## 三、探针脚本（照抄即用；持久内核可能是新建的 ⇒ 脚本自包含、第一步重新读盘）

```python
import os, io, glob, time, hashlib, yaml

R    = r"E:\MemOmics-Agent\results\<sid>"
deliv = os.path.join(R, "results", "<交付物>.md")
notes = os.path.join(R, "notes.md")
KB    = r"E:\MemOmics-Agent\memomics\knowledge_base\<domain>"   # 例：...\ai_agent

def fp(p):
    b = open(p, "rb").read()
    return len(b), hashlib.sha256(b).hexdigest()[:16], time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(p)))

print("交付物", fp(deliv), "lines=", sum(1 for _ in open(deliv, encoding='utf-8')))

# ① 落盘件时序（把回执里每个任务的落盘件列进来）
for p in ["<subagent_output_1>.md", "data/<subagent_output_2>.md"]:
    q = os.path.join(R, p.replace('/', os.sep))
    print(f"  {p:42s}", fp(q) if os.path.exists(q) else "MISSING")

# ② 台账：区分「派发行」与「核销行」（§二 ⓪-i）
for i, l in enumerate(open(notes, encoding='utf-8'), 1):
    if 'deleg_' in l or 'replay' in l or '核销' in l:
        print(i, l.rstrip()[:150])
print("notes bytes:", os.path.getsize(notes))

# ③ KB 健康：先 print 实际键，再写逻辑
ys = sorted(glob.glob(os.path.join(KB, "**", "*.yaml"), recursive=True))
print("样本顶层键:", list(yaml.safe_load(open(ys[0], encoding='utf-8')).keys()))
rows, short = [], []
for y in ys:
    d = yaml.safe_load(open(y, encoding='utf-8'))
    r = dict(f=os.path.relpath(y, KB), content=len(d.get('content', '') or ''),
             evidence=len(d.get('evidence', '') or ''), ver=d.get('verified'),
             cs=d.get('conflict_status'), cc=d.get('contradiction_count'))
    rows.append(r)
    if r['content'] < 800 or r['evidence'] < 40:
        short.append(r)
print(f"YAML 数={len(rows)}  短/空字段={short or '无'}")
print("verified 分布:", {v: sum(1 for r in rows if r['ver'] == v) for v in set(r['ver'] for r in rows)})
print("conflict_status 分布:", {v: sum(1 for r in rows if r['cs'] == v) for v in set(r['cs'] for r in rows)})
print("矛盾合计:", sum(r['cc'] or 0 for r in rows))

# ④ 台账追加（核销行单独成节，带 replay#N + 指纹，见 §二 ⓪-i）
```

## 四、台账核销行模板（写进 `notes.md`，下一轮 grep 才能一跳定案）

```
## [replay 台账 · <YYYY-MM-DD>] 子代理回执核销（N 条同轮到）

- `deleg_<id>` 回执核销 — **replay#1**（k 任务：<每任务覆盖什么>）
- 判定：**迟到重放，早已合并**。回执头 `Dispatched … (Nm ago)` 为渲染假象（实际派发 <时刻>，交付物 <时刻> 已冻结）。
- 证据链层级：**交付物 ↔ 子代理落盘件时序** + **KB YAML 字段健康扫描**（浅层；本任务产物是 Markdown 摘要 + YAML，无逐字段 JSON diff 可做）
- 指纹：交付物 <路径> = <字节> B / sha256:<前16位> / <行数> 行（<mtime>）
- 落盘件（全部早于交付物）：<file> <字节> B@<HH:MM> …
- KB 健康：<域>/ <N> 条，content <区间> 字 / evidence <区间> / verified N/N / conflict_status N/N（unresolved x、矛盾合计 y）→ 无截断、无空字段、无待报缺陷
- **零写入**：交付物与 KB 一个字节未动，仅本行台账
```

⚠️ 派发行（`grep deleg_` 会命中的旧那种「N. 子代理并行做提取（deleg_xxx: …）」）**保持原样、不要改**
—— 它是**派发侧**记录，语义不同；核销行单独成节（§二 ⓪-i）。

---

## 五、二轮实测补遗（2026-10-12 第二批回执：`deleg_1f7a6a84` + `deleg_e78e9cbd` replay#2）

同一天的第二批回执（**同一交付物、不同 deleg_id**）暴露了四条上轮没写进的坑，全部已在 §二 ⓪-k 立项，
此处存实测值与可复用写法。⛔ 探针脚本已固化进 `scripts/probe_replay_nonjson.py`，照跑即可。

### 5.1 单层 `ls` 的 MISSING 是伪警报（本轮差点据此报「交付物丢了」）

| 探针位置 | 结果 | 真相 |
|---|---|---|
| `results/memomics-75ba0499/AI_agent_前沿工作解读.md` | `MISSING` | 不在会话根这一层 |
| `find . -name "AI_agent_前沿工作解读.md"` | `./results/memomics-75ba0499/results/AI_agent_前沿工作解读.md` | **嵌套两层 `results/`** |

⇒ 真实指纹：**23,801 B / 251 行 (`wc -l`) / 18:32:58**。
⚠️ 根因是**台账基线含糊**：核销行写的是 `results/AI_agent_前沿工作解读.md`，从会话根看少了一层 `results/`。
⇒ 写台账/锚点时写**绝对路径**，或至少写全 `results/<sid>/results/<file>`；否则每轮都要靠 find 兜底。

### 5.2 `wc -l` 口径差 → 伪 Δ（252 vs 251）

上轮台账「252 行」，本轮 `wc -l` = **251**；而**字节数 23,801 B 与 sha256 `4e726baa022760bc` 分毫不差**
⇒ 文件**没变**，只是行数没标口径（`wc -l` 数换行符，末行无换行则少 1）。
⇒ 判据：**sha256/字节是权威；行数是次级量，差 1 属计数约定，不是内容变化**。
台账行已就地更正为 `251 行 (wc -l)` 并注明原因 —— 下轮重核不会再产出伪 Δ。

### 5.3 反向封闭（新增第 ⑤ 条证据）

`find results/<sid> -newermt "<交付物 mtime>" -type f | grep -v /log/`
⇒ 实测非空，但只剩 `.loopx/goals/<sid>/runs/*.json|.md`（**框架自身的 goal 运行快照，不是交付物**）
⇒ 写成「此后无未消费产物，仅 loopx 快照」即算封闭成立。
`data/` 三件全部 17:53–18:00 早于交付物 18:32:58 ⇒ 双端（前向消费 + 后向无新增）都闭合。

### 5.4 台账查不到 deleg_id ≠ 未合并

本轮 `deleg_1f7a6a84`（first arrival）在 `notes.md` 里**没有任何核销行**（grep 只命中上轮的 `deleg_e78e9cbd`），
但它照样**直接判重放**：落盘件 `data/AI摘要_paper2Agent_CASSIA.md` 44,224 B @18:00:05 **早于**交付物 18:32:58，
且 9 个系统名在交付物里命中 **11–19 次**
（paper2Agent 19 · Biomni 18 · ScienceBuddy 16 · CASSIA 16 · ChemCrow 14 · Scientist 14 · DeepRare 14 · ChemGraph 12 · BioMaster 11）。
⚠️ 为什么台账没命中：**同一交付物的批次任务可重叠** ——
`deleg_1f7a6a84` = paper2Agent+CASSIA、`deleg_8e3e2dac` = CASSIA+ChemCrow / paper2Agent+ScienceBuddy
（**CASSIA 与 paper2Agent 各出现在两批里**）。
⇒ 判重放的锚点只能是「**交付物是否已消费该批落盘件**」，⛔ 不是「这个 deleg_id 见过没有」。

### 5.5 系统注入的「路径不存在」警告：第二形态

本批会话要求块一次报了 **5 条**「路径不存在」，形态是**路径串自我嵌套**（非上轮的「被截断」）：
`"E:\文献\AI\agent\literature\10.1038_s4158(E:\文献\AI\agent\literature\10.1038_s41586-025-10097-9.pdf" 不存在`
⇒ 判据：**把「不存在」的串按 `(` 切开，括号里又出现一条完整路径 ⇒ 渲染伪影**。
批量实查该目录 9 篇 PDF **全部在位**：`paper2Agent.pdf` 14,067,355 · `10.1038_s41586-025-10097-9.pdf` 9,891,107 ·
`Biomni.pdf` 8,715,906 · `CASSIA.pdf` 6,995,718 · `2609.17523v1.pdf` 5,830,631 · `Co-Scientist.pdf` 5,121,974 ·
`10.1038_s42256-024-00832-8.pdf` 2,396,611 · `BioMaster.pdf` 1,432,158 · `ChemGraph.pdf` 1,054,960（单位 B）。
⇒ 一行更正 + 台账销账；⛔ **伪影的判据是形态，不是条数**（5 条不算「多到像真的」）。

### 5.6 KB 目录实况（按域复查）

`memomics/knowledge_base/ai_agent/` = **13 件** = 12 YAML + `00_INDEX.md`；
分子目录：`frameworks/` 7 · `agent_design/` 2 · `overview/` 1 · `benchmarks/` 1 · `evaluation/` 1。
⇒ 报「KB 条数」时说清**是否含 `00_INDEX.md`**，否则与上轮数字对不上会让人以为丢了一条。