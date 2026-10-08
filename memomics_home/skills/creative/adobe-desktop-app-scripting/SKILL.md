---
name: adobe-desktop-app-scripting
description: 用 COM + ExtendScript 脚本化控制本机 Adobe 桌面应用（Illustrator 为主，Photoshop/InDesign 同一通道）——读取用户正在编辑的文档、新建/编辑文档、增删画板、导出 PNG/SVG、存盘 .ai。Windows 上一行 cscript 即可执行，不抢用户鼠标焦点，可复现、可批量。触发词：Illustrator / AI / .ai 文件 / 画板 artboard / 删掉画板 / 多画板 / 导出 SVG PNG / ExtendScript / jsx / 控制那个软件 / 帮我在 Illustrator 里改一下 / FigureS2 里的框删不掉 / 批量导出图。不适用：科学数据图（走 nature-figure / cns-visualization）、示意图与版式设计（走 diagram-design）。
category: creative
source: memomics-created
---

# Adobe 桌面应用脚本化控制（COM + ExtendScript）

## 0. 触发与不触发

**触发**：用户要「在 Illustrator 里做点什么」——查文档结构、改对象、删画板、批量导出、存盘、把一堆图转格式；或者用户问「你能不能控制我的 Illustrator / AI / 那个软件」。
**不触发**：画科学数据图（nature-figure / cns-visualization / scipilot）、做示意图（diagram-design）、纯 SVG/HTML 生成。

> ⚠️ 用户口语里的 **「AI」很可能指 Adobe Illustrator**（不是人工智能）。凡出现「AI 文件 / AI 里的画板 / AI 里那个框」→ 先按 Illustrator 理解，必要时一句话确认。

## 1. 通道：VBS + cscript（Windows 首选）

文档级精确操控，**不抢焦点、不依赖屏幕截图/点击**，可复现、可批量。屏幕级 GUI 操控（cua-driver 截图 + 点击）只在需要按按钮/进菜单时才用，且属于另一条链路。

```vbs
' run_jsx.vbs —— 通用运行器（把 jsx 路径传进去）
On Error Resume Next
Dim app, res
Set app = CreateObject("Illustrator.Application")
If Err.Number <> 0 Then WScript.Echo "COM_FAIL: " & Err.Description : WScript.Quit 1
res = app.DoJavaScriptFile("<绝对路径>/x.jsx")
If Err.Number <> 0 Then WScript.Echo "JS_FAIL: " & Err.Description : WScript.Quit 2
WScript.Echo "RESULT: " & res
```

```bash
cscript //nologo run_jsx.vbs          # bash（MSYS）下直接跑，路径用正斜杠
```

要点：
- jsx 首行写 `#target illustrator`；入口用 `main()` 包起来，脚本末尾 `return "OK|" + out.join("; ")` 把观测值**结构化回传**——返回值经 VBS 打印出来就是唯一的验收依据。
- `app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;` 防止弹窗卡死。
- ExtendScript 是 ES3 语法：`var`、无模板串、无 `let/const`、无 arrow function；`try/catch(e)` 里用 `e.message`。
- Illustrator 已在跑时直接复用该实例；没在跑 `CreateObject` 会拉起它（冷启动慢，先 `tasklist | grep -i illustrator` 确认 PID）。
- 同通道可推广到 Photoshop（`Photoshop.Application`）与 InDesign。

## 2. 标准动作流程

1. **读**：遍历 `app.documents`，输出每个文档的 `name / saved / artboards.length / layers / pathItems / textFrames / groups`，以及每个 `artboards[i].name + artboardRect` —— 先看清用户手上有什么，再动手。
2. **写**：`app.documents.add(DocumentColorSpace.RGB, W, H)` → `doc.artboards.add([left, top, right, bottom])` → 重命名 `artboards[i].name` → `doc.layers.add()` → `pathItems.rectangle/ellipse/polygon/add() + setEntirePath([...])` → `textFrames.add()` → `groupItems.add()` + `item.move(grp, ElementPlacement.INSIDE)`。
3. **删**（用户最常问的）：`doc.artboards[i].remove();` —— 画板框删不掉时用这条，比手点快且不会漏。删除后重新列举名字确认。
4. **导出**：`doc.exportFile(new File(p), ExportType.PNG24, opts)` / `ExportType.SVG` / `ExportType.PDF`。
   - `ExportOptionsPNG24`：`antiAliasing=true`、`artBoardClipping=false`（要全画布）或 `true`（按画板裁）。
5. **存盘**：`doc.saveAs(new File("x.ai"), new IllustratorSaveOptions({pdfCompatible:true}))`。
6. **收尾**：`doc.close(SaveOptions.DONOTSAVECHANGES)` + 重新列举开放文档，证明用户的文档原样还在。

## 3. 安全铁律（3 条，违反即事故）

