# 长稿改稿执行配方：part 源文件 → 合并稿 → DOCX，与"改后必复测"

> 来源：2026-09-16 吉大硕士学位论文会话（`results/memomics-293573bf/`，脚本 `scripts/gen_thesis_docx.py`）。
> 适用于任何「多个 part 源文件 → 脚本合并 → 生成 DOCX/PDF 长交付件」的**改文风 / 改引用 / 改口径**任务。

## 1. 产品是派生的：改错地方等于没改

产物链（实测）：

```
part1_front.md / part2a_ch1.md / part2b_ch2.md / part3_ch3_ch4_ch5.md / part4_refs_appendix.md
   → merge_md()  "\n\n".join(parts)  → 硕士学位论文_….md（合并稿）
   → build()                          → 硕士学位论文_….docx
```

- **只改 part 源文件**。合并稿是派生物，下次重跑生成器即被覆盖。
- 定位"某段属于哪个 part"：拿该段里**唯一的字符串**去各 part `count()`，命中 1 次才动手。
- 生成器尾部通常是 `if __name__ == "__main__":` 全量块 ⇒ `exec(open(脚本).read())` 即完成"合并 + 拷图 + 出 DOCX"，末行 `OK` + `size/paragraphs/tables/sections`。
- ⚠️ 走 `exec(open(...))` 的脚本**不能依赖 `__file__`**（本表主 SKILL.md 有专门一行）。

## 2. 解释器与路径（一步到位，别试三遍）

| 解释器 | `import docx` |
|---|---|
| 持久内核 `execute_python` | ❌ ModuleNotFoundError |
| 项目 `.venv/Scripts/python.exe` | ❌ 无（只有 lxml） |
| **`C:/Users/<user>/AppData/Local/Programs/Python/Python312/python.exe`** | ✅ 经共享库 `D:/Python/site-packages/docx` |

```bash
"C:/Users/23136/AppData/Local/Programs/Python/Python312/python.exe" \
  -c "exec(open(r'E:/MemOmics-Agent/results/<sid>/scripts/gen_thesis_docx.py', encoding='utf-8').read())"
```

⛔ 脚本路径写 `E:/...`。写成 MSYS 形式 `/e/...` 会被拼成 `E:\e\...` → `can't open file: [Errno 2]`。

## 3. 批量改稿：一个脚本 + 唯一命中断言

```python
EDITS = {'part2a_ch1.md': [(old, new), ...], 'part2b_ch2.md': [...], ...}
for fn, pairs in EDITS.items():
    s = open(os.path.join(BASE, fn), encoding='utf-8').read()
    for old, new in pairs:
        assert s.count(old) == 1, f'{fn}: 命中 {s.count(old)} 次（应为1）→ {old[:40]}'
        s = s.replace(old, new)
    open(os.path.join(BASE, fn), 'w', encoding='utf-8').write(s)
```

一次跑完全部改动（本轮 13 处：2 处图题交叉引用 + 11 处 AI 腔），零漏改、失败即定位到文件名。逐条 `patch` 的代价：轮次多 + 中途失败不知道第几处断掉。

## 4. 复测三步（本轮最大教训）

**"我上一轮说改完了" ≠ 已改。** 上一轮汇报"三处「见图 X.Y 第②步」已改、DOCX 已重出"，重跑生成器后对合并稿 grep：`第②步` **仍残留 1 处**。

1. 重跑生成器（part → 合并稿 → DOCX 全链）。
2. **旧句式计数 → 0，新写入句子的计数 → 命中**，MD 与 DOCX **双端各测一次**：
   - 旧：`第②步`、`见图 \d`、各 AI 腔词
   - 新：新写入的叙述句原文（如 `该流程对应图 1.1 所示技术路线中的第二步`）
   - DOCX 端：`Document(p)` 后把 `paragraphs + tables` 全文拼起来再 `count()`（图题/表格里的字词只在这两者里）。
3. 把「旧计数 → 新计数」直接写进汇报（例：AI 腔词表 **8 → 0**；`第②步` **1 → 0**；模板句式 10 → 8，余下 8 处全是「从而/进而」属正常学术连接词）。

⚠️ **改稿收尾只需这一轮复测**。再叠加"读回 DOCX 逐段确认"之类的多轮核验会被循环检测判失控（本轮末尾即吃到 OOB 强制干预）。判据：改稿任务的正确性 = **计数**，一次就能全出。

## 5. 两项文本自检的可复现口径

```bash
PY="C:/Users/23136/AppData/Local/Programs/Python/Python312/python.exe"
SK="E:/MemOmics-Agent/hermes_home/skills/bioinformatics/human-skill/scripts"
"$PY" "$SK/ai_flavor_scan.py"   <论文.md> --out results/ai_flavor_report.md --json results/ai_flavor_report.json
"$PY" "$SK/similarity_check.py" <论文.md> --ref "E:/专利/毕业专利_v28_论文素材包" --json results/simcheck.json
```

- **源库集合决定 `ref_files` 数**：`similarity_check` 的目录收集规则是 `*.md/*.txt/*.docx/*.csv` 递归 glob ⇒ 素材包（12 md + 5 txt + 1 docx + 6 csv）= **24**。换源库后数字**不可比**，所以汇报里要写明「调用命令 + 源库路径 + `ref_files` / `internal_rate` / `ref_rate` / 最长片段 len」。
- 本轮实测：`internal_rate 7.96%`、`ref_rate 7.85%`（阈值 10%）、最长连读 **88 字**。
- Top 片段里 70/70/69/63 字几条**全部来自「现有技术对比表」的行**（与交底书同源）——表格行重复属结构性重合，要改就得连表格一起动，属需用户决策的范围；真正值得重述的正文超长片段是那条 **88 字**图注/正文句。

## 6. 交付前必须点出的结构性问题（本轮实例）

| 问题 | 判定方法 | 处置 |
|---|---|---|
| **同一张 PNG 被编成两个图号** | 比对 `![图 X.Y　标题](figures/xxx.png)` 里的文件名 | 本轮 `图 2.1` 与 `图 3.1` 同用 `v21_fig2_pillar_funnel_bw.png` ⇒ 交用户选：删后者 + 正文改"如图 2.1 所示"后重编号 / 换独立图 / 仅调位置 |
| **图序 ≠ 正文出现序** | 按合并稿行号排序图题编号（本轮正文序 3.2 → 3.3 → 3.4 → **3.1**） | 与上一条一起决策；重编号会连带改正文交叉引用（如"图 3.3、图 3.4"）与图目录 ⇒ **改一次就全链重出** |
| 目录/图目录页码是**静态数字** | 生成器里没有 TOC 域代码，页码写在 part1 的表格里 | 任何正文改动都会让页码偏移 ⇒ 汇报时点明"终稿须在 Word 里按实排复核"，别当成本次改动引入的缺陷 |
| `[图 X.Y]` 方括号"夹注"命中 | grep `\[图 \d` 命中的其实是 Markdown 图片 `alt`：`![图 X.Y　标题](...)` | 这是**图题载体**，DOCX 渲染后没有方括号——别当夹注去改。真正要改的是**图题括号里的交叉引用**（`**图 X.Y　标题**（…如图 Z.W 所示…）` → 移到正文写成叙述句） |
