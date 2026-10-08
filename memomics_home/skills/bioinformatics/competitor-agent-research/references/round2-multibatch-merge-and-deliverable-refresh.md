# 多批次深读卡归并 → 合入 store → 重出交付物（2026-10-08 实测底稿）

> 场景：`results/memomics-be17649b`（科研 AI Agent 竞品定位）。用户指令 = **把 16 张首轮薄卡升级为深读卡**。
> 这一批经过**三轮派发**（一次全批蒸发、一次撞迭代上限、一次按用户「每写完一张立即落盘」重拆），
> 最终碎成 **4 个文件**。本文记录归并、硬门审计、合并、重渲染、交付物重建与终态断言的全量数字。

---

## 1. 批次链路（为什么会有 4 个文件）

| 轮次 | delegation | 分派 | 结果（磁盘实测） |
|---|---|---|---|
| 1 | `deleg_bfb03f20` | 3 任务（n=1,2,14–17 / 19–23 / 24,26,27,29,31） | ❌ `owner exited before recording a terminal result`，三个 live log 全部停在 20:15:44（正当「校验 evidence_quote 原文子串」一步）→ **磁盘零残留** |
| 2 | `deleg_c617920e` | 同 3 组，**强制落盘** | t1/t2 `completed`（→ `deep_cards_round2_t1.json` 5 卡 / `t2.json` 5 卡）；**t0 `max_iterations`** |
| 3 | `deleg_96407a20` | 把 t0 拆成 t0a(n=1,2,14) / t0b(n=15,16,17)，**每写完一张立即 dump** | 两任务 manifest 记 `interrupted`，但 **`deep_cards_round2_t0a.json` / `t0b.json` 各 3 卡完整落盘** |

⇒ **两个教训**：
1. 归并要收全部散件：`ls data/deep_cards_round2_t*.json` → 4 个文件、3+3+5+5 = **16 卡**，与 16 张薄卡一一对应。只认最后一批会漏 3 张。
2. **manifest 的 `status` 是声明、磁盘文件才是事实**：`interrupted` / `max_iterations` ≠ 产出不完整。判完整性看**文件**（字段数 / 字段长度 / 引文命中），不要凭 status 重派。

---

## 2. 引文硬门（内置进合并脚本，写入路径上的门）

```python
norm = lambda s: re.sub(r"\s+", " ", str(s)).strip()
corpus = {os.path.basename(p)[:-4]: open(p, encoding="utf-8", errors="ignore").read()
          for p in glob.glob(os.path.join(BASE, "data/text/PMC*.txt"))}      # 31 篇本地全文
q_n, t_n = norm(card["evidence_quote"]), norm(corpus.get(card["pmcid"], ""))
ok = bool(q_n) and bool(t_n) and q_n in t_n
if not ok:
    rejected.append(n)          # ⇒ 该字段拒写，保留旧值，报告里点名
```

实测：**16/16 exact、`rejected=[]`**（审计落盘 `log/round2_quote_audit.json`）。

---

## 3. 合并（`scripts/merge_round2_deepread.py`，本 skill 同名脚本可直接复用）

- 源：4 个散件（顶层 `{"cards": {n字符串: {...10 字段...}}}`）
- store：`data/cards.json`，**顶层是 `list[dict]`（键在元素里），不是 dict** —— 先 `print(type/len/首元素 keys)` 再写逻辑
- 备份：`data/cards_v3_snapshot.json`（首次才建）
- 硬门：见 §2；`evidence_quote` 拒写时该字段跳过，旧值另存 `evidence_quote_v1`
- 冻结标记：`deep_read=True` / `deep_read_round="2026-10-08"` / `deep_read_pass="round2"` / `deep_read_date=TS`
- 报告：`log/round2_merge_report.json`（逐卡 `filled` / `skipped` / `grew`）

### 升级前后（16 卡，10 字段总字符）

| n | before | after | 最显著变化 |
|---|---|---|---|
| 1 | 1713 | 3714 | arch 373→1318；validation 271→520 |
| 2 | 1686 | 3686 | **limitations 8→522**（截断修复） |
| 14 | 1342 | 2894 | arch 456→1204 |
| 15 | 1489 | 2997 | arch 506→1431 |
| 16 | 1362 | 2476 | arch 596→1297 |
| 17 | 2142 | 3326 | arch 880→1510 |
| 19 | 1267 | 3138 | arch 365→1587；models 95→297 |
| 20 | 1415 | 2554 | arch 619→1151；models 93→231 |
| 21 | 1817 | 3267 | models 85→413；validation 52→102 |
| 22 | 1779 | 3055 | bench 400→736 |
| 23 | 1278 | 3044 | arch 383→1353；evid 181→393 |
| 24 | 2296 | 3515 | arch 642→1287；validation 182→415 |
| 26 | 901 | 2381 | models 19→245；bench 5→73 |
| 27 | 1597 | 3135 | bench 258→520；validation 165→512 |
| 29 | 1684 | 2941 | bench 387→598 |
| 31 | 1028 | 2421 | limitations 55→341 |

**合计 24,796 → 48,544 字符（+23,748，+95.8%）**；全库 31 卡 `deep_read=true`、**0 薄卡**。

---

## 4. md 附录重渲染（`scripts/upgrade_deepread_v4.py`）

- **两类处理**：round2 的 16 张 → **从 `cards.json` 整节重渲染**（单源真相）；其余 15 张 → **只替换那一行代次标记**
  （`^\*（[^）]*(?:深读|精读)[^）]*）\*$` → `*（深读升级 · 2026-10-07 · 全文重读 10 字段）*`）
