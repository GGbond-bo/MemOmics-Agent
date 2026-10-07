# 深度卡合入交付物与报告重出（模式 C10 全流程）

> 来源：2026-10-07 会话（results/memomics-be17649b）。3 个子代理各精读 5 篇，回 15 张深度卡；
> 主代理负责回收 → 合并 → 附录重渲染 → HTML/DOCX 重出 → 校验。15 张卡一次跑通。

## 0. 一句话流程

```
delegation 结果消息 → (state.db 回收) → 五级解析 → 键归一化 → 合并进 cards.json（快照+标记）
   → 附录 md 章节重渲染（.bak_v1）→ 重跑 HTML 生成器 + DOCX 转换器
   → 同步 evidence.csv 到 deliverables/ → 探针式机械校验
```

## 1. 回收：live transcript 不可用，但 state.db 可以

| 来源 | 内容 | 可用性 |
|---|---|---|
| `cache/delegation/live/<deleg_id>/task-N.log` | 流式片段，JSON 被截成 2–3KB（完整约 30KB） | ❌ 不可解析 |
| 子代理自身 session 的 assistant 消息 | 分批残片（最长一条 16KB，仍是 part 2） | ❌ 不完整 |
| **`hermes_home/state.db` 的 `messages`（唤醒消息本体）** | 合并后的完整结果文本（本次 49,253 chars） | ✅ 全文 |

```python
con = sqlite3.connect(r"E:/MemOmics-Agent/hermes_home/state.db")
rows = con.execute(
    "SELECT id, session_id, role, length(content) FROM messages "
    "WHERE content LIKE ? ORDER BY length(content) DESC LIMIT 5",
    (f"%{unique_phrase}%",)).fetchall()
```
- `unique_phrase` 用卡里**一句中文原话**（如 `MCP 原生层级化`）——比英文标题更独特。
- 同一批结果在 messages 里可能有 2 条（同一 session 重复注入），取 `length(content)` 最大的那条。
- ⚠️ 表有 1GB 级，务必带 `LIMIT` 与唯一短语，别全表扫。

## 2. 解析：五级回退（C8 的第四级 + 本次新增第五级）

| 级 | 处理 | 现象 |
|---|---|---|
| 1 | 原样 `json.loads` | 少数干净块 |
| 2 | **裸引号修复**（本次新增） | `Expecting ',' delimiter` —— 中文字符串里写了 ASCII `"`（`提出"MCP 原生…"框架`） |
| 3 | 去尾随逗号 `re.sub(r",\s*([}\]])", r"\1", s)` | LLM 手写 JSON 通病 |
| 4 | 尾部裁剪 + 试闭合后缀 | 输出长度截断 |
| 5 | 栈式花括号配对逐对象抢救（字符串态内的 `{}` 不参与配对） | 前四级全挂时兜底 |

`fix_quotes` 判据（本次救回 3 块中的 2 块）：

```
字符串态内遇到 '"' → 向后跳过空白看下一个字符
   ∈ {',', '}', ']', ':'} 或已到末尾  ⇒ 这是闭合引号
   否则                             ⇒ 这是字面量，转义成 \"
```

现成实现：`scripts/merge_deep_cards.py` 的 `fix_quotes()` / `parse_json_blocks()`。

## 3. 键归一化（静默失败点）

三个子代理用了三种顶层键：`"4"`（纯数字）、`"n=9"`（带前缀）、`"34"`。
不归一化 → `deep.get(str(n))` 全 miss → **升级 0 张且不报错**。用 `int(re.search(r"\d+", k).group())`。

## 4. 合并（不动容器形状）

- 先快照：`data/cards_v1_snapshot.json`
- 10 字段覆盖：`architecture / inputs / outputs / models / benchmark / validation / key_claim / novelty / limitations / evidence_quote`
- 旧引文挪 `evidence_quote_v1`（审计要留原引）
- 打标 `deep_read / deep_read_batch / deep_read_at` → 下游渲染「深读 v2」徽标
- 顺手补系统名：本次 n=36 薄卡名只有「多智能体 LLM 单原子催化剂设计」，深读文里有 `MAESTRO` → 改为 `MAESTRO（…）`，旧名存 `name_v1`；md 章节标题同步改
- 本次实测增量：architecture +15,433 字符、benchmark +5,196、limitations +2,813、models +2,815（薄卡 architecture 仅 48–124 字 → 深读 775–1,560 字）

## 5. 附录 md 章节重渲染

按 `^### A(\d+)\.` 的 `m.start()` 建边界：`end = 下一节起点`（最后一节到 `\n## `）。只替换命中的 n。
每章首行加代次标记：`*（v2 深读升级 · 2026-10-07 · 全文重读 10 字段）*`。
本次：114,411 → 148,064 字符，31 章节数不变（校验用 `len(re.findall(r"^### A\d+\.", md, re.M))`）。

