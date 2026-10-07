# 交付物组装与内容核验（Deliverable assembly & verification）

> 来源：2026-10-02 竞品定位交付会话（31 张竞品卡 + 证据表 + DOCX/HTML 报告）。
> 本文件收录**组装多件套交付物**时的四个坑（其中两个会让 `rail_review(post)` 误判 failed，
> 一个会让"内容核验"给出**假阴性**）。

---

## 1. 🔴 `rail_review(post)` 第五种错法：图在**兄弟目录**，`output_dir` 指了交付目录 → 判 failed

**现象**：`passed=false`，`issues=["未生成任何图片 — 每步至少 1 张图"]`，`figure_count=0`，
而 3 张图（PNG+PDF+SVG）明明都在 `figures/`。

**根因**：扫描器只数 **`output_dir` 这一层**的图片文件。组件型会话里图在 `figures/`、
文档在 `deliverables/`，传后者必然 0 张。这是已知第五种错法（前四种见 SKILL.md 坑表：
传文件路径 / 传共享大目录 / 纯数据步骤 / 传只有一半产物的子目录）。

**正解 —— 让交付目录自包含（这一步同时提升了交付质量，不是凑数）**：

```python
import os, shutil
os.makedirs("deliverables/figures", exist_ok=True)
for base in ["Fig1_landscape_and_funnel", "Fig2_positioning_matrix", "Fig3_capability_vs_credibility"]:
    for ext in [".png", ".pdf", ".svg"]:
        s = os.path.join("figures", base + ext)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join("deliverables/figures", base + ext))
for f in ["references/references.bib", "references/references.ris", "review/evidence.csv"]:
    if os.path.exists(f):
        shutil.copy2(f, os.path.join("deliverables", os.path.basename(f)))
```

再 `rail_review(phase="post", output_dir="<deliverables 目录>", code_executed=<完整脚本>)`
→ 实测 `figure_count=6, passed=true`。

**为什么这条比"改 output_dir 指回 `<sid>` 根"更好**：本会话的交付意图就是**给别人一个文件夹**。
把图/引用库/证据表复制进 `deliverables/`，用户拷走整个目录即可用（DOCX 里的相对路径图、
HTML 里的内嵌图、`references.bib` 全都齐）。⛔ 属**产物口径类**，**不要重跑报告生成脚本**。

---

## 2. 🔴 核验 `.docx` 是否含某段中文：**字节搜索会给假阴性**

**现象**：`open(p,'rb').read()` 后搜 `'先例逐字差异表'.encode('utf-8')` → `False`，
据此差点汇报"DOCX 缺附录 F"。而实际**内容就在里面**。

**根因**：`.docx` 是 zip，正文在 `word/document.xml`；
python-docx / Word 会把一段文字**切成多个 `<w:r>` run**（字体、语言、修订痕迹都切），
所以连续中文串在 XML 字节流里**可能被标签打断**，直接字节搜必然漏。

**正解 —— 解 XML、去标签、再判定**：

```python
import zipfile, re
xml = zipfile.ZipFile(docx_path).read("word/document.xml").decode("utf-8", errors="replace")
txt = re.sub(r"<[^>]+>", "", xml)          # 去标签得纯文本
for probe in ["附录 A", "附录 F", "先例逐字差异表", "Evidence-Gated Memory", "BIOGEN"]:
    print(probe, "->", "✓ 在" if probe in txt else "✗ 缺")
```

备选（有 python-docx 时）：`"".join(p.text for p in Document(p).paragraphs)` +
遍历 `doc.tables` 的单元格 —— 与 SKILL.md #18 的「DOCX 端用 paragraphs + tables 拼全文再 count()」同法。

**判据**：**凡在二进制容器（docx/xlsx/pptx/pdf）里核验文本，一律先解容器取内容流，
禁止对原始字节做子串搜索**。同类假阴性家族：`search_files` 对中文路径/中文 pattern 返回 0。

---

## 3. 🔴 改写**共享中间文件**时，容器形状不能变

**事故**：`data/cards.json` 原本是 **list**；我把合并结果写成
`{"cards":[...], "evidence":[...]}` 的 **dict** —— 下游 `assemble_full_doc.py` 里
`sorted(cards)`、`build_report_html.py` 里按 list 遍历**当场崩**，而报错点离事故点很远
（先怀疑"脚本坏了"，实际是我改了数据契约）。

**正解**：
```python
raw  = json.load(open(path, encoding="utf-8"))
shape = "dict" if isinstance(raw, dict) else "list"        # 记住原形状
...
payload = final if shape == "list" else dict(raw, cards=final)   # 按原形状写回
json.dump(payload, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
```
新增的附属数据（如合并后的 evidence 数组）**另存新文件**（`data/evidence_merged.json`），
不要把新字段塞进老文件改变其形状。

**判据**：**共享中间文件的形状是隐式契约** —— 改它之前先 `grep` 一遍谁在读
（`search_files(pattern="cards.json")`），并保持兼容；形状确实要变就同时改所有消费方。

---

## 4. `md2docx.py` 的两个操作细节

- **必须传两个参数**：`md2docx.py <in.md> <out.docx>`；不带参数直接跑
  → `IndexError: list index out of range`（看着像脚本坏了，其实是签名要求两个 argv）。
- **要用带 python-docx 的解释器**：本会话实测**项目 `.venv/Scripts/python.exe` 没有 docx**、
  `E:/release/__stage_python` 也没有，而 **`E:/miniconda3/python.exe`（conda base）有**。
  ⚠️ 与 SKILL.md 坑表里"python-docx 在共享库 `D:/Python/site-packages`、Python312 可见"
  那条**不完全一致** —— 说明**该包的位置随机器/时期变动，不要照抄某个具体解释器**。
  **正确姿势 = 按顺序探测**（一次调用探完，不要逐个来回试）：

  ```python
  import subprocess
  for py in [r"E:/MemOmics-Agent/.venv/Scripts/python.exe",
             r"E:/miniconda3/python.exe",
             r"C:/Users/<user>/AppData/Local/Programs/Python/Python312/python.exe"]:
      r = subprocess.run([py, "-c", "import docx"], capture_output=True, text=True)
      print(py, "->", "OK" if r.returncode == 0 else "no docx")
  ```

  拿到可用的就调它跑 md2docx，**不要为此往 `.venv` 装 python-docx**（铁律 29：装包需用户同意，
  且这里只是解释器选错，不是缺包故障）。
- **成功回执形如** `OK: 737,669 bytes | 676 paras | 15 tables` —— **记下字数与表数**，
  它是后续"内容真的进去了吗"的对照基线。

---

## 5. 收尾：一次批量探针，不要逐件分轮核验

多件套交付（DOCX + HTML + MD + bib + ris + csv + 9 张图）的验收**写成一个 `execute_python`**
一次打印全部判据，避免"逐项核对"触发循环检测：

```
竞品卡张数 / 带 evidence_quote 数 / 带 implication 数
证据表条数 / 覆盖 DOI 数 / strength 分布
references.bib 条目数（re.findall(r'^@', bib, re.M)）
正文附录计数（附录 A 卡数 / 附录 B 证据行数 / 附录 C·D·F 是否在）
DOCX: 大小 + PK 头校验 + 解 document.xml 后核关键串
HTML: 大小 + 卡片数 + <img> 数
交付目录: PNG/PDF/SVG 各几张 + 文件总清单
```

⛔ 不要"核验完再回头确认一次"。⛔ 判据一律**从文件读，不从记忆报**。