---
name: supplementary-table-assembly
description: "把策展基因集/打分表/注释表组装成可交付的补充表（xlsx/CSV）：按生物功能轴重排、统一英文标签、附加 legend 表、表↔图口径对账。触发：把表格分类排列/按分类重排/重命名导出/重出一张表/补充表/Supplementary Table/表格里不能有中文/表和图对不上/表格行序乱要排一下。"
when_to_use: "用户要求重排/重命名/导出/英文化一张分析结果表（基因集表、通路打分表、轴分类表、示例分析 输入表等），或抱怨'表和图口径不一致'时。也适用于新建补充表。"
version: 1.0.0
author: MemOmics
license: MIT
platforms: [windows, linux, macos]
metadata:
  memomics:
    tags: [table, xlsx, openpyxl, supplementary, deliverable, gene-signature]
    difficulty: basic
    language: Python
    category: bioinformatics
---

# 补充表组装（xlsx 交付规范）

把「随便排的」分析中间表 → 排成**可交给合作者/审稿人的补充表**。
核心不是写代码，是把**交付约定**固化进脚本：全英文、轴序、legend、表↔图对账、出口断言。

## 铁律 1：交付表一律全英文（用户 2026-10-21 硬要求：「表格里不能有中文」）

范围是**整份 workbook 的每一个 sheet 的每一个 cell**，不只是主表：

| 位置 | 最容易漏 |
|------|---------|
| 主表表头 | ✅ 通常已是英文 |
| **legend / 说明 sheet 的列头** | ⚠️ 最常见漏点（如 `归类依据`、`参考文献`、`成员清单`） |
| **legend 的正文（rationale / references）** | ⚠️ 第二常见——中文整段说明最容易被忘掉 |
| sheet 名 | 通常已英文 |
| 图注/标题行 | 检查一遍 |

**对策：把约束写成出口断言，不靠记性。** 导出后、`save()` 前遍历全表：

```python
def has_cjk(s):
    return any('\u3000' <= ch <= '\u9fff' or '\uff00' <= ch <= '\uffef' for ch in str(s))

bad = [(name, c.coordinate, str(c.value)[:40])
       for name in out.sheetnames
       for row in out[name].iter_rows() for c in row
       if c.value is not None and has_cjk(c.value)]
assert not bad, f'❌ 仍存在中文: {bad[:10]}'
print('✅ CJK 自检通过')
```

约束一旦进脚本，就不会再产出带中文的表——比"下次注意"可靠得多。

## 铁律 2（2026-10-21 晚定稿，**覆盖**当日早先的"长名 + Figure_axis_name"方案）

**`Axis` 列直接用用户 AXES 里的短名，禁止自造长名。**

- `Axis` 列 = 用户口径短名：`Metabolism` / `Nutrient` / `Contractile` / `Inflammaging` / `Sarcopenia`
  （身份轴 `Fiber type`、技术对照轴 `Stress` 各自单独一轴）。
- 改名以**用户当日口径为准**：`Inflamm-aging → Inflammaging`、`Decompensation → Sarcopenia`。
- legend 的 `Figure_axis_name` 冗余列**删掉**（表内轴名与图内轴名已一字不差，无需映射列）。

**踩坑复盘（两次返工换来的）**：先按"描述性长名 + Figure_axis_name"方案交付，用户看到
`Substrate metabolism axis` / `Nutrient sensing & proteostasis axis` 这类自造名后直接说
**"简直就是狗屎"**、并当场贴出他自己的 `AXES` 列表问"我不是让你按这个分类吗？"。
教训：**轴名不是我的自由度，是用户已定义的字符串常量**。表里凡出现"我自造的名字"，
交付前必须先与用户的原始定义（脚本里的 `AXES <- list(...)` 或对话里贴过的列表）逐字比对。
**任何"同一概念在两处用了不同名字"的交付表，都要先把两处的字符串对齐到用户口径。**

## 铁律 3：长文本列必须给列宽 + 换行，否则用户会说"你根本没写"（2026-10-21 事故）

用户拿到表后质问 **"你怎么没把来源写进去呢？"** 并当场贴出 22 条来源原文。
只读核验结果：主表 `Annotation` 列 **20/20 逐字全在** —— 真凶是那一列**列宽停留在 Excel 默认
的 8.43 字符**，而来源文本 80–165 字符，屏幕上只剩 `Genes ex…`，**视觉上就是一个空列**。

