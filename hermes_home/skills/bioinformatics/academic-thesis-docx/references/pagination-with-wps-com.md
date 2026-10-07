# 用办公套件的 COM 接口取论文**真实分页**（目录 / 插图清单 / 附表清单页码）

> 触发：论文 DOCX 需要目录、插图清单、附表清单的页码；用户问"页码对不对"；或用户明确说
> **"你自己看好页码呀"**——即**不接受**"你去 Word 里 Ctrl+A→F9 一下"这类把手工步骤推回给用户的答复。

## 0. 铁律：页码要么是实测的，要么**显式标为估算**

- ❌ 把版心实算出的数字当成实测页码交付（实测：同一稿 实算 94 页 vs WPS 实测 **86 页**，差 8 页，目录全错）。
- ❌ 回"页码请你在 Word 里更新域"（用户已明确反感；本机通常装了 WPS，完全可以自动化）。
- ✅ 先探测办公套件 COM；能自动化就自动化，取回后回写并**重渲染**。
- ✅ 只有确实无 WPS/无 Word 时，才退回版心实算，并在交付说明里写清"**估算值 ±N 页**"。

## 1. 探测（一次，别反复试）

```bash
# 本机是否有 WPS / Word 的 COM 注册
reg query "HKCR\KWPS.Application\CLSID"    # WPS 文字（中文本机常见）
reg query "HKCR\Word.Application\CLSID"    # 微软 Word
# 是否有 pywin32（注意：分析内核常常没有，要用装了 pywin32 的解释器）
python -c "import win32com.client; print('pywin32 OK')"
```

WPS 的 ProgID：`KWPS.Application`（文字）/ `KET.Application`（表格）/ `KWPP.Application`（演示）。
Word 的 ProgID：`Word.Application`。**API 与 Word 兼容**，脚本用 `os.environ["WPS_PROGID"]` 切换即可。

## 2. 取页码

直接跑 `scripts/wps_pages.py <docx> [输出json]`，核心是三个调用：

| 用途 | 调用 |
|---|---|
| 某段落在第几页（绝对页） | `doc.Paragraphs(i).Range.Information(3)` （wdActiveEndPageNumber） |
| 显示页号（受页码格式影响） | `...Information(1)` （wdActiveEndAdjustedPageNumber） |
| 总页数 | `doc.ComputeStatistics(2)` （wdStatisticPages） |
| 顺手导 PDF 供人翻页核对 | `doc.ExportAsFixedFormat(pdf_path, 17)` |

打开方式：`Documents.Open(docx, ReadOnly=True)`，**不要** `doc.Save()`——只读 + 不保存可避免
WPS/Word 弹出格式确认框把脚本挂死。

## 3. 页码映射规则（按吉大式装订页码）

```
前置部分：罗马数字，自「摘要」起 = I
主体部分：阿拉伯数字，自「第1章」起重新起算 = 1
封面 / 封底：不编号
label(pg) = pg - body_abs + 1        # pg >= body_abs
          = roman(pg - front_abs + 1) # front_abs <= pg < body_abs
```

`front_abs` = 摘要标题段落的绝对页；`body_abs` = **`第1章…` 标题段落的绝对页**。

## 4. ⚠️ 本会话实测的两个污染坑（会让整表偏移且看不出原因）

| 坑 | 现象 | 正解 |
|---|---|---|
| 🔴 **段落遍历读到目录行** | `doc.Paragraphs` 也会遍历到目录块里的条目（`第2章　材料与方法 ……… 23`），其文本同样以 `第N章` / `N.M` / `摘要` 开头 → 被标题正则误判，且 `setdefault` 让"**首次出现**"（= 目录行）优先于正文真实标题 → **body 基准取错，全表页码整体偏移 8 页** | 遍历时 `if "……" in text: continue`（目录行必含省略号引导） |
| 🔴 **前置格式说明长句被当标题** | 前置部分常放"摘要：硕士约1000字…""参考文献严格按 GB/T 7714-2015 著录"这类说明行，也以 `摘要`/`参考文献` 开头 | 标题键加**长度上限**：章级/前置标题 `≤20` 字、节标题 `≤30` 字 |
| 🟠 节标题取到目录行 | 目录里 `2.1　数据来源 …… 23` 也是节标题格式 | 节标题**覆盖式赋值（取末次出现）**——真实节标题必然在目录之后；章级标题仍取**首次**（避免被正文里提到"第1章…"的句子抢走） |
| 🟠 `body` 基准别用"第一个以『第』开头且含『章』的键" | 会被 `第1章绪论。阐述研究背景与意义…` 这类长句污染 | 精确取 `heads.get("第1章绪论")`，取不到再退化为"首个长度 ≤20 的章标题" |

**验证口径**：回写后必须断言 ① 第1章显示为 `1`；② 各章/各清单页码**单调不减**；③ 总页数与 `ComputeStatistics(2)` 一致。

## 5. 三遍流程（页码只改数字，不回改版式）

```bash
# ① 先出稿（母本 → DOCX）
python scripts/gen_thesis_docx.py
# ② WPS 实测分页 + 导 PDF
PYTHONPATH=<pywin32所在site-packages> python scripts/wps_pages.py <docx> _wps_pages.json
# ③ 回写 part1_front.md 的目录 / 插图清单 / 附表清单
python scripts/wps_writeback.py
# ④ 重渲染（页码是纯数字替换，版式不变 → ② 的页码继续有效）
python scripts/gen_thesis_docx.py
```

> 页码字符串是 1–2 位数字，替换后**不会**改变行高与分页，因此无需再跑一次 ② 校正。
> 只有在正文**增删内容**后才需要重跑 ②。

## 6. 回写时的两个坑

1. **目录块前面常有一行格式说明**（"（三号黑体，居中排；…）"）。用
   `re.search(r"## 目\u3000录[\s\S]*?```\n([\s\S]*?)\n```", s)` —— **不要**写成 `## 目　录\n\n```"`（中间有说明行时直接断言失败）。
2. **清单行可能重复**：手工补登记一行时若该行已存在，会出现两行同号。回写/校验时按号去重，
   并核对"清单条数 == 正文题注数"。

## 7. 交付话术

- 报"**WPS 实测分页**：全文 N 页；摘要 p?, 第1章=1, 参考文献=N, 附录A=N…"，并附**导出的 PDF 路径**让用户直接翻页核对。
- 若某轮用了实算兜底，必须写"估算值，非实测"，不要把两者混在一张表里。
