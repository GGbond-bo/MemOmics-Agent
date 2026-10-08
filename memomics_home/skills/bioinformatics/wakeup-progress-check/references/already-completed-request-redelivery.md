# 已完成请求被重投时的一步判定（别重做，别连环复核）

**场景（2026-10-01 memomics-afd2d418 实测）**：唤醒/中断轮重投了一条用户请求 ——
「`44_MEF2C_locus_from_GTF` 这个里面的文字变成英文」。上一轮 **21:50–21:59 已经把活干完了**
（6 处中文→英文 + rail_review + `record_run` 记录在案），本轮 22:15 收到同一条请求。

**代价对照（本会话实测）**：

| 做法 | 调用数 | 结果 |
|---|---|---|
| 我实际走的：`search_files` ×4 → `vision_describe`（OCR 整张图）→ `execute_python` ×5（查 SVG 文本 / 查 mtime / 扫脚本 / 列目录） | **10+** | 每一条都只能证明"看起来已是英文"，**无法证明"活已经干过"**；且第 5 轮起就被系统判循环失控 OOB 强制干预 |
| 正确做法：`grep -i '<资产名>' results/<sid>/log/system_log.jsonl` | **1** | 直接看到完整证据链（见下），一步结案 |

## 一步判定：查 `log/system_log.jsonl` 的资产名

```bash
# 一条命令拿到"这个资产被谁、什么时候、怎么处理过"
grep -n '<资产名关键词>' results/<sid>/log/system_log.jsonl | tail -30
```
或跑现成探针：`python scripts/asset_history_probe.py <会话目录> <关键词>`

**日志里要抓的 4 类行（按时间排开就是完整证据链）**：

| 行 | tool | 说明 |
|---|---|---|
| `write_file` | 写脚本 | `args.content` 是当时脚本**全文** |
| `execute_python` / `execute_r` | 真跑 | `args.code` 是当时执行的内容，`result_preview` 是 stdout |
| `vision_describe` | 自查 | 上一轮自己已经 OCR 核对过 |
| `rail_review` | 过审 | `phase=post` 出现 = 该步已闭环 |
| 🔴 **`skill_evolution(action="record_run")`** | **完成声明** | **`notes` 字段就是上一轮自己写的"做了什么改动"摘要** —— 本次实测逐字写着「图内文字全英文化（用户全局偏好「把图中文字=英文」）。6 处中文→英文：①…②…」 |

→ **看到 `record_run` + `notes` 覆盖了用户这条请求 + 时间在上一条用户消息之后 ⇒ 任务已完成，直接汇报，不要重做、不要复核。**
→ 没看到 `record_run`、或 `notes` 说的事与本次请求不同 ⇒ 才是真没做，正常执行。

## 二步：产物 mtime 与上一轮时间窗对照（30 秒）

```python
import os, time
p = r'<会话目录>/figures/<资产名>.<ext>'
print(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(p))))
# 再对照 log 里 write_file / execute 的 ts —— 落在同一时间窗 = 同一轮产物
```
🔑 **看 mtime 的绝对时间，不看"我有没有印象"**：本次产物 21:57–21:58 落盘、当前 22:16，
**差 18 分钟** ⇒ 用户这句请求要么是重投、要么是在看旧缓存（汇报时提示刷新界面即可）。

## 为什么"逐条复核图"这条路必然失败

1. **复核只能证明"现在是对的"，不能证明"活已经干过"** —— 而用户要的判据是后者（他不想重做）。
2. **图内文字的正确性本来就不是靠肉眼看图确认的**：上一轮已 OCR + rail_review 过了。
3. **同形态调用铺开 ≥5 轮必吃循环检测 OOB**（本次第 5 条 `execute_python` 后即被点名）。

## 附带坑：matplotlib SVG 的文本是**路径**，不是 `<text>` 节点

想"用 grep 精确证明 SVG 里没有中文"是行不通的（本次实测）：

```python
import re
s = open('44_xxx.svg', encoding='utf-8').read()
len(re.findall(r'<text[^>]*>', s))     # → 0   ← 不代表"没有文字"！
```

matplotlib `svg.fonttype` 默认 = **`path`** ⇒ 所有文字被转成矢量路径，SVG 里**根本没有 `<text>` 元素**。

| 想验的事 | 可行办法 | 不可行办法 |
|---|---|---|
| 图内是否有中文 | ① 源脚本 grep CJK（`re.compile(r'[\u4e00-\u9fff]')`）② PNG 走 `vision_describe` OCR（OCR 文本里出现中文即证据） | grep SVG 的 `<text>` |
| 两份产物是否同一版 | `stat` 比字节数（本次 figures/ 与 task5/figures/ 三格式**字节完全相同** = 同一份拷贝，不必再比内容） | 逐字符读 SVG 比对 |

→ 判"图内文字是否全英文"最快的一手证据 = **改图那一步的脚本 + 那次 OCR 的 record_run notes**（在 `system_log.jsonl` 里），
不是对着成品图再猜一遍。

## 汇报形状（一步判定之后）

```
这件事已经做完了（上一轮 HH:MM–HH:MM 完成，本轮只是复核确认）：<资产> 内文字已全部英文，无中文残留。
改动的 N 处：<表格：位置 / 现在的英文>
产物：<路径>（两处内容完全相同）
若界面还显示旧版 = 浏览器缓存，刷新即可。
```
⛔ 不要再附：三源验证仪式、逐文件 mtime 表、审查器口径说明（用户要的是结论）。