**交付前必做（写进脚本，不靠眼睛）**：

```python
from openpyxl.styles import Alignment
ws.column_dimensions['A'].width = 20.0     # Axis
ws.column_dimensions['B'].width = 34.0     # Signature
ws.column_dimensions['C'].width = 62.0     # Annotation（长文本列）
for r in range(2, ws.max_row + 1):
    ws.cell(r, 3).alignment = Alignment(wrap_text=True, vertical='top')
```

- 判据：**列宽 ≈ 该列最长字符串长度 × 0.75**（中文按 2 字符计）。超长列（URL 串、多篇文献堆叠引用）
  → `wrap_text=True` 让它折行，**不要为了一行装下把列宽设到 150**。
- legend sheet 同理：`References` 88 / `Rationale` 58 / `Members` 50，三列都 `wrap_text=True`。
- 出口自检补一条：`print({c: ws.column_dimensions[c].width for c in 'ABC'})`。

**回读核验脚本自己也有坑：表头不在 R1（2026-10-21 唤醒#0 实测）。**
本 skill 的标准结构是 **R1 = 合并标题行、R2 = 表头**，但回读脚本若直接取 `row 1` 找列名，
会匹配到标题串 → 打印 `annotation-like col idx: None` 并**静默跳过来源列计数**，
等于「跑了核验但什么都没核验到」，还会被当成"通过"。回读一律**下探前 5 行找表头**：

```python
hdr_row = hdr_col = None
for r in range(1, 6):
    for c in range(1, min(ws.max_column, 8) + 1):
        v = ws.cell(row=r, column=c).value
        if v and str(v).strip().lower() in ('annotation', 'source', 'reference', 'references'):
            hdr_row, hdr_col = r, c; break
    if hdr_row: break
assert hdr_row, '❌ 前 5 行内找不到 Annotation/References 列头 —— 核验未生效，不是表没问题'
filled = sum(1 for r in range(hdr_row + 1, ws.max_row + 1)
             if ws.cell(row=r, column=hdr_col).value not in (None, ''))
print(f'Annotation 非空 {filled}/{ws.max_row - hdr_row}')
```

**「找不到列头」必须让脚本 assert 失败，不能当默认通过** —— 否则核验脚本给出假阴性结论。

**流程教训（比列宽本身更重要）**：用户说"你没写 X / 你没做 Y"时，
**先只读实证 X 到底在不在**（逐格比对 + 非空计数 + 贴出行号），**再**定位"他为什么看不到"
（列宽截断 / 冻结列挡住 / 列被隐藏 / sheet 选错 / 文件版本不对），最后才谈改不改。
本次核验出 20/20 全在、真因是列宽 → 避免了一轮无意义的重做；
汇报时**先给"内容全在"的实证表，再讲真因**，不要一上来就道歉重做。

## 铁律 4：改列（插列 / 改名 / 删列）必须做「前后快照比对」（2026-10-21 实测配方）

用户说「你应该在这个表格写来源啊，**加一列，加在第三列**」这类**列位变动**需求时，交付物是
「表头 + 该列内容都变、右侧基因块一字不动」。`insert_cols` / `delete_cols` 会**静默移动单元格**——
列号写错一格，200 个基因列整体错位且不报任何错。配方：

```python
# ① 插入前：快照「会被移动的那一块」（本例 = 基因列 col 4..max）+ 冻结窗格
gene_snap = {(r, c): ws.cell(r, c).value for r in range(1, last + 1) for c in range(4, maxc + 1)}
fp0 = ws.freeze_panes

# ② 先收集要搬的内容 —— insert_cols 会把原 C 推走，插完再读就读到空列
rows_src = [(r, ws.cell(r, anno_col).value) for r in range(hdr + 1, last + 1)]

ws.insert_cols(3); ws.cell(hdr, 3, 'Source')        # ③ 插列 + 表头 + 逐行写值（wrap_text=True）
assert str(ws.cell(hdr, 4).value).strip() == 'Annotation'   # ④ 断言旧列确实右移一格
ws.delete_cols(4)                                   #    再删旧列 → 净列位移 = 0
ws.freeze_panes = fp0                               # ⑤ 冻结窗格复位（列位移会带跑它）

# ⑥ 写盘后逐格比对快照：0 差异才算过
diff = [(r, c) for (r, c), v in gene_snap.items() if ws2.cell(r, c).value != v]
assert not diff, diff[:5]
```

