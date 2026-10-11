# Illustrator COM/ExtendScript harness —— 实测记录

> 2026-10-04 全链路实跑验证。**任何关于"能不能操控 Illustrator"的结论以此为准**，
> 不要凭印象回答。

## 1. 实测结论（真实返回，非"成功"）

```
$ cli-anything-illustrator --json doctor
{ "bridge": true,
  "cscript": "C:\\WINDOWS\\system32\\cscript.EXE",
  "illustrator": { "doc_count": 0, "active_doc": null } }

$ cli-anything-illustrator --json probe --text "MemOmics Illustrator CLI" --size 14
{ "pathitems": 1, "textframes": 1,
  "text": "MemOmics Illustrator CLI", "size": 14,
  "png": "C:\\Users\\<user>\\AppData\\Local\\Temp/memomics_cli_probe.png",
  "png_exists": true, "png_bytes": 2395 }

$ cli-anything-illustrator --json gradient-probe        # 渐变绕过实测
{ "gradient_swatches": [], "gradient_count": 0,
  "swatch_typenames": ["Swatch"], "gradients_collection": 5,
  "applied_via_swatch": false, "applied_via_collection": false,
  "applied_via_gradientcolor": true,
  "used_name": null, "error": null, "pathitems": 1 }
```

**读法**：`doc_count: 0` 是**诚实状态**（当时确实没有打开的文档），不是失败。
探测类命令必须能在无文档时正常返回——agent 要能自己判断，而不是收异常。

## 2. 渐变（gradient）的完整真相

三条实测事实（缺一不可）：

1. **新建 RGB 文档的 `swatches` 里没有渐变**：`swatch_typenames` 只有 `["Swatch"]`，
   `gradient_count = 0` → 所以 `swatches.getByName(<渐变名>)` 是**必然失败路径**。
2. **但 `doc.gradients` 有 5 个**（`gradients_collection: 5`）→ 走 `doc.gradients[i]`。
3. **不能把 Gradient 直接当颜色**：`rect.fillColor = doc.gradients[0]` → `Internal error`
   （中文 locale 下错误文本是乱码，别被吓到）。必须包一层 `GradientColor`：

```js
var gc = new GradientColor();
gc.gradient = doc.gradients[0];
gc.origin = [80, 260];
gc.angle = 45;
rect.fillColor = gc;          // → applied_via_gradientcolor: true, error: null
```

## 3. 颜色（非渐变）

`Error 1302: No such element` ← 在 **RGB 文档**里取 `swatches.getByName("CMYK Red")`。
别用色板名，直接构造：

```js
var rgb = new RGBColor();
rgb.red = 240; rgb.green = 90; rgb.blue = 70;
rect.fillColor = rgb;
```

## 4. harness 结构与命令

```
results/<sid>/software_control/illustrator/agent-harness/
├── setup.py                                  # cli_anything.* 命名空间包 + console_scripts
└── cli_anything/illustrator/
    ├── __init__.py  __main__.py
    ├── illustrator_cli.py                    # Click：doctor/info/artboards/text-list/
    │                                         #        text-set/export/probe/gradient-probe/repl
    └── utils/illustrator_backend.py          # run_jsx + 各 op 的 JSX 正文
```

安装：`<项目 venv>/python -m pip install -e .` → 得到 `cli-anything-illustrator`。

| 命令 | 作用 | 写操作？ |
|------|------|---------|
| `doctor` | 桥探活 + cscript 路径 + 文档数 | 否 |
| `info` | 版本/文档数/画板数/图层数/文字框数/路径项数 | 否 |
| `artboards` | 列画板（名称/矩形/哪个是活动画板） | 否 |
| `text-list` | 列文字框（内容/字号/字体/包围盒） | 否 |
| `text-set` | **全文档文字框批量设字号/字体** | 是（**不保存**） |
| `export` | 活动文档导出 PDF/SVG/PNG | 是（落盘到指定路径） |
| `probe` | 隔离新文档：矩形+文字+导 PNG+不保存关闭 | 是（独立文档） |
| `gradient-probe` | 渐变绕过验证（同上，隔离文档） | 是（独立文档） |
| `repl` | 交互模式（默认入口） | — |

## 5. 用户偏好（本会话确认过的做法）

- 用户要的是**可验证**："能不能完全操控"→ 用**真实返回**回答（doctor/probe 的 JSON 原样贴出），
  不要口头承诺"可以"。
- **演示一律在独立文档里做**，用户正在编辑的文件毫发无损；收尾明确声明
  「你的文档未被改动」并给出 `saved` 状态。
- 能力边界要说实话：画布上的图元**不在无障碍树里**（UI 驱动只能按坐标点，依赖缩放）；
  精确的对象级操作走脚本，不走截图。
- 用户日常用 Illustrator 做论文图 → 最有价值的命令是**批量**类
  （`text-set` 统一字号/字体、`export` 批量导出变体），而不是单点微调。