- 章节边界：`^### A(\d+)\.` 的 `m.start()`，下一节起点 = 本节终点，最后一节到 `\n## `
- 备份：`deliverables/positioning_full.md.bak_pre_v4`（首次）
- 实测：`148,814 → 172,448` 字符（+23,634）；`rerendered=16`、`relabelled=15`、**残留旧标注行 0**

---

## 5. 交付物重建

```bash
# DOCX —— 先用带 python-docx 的解释器（项目 .venv 本轮没有）
for p in "$(which python)" "$(which python3)" "E:/MemOmics-Agent/.venv/Scripts/python.exe"; do
  "$p" -c "import docx;print('$p OK')" 2>/dev/null; done
python scripts/md2docx.py deliverables/positioning_full.md \
  "deliverables/MemOmics_科研AI_Agent领域定位报告.docx" \
  "科研 AI Agent 领域全景与 MemOmics 发文定位" \
  "31 篇全文精读竞品卡（round2 深读升级 16 篇 + 深读升级 15 篇）· 证据表 97 条 · 检索窗口 2024-01 → 2026-10"
# HTML —— 卡片直接读 cards.json，重跑即自动升级（只需同步副标题口径）
E:/MemOmics-Agent/.venv/Scripts/python.exe scripts/build_report_html.py
```

| 交付物 | before | after |
|---|---|---|
| `positioning_full.md` | 245,154 B（148,814 字符） | **299,145 B（172,448 字符）** |
| DOCX | 769,470 B / 708 段 / 15 表 | **793,395 B / 708 段 / 15 表 / 3 图** |
| HTML | 1,180,780 B | **1,233,970 B**（31 卡 / 3 内嵌图） |

未动：3 张图（landscape_stats 未变）、`evidence.csv` 97 行（round2 未附新证据行）、`references.bib` 69 条。

---

## 6. 终态断言（产出到产物本身上，双向）

```
HTML 徽标分布 : 16×'class="drd">全文精读 round2 · 2026-10-08' + 15×'…2026-10-07'   ✔ == 各批卡数
旧标记归零    : grep -c "首轮合并 2026-10-02"   → 0                                  ✔
截断缺陷归零  : 搜 "作者自陈：物理能"             → 0                                  ✔
DOCX 图片     : len(doc.inline_shapes)=3, word/media/ = image1..3.png                ✔
DOCX 结构     : paragraphs 708 / tables 15                                            ✔
DOCX 副标题   : "31 篇全文精读竞品卡（round2 深读升级 16 篇 + 深读升级 15 篇）· 证据表 97 条…" ✔
```

🔴 **只查「新在」不够，必须同时查「旧不在」** —— 本轮 4 条"存在断言"全过，真正的价值在那 3 条归零断言上。

---

## 7. 汇报口径（用户认的形状）

给用户的话里必须包含：① 哪些回执是**迟到重放**（零动作）；② 真实待办是什么（4 个散件落盘）；
③ 硬门数字（16/16 引文命中）；④ **before→after 数字表**；⑤ 终态断言结果；⑥ 一处环境事实
（DOCX 用系统 Python 重建，`.venv` 无 python-docx）+ 一句「要不要装进项目 `.venv`」的询问。
⛔ 不提「我修好了 bug」，只陈述实测值。

---

## 8. 归并之后的**重放轮**：对账目标是终态 store，不是「再合一遍」（2026-10-08 实测）

归并完成后，同一批 `deleg_96407a20` / `deleg_58d8c19a` 的**回执迟到重放**会再次到达（本轮同一唤醒里**两条并存**）。
这一轮的正确形态是**只读对账 + 零写入**，别把 §3 的合并脚本再跑一遍。

| 项 | 做法 / 实测 |
|---|---|
| 判定入口 | 回执台账 `grep -n "deleg_" results/<sid>/notes.md` 命中且交付物字节数与当前一致 ⇒ 一跳定案 |
| 对账口径 | **散件 ↔ 终态 store 逐字段逐字 diff**（10 字段 + 长度指纹）。`t0a`(21,729 B, n=1/2/14) / `t0b`(19,286 B, n=15/16/17) ↔ `cards.json` → **6/6 一致**，`architecture` 字符数 1318/1544/1204/1431/1297/1510 全对 ⇒ 零写入 |
| 回执头部不可信 | `deleg_96407a20` 记 `status=interrupted, 0s` / 无 summary，但散件**完整落盘且早已被 §3 消费** ⇒ 对**磁盘**下结论，⛔ 不对回执标签下结论（§1 教训 2 的延伸） |
| 🔴 快捷判据失效 | 「文件名编码批次 id」（`deep_cards_deleg_<id>.json`）对本批**不适用**——输出路径是用户点名的 `deep_cards_round2_t0{a,b}.json` ⇒ 必须回退逐字段 diff |
| ⛔ 不许重合并 | 同一批重合并会覆盖 store 条目，且代次字段（`deep_read_round` / `_pass` / `_date` / `_batch` 逐轮在变）与容器口径与首次合并时未必相同 ⇒ 静默污染 |

**终态复核断言（可直接复用）**：`cards.json` = **31 卡** / `deep_read=True` **31/31** / **薄卡(<300 字) = 0** /
`deep_read_round` 分布 **10-08=16 + 10-07=15** / id 全集 `1,2,4–12,14–17,19–24,26,27,29,31,33–36,41,45`。

**收尾**：只留**两个待用户定夺项、各一行**（⛔ 不重复弹窗——同一问题每轮弹一次，用户会当成新问题）：
① `pip install python-docx` 进项目 `.venv`（§5 的环境事实，按铁律「先问再装」）；
② `E:\文献\AI\Closed-loop transfer …chemical knowledge.pdf`（24.2 MB、**实测存在**、不在 31 卡内）是否补成第 32 张。