要点：

- **净位移 = 0 的「插 + 删」**（插第 3 列、删第 4 列）让被搬走的块回到原位，比整表重建安全得多。
- **防重复执行**：插列前 `assert str(ws.cell(hdr, 3).value).strip() != 'Source'`——脚本可安全重跑，
  第二次会中止，而不是插出两列。
- **表头行不一定是 R1**：本 skill 标准结构是 R1 标题 / R2 表头，定位一律「下探前 8 行找 `Signature`」。
- 列号一律**动态定位**（找 `Annotation` / `Source` 表头名），不写死字母。
- 落法（插新列 / 仅改名 / 保留原列另加）**必须先弹窗问清**——三种读法产出的表头完全不同。
  本次用户在弹窗选 B：「第 3 列插入新列 Source，并删掉原 Annotation 列」⇒ `Axis|Signature|Source|Genes`。

## 标准化结构

```
Sheet1（主表，sheet 名 = 文件名语义）
  R1  标题行（粗体）：一句话说明 + 来源与版本
  R2  表头（粗体）：Axis | Signature | Source | Genes | …（2026-10-21 定稿：Class 列由用户删除、
      Annotation 列改名为 Source 并固定在【第 3 列】—— 用户原话「加一列，加在第三列」）
  R3+ 数据行，按轴分组、按轴序排列
  freeze_panes = 'D3'   # 冻结表头 + 前 3 列标识列，横向拖看基因时行名不丢
  列宽 A/B/C = 20 / 34 / 62，长文本列（Source）wrap_text=True（铁律 3）
  基因/长列表横向铺开（Genes 列 = 第 1 个，右侧继续铺）

Sheet2（legend）
  列：Axis | n_members | Members | Rationale | References
       （Figure_axis_name 冗余列已删；References 是【第 5 列】，回读时别取第 4 列）
  Rationale 写为什么归进这一轴（机制层面），References 写 PMID / R-HSA / 数据库 URL（禁自指文本）
```

## 流程

1. **口径先问清**：一次 `ask_user` 问齐 ≤3 项——① 按哪个分类键排（新口径 vs 源表 Class 列）
   ② 去掉哪些行 ③ 落盘位置与是否覆盖原表。选项用 dict 带 `desc` + `recommended`。
2. **源表只读**：`openpyxl.load_workbook(SRC, read_only=True, data_only=True)`，**绝不改写源表**。
3. **写显式断言**：轴定义必须**不重不漏**覆盖保留集（见下方代码骨架），行数写死检查。
4. **一个交付一套脚本**：脚本直接生成全部产物，禁止多版本产物并存（用户 2026-09-11 定的复现铁律）。
5. **出口 CJK 断言**（铁律 1）+ 跑一遍跑通 → `record_run`。

## 代码骨架

```python
SRC = 'E:/.../源表.xlsx'
DST = 'E:/.../交付表名.xlsx'
DROP = ['<要删掉的集>']

# 元组 = (Axis 长名EN, 图上轴名, Rationale EN, 成员, References EN)
AXES = [('Substrate metabolism axis', 'Metabolism', '<why>', ['A score', 'B score'], '<PMID ...>')]
# 身份轴等"语义层级不同"的组，另立一轴而非并入功能轴（写明依据）

rows = list(ws.iter_rows(min_row=1, max_row=N, values_only=True))
recs = {r[1]: dict(cls=r[0], anno=r[2], genes=[g for g in r[3:] if g not in (None, '')])
        for r in rows[2:]}

ordered = [(a[0], s) for a in AXES for s in a[3]]
kept = [s for _, s in ordered]
assert not set(kept) & set(DROP), '被删集仍在轴定义中'
assert not (set(recs) - set(kept) - set(DROP)), '存在未归轴的集'
assert len(kept) == len(set(kept)) == <期望行数>, f'行数异常 {len(kept)}'
```

## 坑

- **来源列（Annotation / References）不准出现"自指文本"**：`session convention: fig_xxx.R`、
  `textbook consensus`、`J matrix of this dataset`、`本表内部口径` 这类都**不是来源**。
  用户 2026-10-21 明确"这个很重要的"。可接受的来源只有三类：
  ① 论文 `作者 et al., 期刊 年份, PMID xxxxxxxx` ② 数据库条目 URL（MSigDB KEGG/Reactome/WikiPathways）
  ③ 数据集内实证（需写清是哪个矩阵哪个值）。**PMID 必须联网核验**（esummary 一次可批量 14 个）。