1. **绝不改动/关闭用户正在编辑的文档**——只读它的元信息。要演示就 `documents.add()` 新建一个探测文档。收尾必须回传用户文档仍 `saved=false`、名字未变。
2. **脚本开头先清理上轮残留**：遍历 `app.documents` 倒序，把名字等于本次探测名的文档 `close(DONOTSAVECHANGES)`。脚本中途抛错会把探测文档留在界面上，第二次跑就会堆一地。
3. **报告"能做/不能做"都要有实测数字**，不许凭印象说"我可以控制它"。

## 4. 实测能力清单（2026-10-03 本机 Illustrator 实测）

| 能力 | 状态 | 证据 |
|---|---|---|
| 读开放文档结构（画板/图层/对象计数） | ✅ | 读到 2 个文档：1740 路径 / 354 文字 / 38 组 |
| 新建文档 + 多画板 + 重命名 | ✅ | 3 画板 AB_1_keep / AB_2_delete_me / AB_3_keep |
| 删画板 `artboards[i].remove()` | ✅ | 3 → 2，名字逐个核对 |
| 图层 / 矩形 / 椭圆 / 多边形 / 贝塞尔 / 文字 / 分组 | ✅ | pathItems=5, textFrames=1, groups=1, group_children=2 |
| 导出 PNG24 / SVG | ✅ | PNG 5,863 B（541×337, 94 色）；SVG 32.2 MB |
| `saveAs` .ai（pdfCompatible） | ✅ | 231,830 B |
| **脚本赋渐变填充** | ❌ 见坑 6.2 | Error 1200 Internal error |
| 屏幕级点击/菜单（cua-driver） | 独立链路 | 需驱动在线；本 skill 不依赖它 |

## 5. 直接可用的脚本

- `scripts/illustrator_control_probe.jsx` —— 全操控探针（读 + 新建 + 画图 + 删画板 + 导出 PNG/SVG/.ai + 安全收尾），改路径即用，也是**每次动手前的 30 秒体检**。
- `scripts/run_jsx.vbs` —— 通用 VBS 运行器（把 jsx 绝对路径填进去）。
- `references/gradient-fill-error-1200.md` —— 渐变赋值失败的细节与四条替代路线。

## 6. 坑（PowerShell/COM 层的真实教训）

1. **中文字符经 cscript 回传变乱码**（画板名 `图板 1` → ` 1`）。判断"叫什么"没关系，**别把回传的名字当唯一依据**；要精确比对就回传长度/编码后值，或只回传计数。报告里写计数与矩形，不要复述乱码名字。
2. **`pathItem.fillColor = 渐变` 报 `Error 1200 Internal error`**：新建渐变、改用 `doc.gradients[0]` 默认渐变，两路都失败（`gradientStops` 颜色设置本身不报错，赋值给对象时才炸）。这是脚本 API 层限制，**不是通道问题**。替代路线：① SVG 侧定义渐变后导入；② 两层同形状不同透明度叠色近似线性渐变；③ 让用户手动建好渐变，脚本只改 stop 颜色后重试；④ 交付里如实写"渐变需手动填"。详见 references。
3. **脚本抛错 = 探测文档留在界面上**，后续导出/存盘/关闭全部没执行。写脚本时给易错段包 `try/catch` 并把结果记进回传串（本次做法：`gradient_ok=false (assign_fail:...)`）——错一步不拖垮整条链。
4. **SVG 导出的是整个文档**：对象多的文档轻易上 30 MB（本次 32.2 MB）。要小就按画板裁或先 `ExportType.SVG` 前清理无关图层；交付前看字节数，别把 32 MB 当"轻量矢量"。
5. `documents.add()` 的第二个参数是画板宽高（点，1pt≈1/72in）；A4 纵向画板矩形是 `0,0,595.276,-841.89`（top=0，bottom 为负）。
6. 导出/存盘路径必须在 Windows 存在的目录（`new File()` 不建目录，父目录要先 `write_file` 造出来）。

## 7. 验收（每次交付前一次批量探针，别分轮反复看）

一次性核验三件事，合并成**一次调用**：
1. `os.path.exists + getsize` 三个产物（PNG/SVG/ai）；
2. PNG 真非空白：PIL 打开 → `size` + `getcolors()` 唯一色数（本次 94 色，白底占比高）+ 前几名颜色是否包含预期色；
3. 回传串里用户文档是否 `saved=false`、仍开放。

> ⚠️ 平台侧：连续两轮做同类只读核验（读文件 + 截图）会被循环检测判成"循环失控"并插入强制干预消息。对策就是上面这条：**核验合并成一次，拿到证据就收尾**。

## 8. 汇报口径（用户偏好）

- 中文、结构化：一张能力对照表（能力 / 实测结果），数字全带上。
- **限制如实写**：做不到的（渐变）直接说做不到 + 已试过的替代路径，不粉饰、不假装。
- 结尾给一句"要不要我把这条限制绕过 / 把 GUI 那条链路也修好验一遍"，把选择权交回用户。
- 所有产物路径给全（图/脚本/日志），并说明脚本可复跑。