## 6. 报告重出

```bash
# HTML：卡片直接读 data/cards.json ⇒ 重跑即自动带上深读内容
python scripts/build_report_html.py
# DOCX：读 md 母本
python scripts/md2docx.py deliverables/positioning_full.md deliverables/<报告>.docx "标题" "副标题"
```

- 🔴 **同步 `review/evidence.csv` → `deliverables/evidence.csv`**（本次 deliverables 那份仍是旧 72 行；用户两份都会打开）。
- HTML 卡片可加深读徽标：在 `card_html()` 里 `{'<span class="drd">深读 v2</span>' if c.get('deep_read') else ''}` + `<style>` 内 `.drd{...}`。

## 7. 校验探针（一次跑完，别逐张分轮）

```python
z = zipfile.ZipFile(docx); xml = z.read("word/document.xml").decode("utf-8")
assert len([i for i in z.namelist() if i.startswith("word/media/")]) >= 3      # 图没掉
h = open(htmlp, encoding="utf-8").read()
assert h.count('class="drd"') == n_deep                                       # 徽标数 == 深读卡数
for kw in ["固定流水线 + 迭代实验", "双 RAG", "OntoReaction", "BioLORD", "MCPCreator"]:
    assert kw in xml and kw in h                                              # 深读特有专名
```
（探针要用**深读特有专名**，用通用词会假阳性。本次 `UMA(OC20)` 未命中属正常——原文写的是 `UMA（… 'OC20' 域）`。）

## 8. 两个脚本坑（本轮各栽一次，已修）

### 8.1 往 f-string 模板注入 CSS 必须转义花括号

```python
# ✗ 注入后：<style>{CSS}.drd{display:inline-block;...}</style>
#   → NameError: name 'display' is not defined   （{display:...} 被当 f-string 表达式）
# ✓ 正确：.drd{{display:inline-block;...}}
```
报错点（HTML 生成阶段）离事故点（一行 CSS）很远。**生成脚本突然 NameError 时，先检查自己最近替换进去的那段文本**。

### 8.2 `str.replace` 会替换全部匹配，且不保证落点

用 `src.replace("</style>", ...)` / `src.replace("def card_html(c):", ...)` 打补丁时，注入行可能落到文件顶层 ⇒ `IndentationError`（且报错行号指向无关代码）。
修法：**regex 按行改 + `ast.parse()` 断言**再继续：
```python
fixed = re.sub(r"(?m)^[ \t]+def card_html\(c\):", "def card_html(c):", raw)
ast.parse(fixed)          # 语法断言通过再写回
```
不要对同一个 replace 反复重试。

### 8.3 md2docx.py 的图片路径只试了 `../`

原实现 `os.path.join(md_dir, "..", pth)`：md 母本在 `deliverables/`、图在 `deliverables/figures/` 时，会解析到 `results/figures/` 而**静默显示 `[缺图: …]`**（DOCX 仍生成、无报错）。
修法：**同目录优先，再退 `../`**：
```python
d = os.path.dirname(os.path.abspath(md_path))
cand = [os.path.join(d, pth), os.path.normpath(os.path.join(d, "..", pth))]
pth = next((c for c in cand if os.path.exists(c)), cand[0])
```
验证：生成后 `zipfile` 数 `word/media/`（>0 才算图真的嵌入）。

### 8.4 用「已有 python-docx 的解释器」跑 md2docx

本次 `.venv` 里没有 `python-docx`，而系统 Python 3.12 里有 ⇒ **用系统解释器跑这一次转换**，不要为了跑它去装包（用户环境优先级，见铁律 29）。探测：
```bash
python -c "import docx, sys; print(sys.executable)"
```
（DOCX 转换是单次文档操作，不承担「terminal 冷启动 python 跑分析」的性能禁忌。）

## 9. 本轮交付物基线（可作下次对照）

| 文件 | 大小 | 说明 |
|---|---|---|
| `deliverables/MemOmics_科研AI_Agent领域定位报告.docx` | 769,200 B | 692 段 / 15 表 / 3 图（media 验证） |
| `deliverables/MemOmics_科研AI_Agent领域定位报告.html` | ~1.17 MB | 15 处「深读 v2」徽标 / 31 卡 / 87 证据 / 69 引用 |
| `data/cards.json` | ~162 KB | 31 卡，15 张 `deep_read=true` |
| `review/evidence.csv` | 87 行 | +15 条 deep-read 逐字佐证 |
| 备份 | — | `positioning_full.md.bak_v1`、`cards_v1_snapshot.json`、`deep_cards_deleg_*.json` |