- **删行后要清掉引用它的来源**：本会话从 Inflammaging 轴删掉 SenMayo 后，legend 仍引用
  `SAUL_SEN_MAYO`——**失效引用比没引用更糟**（审稿人会问这个集在哪）。改法：换成该轴现有成员
  各自的来源，并在 NOTE 里写明"X 已于 YYYY-MM-DD 移除、本表无对应行"。
- **同一作者两篇不同论文不是"PMID 冲突"**：`Machado L.` 一篇是 Cell Stem Cell 2021 PMID 33609440
  （Stress index 基因表来源），另一篇是 Trends Cell Biol 2021 PMID 34074577（解离伪影综述）。
  核验后再下结论，不要先按"冲突"报错——**先 esummary 看标题**。
- **用户改过的表是基准**：`xlsx` 内 `docProps/core.xml` 的 `cp:lastModifiedBy` = 用户 Windows 用户名
  （此处 `张波`）、`dcterms:modified` = 其保存时间，`dc:creator=openpyxl` = 我写的初版。
  靠这个判定"哪份是用户改的"，比看文件 mtime 可靠（Excel 保存常与我的写盘时间接近）。
  **用户删掉的列（如 `Class`）不得擅自加回**。
- **写回原文件名时 `os.replace` 报 `WinError 5 (拒绝访问)` ≠ 文件被 Excel 占用**（2026-10-21 实测纠错；
  旧版"改写出 `_SRC_fix_*` 副本"的建议已被证明是**误判后的退让**，勿再照做）：
  用户**明明已关 Excel**，`os.replace` 仍失败——真凶是**目录同步服务**：实测
  `tasklist` 扫到 `wps.exe`×4 + `wpscloudsvr` + `OneDrive.Sync.Service` + `OneDrive` +
  `clouddrive_desktop_widget` 在盯 `<数据目录>/`。它们挡的是需要 **DELETE 权限的
  rename/delete**（`os.replace` 本质是原子 rename），**不挡改写内容**。
  - **判据**：`open(DST,'r+b')` 能打开 → 不是独占锁，只是 rename 被挡 → **能写回原名，不要退化成副本**。
  - **解法**：先试 `os.replace`，`PermissionError` 时改内存序列化 + 原地覆写：
    ```python
    buf = io.BytesIO(); wb.save(buf); wb.close()
    with open(DST, 'r+b') as f:
        f.write(buf.getvalue()); f.truncate()   # truncate 必须调用（新内容更短）
    ```
    写前 `shutil.copy2` 备份（原地覆写非原子），写后回读验证内容。
  - 覆写后若 WPS/Excel 仍开着该文件 → **提醒用户关掉重开**才看得到新内容。
  - `openpyxl` 重写后文件变小（27,047 → 20,916 B）属正常（丢弃 Excel 原生扩展后重打包），
    判据看回读的行数/断言，不看字节数。
  - 完整判别三步（`~$` 锁文件 / `r+b` 探针 / 进程扫描）+ 配方 →
    `platform-execution-pitfalls` 的 `references/windows-file-lock-inplace-overwrite.md`。
- **`rail_review(post)` 对表格步骤有两类结构性误报 —— 正确传参即可通过（2026-10-21 两轮实测）**：
  ① **别把 `output_dir` 传成用户数据目录**（如 `<数据目录>，
  扫到用户目录里躺着的历史无关图（本次 `cy3logo_orange.svg` 1502B）后判 `passed=false 图片太小`。
  **表步骤按设计不出图 → 省略 `output_dir`，只传 `phase/module_id/skill_name/code_executed` 即 passed=true。**
  ② `code_executed` **必须传完整多行脚本**；传单行摘要会被判 `代码过短 (1 行) — 可能偷懒`（按行数判，
  与内容无关）。实测：同一步传单行 → `passed=false`；传回原件 193 行 → `passed=true`。
  ③ 遇到这两类报警**不要去重出图 / 不要重跑脚本**，改传参重审一次即可；汇报时如实说明
  「该文件为 <路径> 的历史文件，非本步产出，本步无图产出」。
- **源表列"不改一字"**：源表 `Class` 列可能有拼写问题（如 `Diabete` 应为 `Diabetes`）——
  保留原样并**主动指出**，要改等用户一句话，不擅自动手。
- **用户说"去掉之前那两个"时，去实读脚本里的断言**定位是哪两个，不要凭印象。
  本会话脚本里写死的断言 = `scoreSenMayo + Adipogenesis`，据此才敢确认口径。
- **宽表读取**：基因被 Excel 摊成 199 个 `Unnamed` 列 → 用 `r[3:]` 过滤空值还原，
  或直接读同目录的长格式 CSV 更省事。
- **默认写回原文件名（用户 2026-10-21 口径，覆盖早先"另存新文件"）**：用户在弹窗里明确选
  「写回原文件名（我已关掉 Excel）」。只有用户说"另存新文件 / 原表不动"时才另存。
  写回前 `shutil.copy2` 备份；写回后目录里会留下三件套：
  `*.bak_<时间戳>.xlsx`×2（**必须保留**——仓库规范「不删备份」）
  + `*_SRC_fix_<时间戳>.xlsx`（中间产物，可删，但**删除前逐项列给用户点头**）。
  ⛔ 别自作主张清目录：xlsx 类文件的自动删除会被系统拦下，列清单等用户一句话即可。
- **回读核验脚本必须能报"核验没生效"**：找不到列头要 assert 失败（见铁律 3），
  否则会出现"跑了核验、结论是假阴性、却被当成通过"。
- 交付时不只给文件清单，要**先结论后证据**：轴序表 + 校验结果 + 与原表的差异说明。
- **出口断言里禁止出现「我自己推测出来的来源」—— 期望值必须逐字取自用户原文**（2026-10-21 自伤）：
  给 mTORC1 行的期望值写了 `PMID: 29104506`（那是我上一步核验 legend 时查到的），
  而用户清单里该行**只有一条 MSigDB URL、没有 PMID** → 断言失败、脚本 exit 1。
  三条对策：① 把用户贴的清单按 `Signature` 建「期望表」，一个字都不要改写或补充；
  ② 匹配一律**大小写不敏感**（`k.lower() not in src.lower()`）——数据库基因集名在 URL 里是小写
  （`hallmark_mtorc1_signaling`，写 `mTORC1` 会匹配不到）；
  ③ 纯 URL 类来源**不要硬塞 PMID**（能接受的只有论文类来源才带 PMID）。
- **「写盘在断言之前」时的汇报口径**：本次 exit 1 报的是最后一道内容自检没过，**但文件已经写入成功**
  （表头已改、20 行已写、基因块 0 差异）。所以：
  ① 先回读实测产物状态（列头 / 非空计数 / 基因块逐格差异），确认数据对不对，**再**单独解释断言为什么失败；
  ② **不要因为 exit 1 就重跑脚本**——防重复断言会中止它（插列前有 `!= 'Source'` 保护，这是设计而非故障）；
  ③ 汇报顺序：产物已成 + 实证 → 断言误报原因 → 已修脚本（期望表 + 大小写不敏感），不要把自伤写成数据错误。
- **独立核验脚本的列号要数对**：`Axis_legend` 表头是 `Axis | n_members | Members | Rationale | References`
  → References 是**第 5 列**。取第 4 列会把 `Rationale` 当 References 打印，看着"有内容"实则验错了列
  （本次实测踩到，靠打印表头才发现）。**核验脚本先打印表头再做断言**，列号错位会立刻暴露。

## 配套

  rail_review 传参矩阵**（含 2026-10-21「加一列在第三列」这一轮的完整实证与自伤复盘）。

## Proven Scripts

> Auto-generated from actual analysis runs. Each row records a successful execution.

| 物种 | 组织 | 方向 | 日期 | 脚本 | auto | user | ✔ |
|------|------|------|------|------|------|------|----|
| human | example_tissue | aging | 2026-10-21 | build_gene_score_table.py | - | - |  |
| human | example_tissue | aging | 2026-10-21 | patch_axis_legend_references.py | - | - |  |
| human | example_tissue | aging | 2026-10-21 | verify_annotation_sources_readback.py | - | - |  |
| human | example_tissue | aging | 2026-10-21 | verify_annotation_sources_readback.py | - | - |  |
| human | example_tissue | aging | 2026-10-21 | insert_source_column.py | - | - |  |
| human | example_tissue | aging | 2026-10-21 | insert_source_column.py | - | - |  |
| human | example_tissue | aging | 2026-10-21 | verify_source_column.py | - | - |  |
| human | example_tissue | aging | 2026-10-21 | check_final_table_state.py | - | - |  |
