# 可复制的 Windows COM → ExtendScript 桥脚手架

> 已在 **Adobe Illustrator** 上实跑验证（2026-10-04）。同构适用于任何提供 COM 自动化 +
> 脚本引擎的 Windows 应用：**Photoshop / InDesign / Word / Excel / PowerPoint / Visio**。
> 用法：把下面三块抄进你的 harness，改 `CreateObject` 的 ProgID 和各 op 的 JSX 正文即可。

## 为什么用这条路

GUI 应用没有 CLI。但 Windows 上的商业软件大多暴露 **COM 自动化接口**，
并配一个**脚本引擎**（Adobe 系 = ExtendScript/JSX）。桥的形状固定：

```
Python(Click CLI)  →  cscript.exe  →  VBScript
                                    →  CreateObject("<ProgID>")
                                    →  <App>.DoJavaScriptFile(<jsx 路径>)
                                    →  JSX 返回 JSON 字符串 → Python json.loads
```

比截图点坐标可靠得多：**确定性、快、不需要焦点、可重跑**。

## 各应用 ProgID 与脚本入口（替换点）

| 应用 | ProgID | 脚本入口 |
|------|--------|---------|
| Illustrator | `Illustrator.Application` | `DoJavaScriptFile(path)` |
| Photoshop | `Photoshop.Application` | `DoJavaScriptFile(path)` |
| InDesign | `InDesign.Application` | `DoScript(script, language)` |
| Word | `Word.Application` | `Run(macroName)`（或 VBA 宏） |
| Excel | `Excel.Application` | `Run(macroName)` |

## 1) VBScript 运行器（生成到临时目录再跑，别提交）

```vb
On Error Resume Next
Dim app, res
Set app = CreateObject("Illustrator.Application")     ' ← 换 ProgID
If Err.Number <> 0 Then
  WScript.Echo "COM_FAIL|" & Err.Description
  WScript.Quit 1
End If
res = app.DoJavaScriptFile("<JSX 绝对路径，正斜杠>")     ' ← 换脚本入口
If Err.Number <> 0 Then
  WScript.Echo "JS_FAIL|" & Err.Description
  WScript.Quit 2
End If
WScript.Echo "RESULT|" & res
```

调用：`cscript //nologo run.vbs` → 解析 stdout 的 `RESULT|` / `COM_FAIL|` / `JS_FAIL|` 前缀。

⚠️ **VBScript 里 JSX 路径必须用正斜杠**（`E:/path/op.jsx`）。反斜杠会被当转义序列
（`\t`、`\n` 会变成真字符），路径静默失效。

## 2) JSX 前置（**必须**，ExtendScript 是 ES3、没有 JSON 对象）

```js
// 手动拼 JSON：ExtendScript 无 JSON.stringify，靠 esc() 转义
function esc(s) {
  s = String(s);
  var out = "", i, c;
  for (i = 0; i < s.length; i++) {
    c = s.charAt(i);
    if (c == '"') out += '\\"';
    else if (c == '\\') out += '\\\\';
    else if (c == '\n') out += '\\n';
    else if (c == '\r') out += '';
    else if (c == '\t') out += ' ';
    else out += c;
  }
  return out;
}
function q(s) { return '"' + esc(s) + '"'; }
function num(n) { return (isNaN(n) ? 'null' : String(n)); }
```

输出约定：JSX 的**最后一条表达式**就是返回值（`out + '';`），被 VBS 的 `res` 接住。
**不要用 `return`**——顶层 `return` 在 ExtendScript 里会报错。

## 3) Python 侧要点

```python
def find_cscript() -> str:
    """动态探测，别硬编码盘符。"""
    found = shutil.which("cscript") or shutil.which("cscript.exe")
    if found:
        return found
    for cand in (r"C:\Windows\System32\cscript.exe", r"C:\Windows\SysWOW64\cscript.exe"):
        if Path(cand).exists():
            return Path(cand)
    raise RuntimeError("cscript.exe not found")


def run_jsx(jsx_body: str, progid="Illustrator.Application", timeout=180) -> dict:
    workdir = Path(tempfile.mkdtemp(prefix="com_cli_"))
    jsx = workdir / "op.jsx";  jsx.write_text(jsx_body, encoding="utf-8")
    vbs = workdir / "run.vbs"
    vbs.write_text(
        "On Error Resume Next\r\n"
        "Dim app, res\r\n"
        f'Set app = CreateObject("{progid}")\r\n'
        "If Err.Number <> 0 Then\r\n"
        '  WScript.Echo "COM_FAIL|" & Err.Description\r\nWScript.Quit 1\r\nEnd If\r\n'
        f'res = app.DoJavaScriptFile("{jsx.as_posix()}")\r\n'          # ← 正斜杠
        "If Err.Number <> 0 Then\r\n"
        '  WScript.Echo "JS_FAIL|" & Err.Description\r\nWScript.Quit 2\r\nEnd If\r\n'
        'WScript.Echo "RESULT|" & res\r\n',
        encoding="utf-8")
    p = subprocess.run([find_cscript(), "//nologo", str(vbs)],
                       capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")           # ← 防中文 locale 解码炸
    out = (p.stdout or "").strip()
    if p.returncode != 0 or out.startswith(("COM_FAIL|", "JS_FAIL|")):
        raise RuntimeError(f"bridge failed rc={p.returncode}: {out or p.stderr}")
    if not out.startswith("RESULT|"):
        raise RuntimeError(f"unexpected bridge output: {out[:400]}")
    return json.loads(out[len("RESULT|"):])
```

## 4) 安全铁律（血泪）

| 铁律 | 说明 |
|------|------|
| **绝不保存用户文档** | 探测/演示一律新建独立文档，收尾 `doc.close(SaveOptions.DONOTSAVECHANGES)` |
| **颜色不要靠色板名** | RGB 文档里 `swatches.getByName("CMYK Red")` → `Error 1302: No such element`。直接 `new RGBColor()` 设 r/g/b |
| **渐变不要直接赋值** | `rect.fillColor = doc.gradients[0]` → `Internal error`。必须 `new GradientColor()` + `.gradient/.origin/.angle` |
| **渐变色板不在 swatches 里** | 新建 RGB 文档 `swatches` 的 `typename` 只有 `"Swatch"`，但 `doc.gradients` 有 5 个 → 走 `doc.gradients[i]` |
| **先 doctor 再动** | 第一个命令永远是只读探活（桥通不通 + 当前文档数），再谈写操作 |
| **只读命令要能在无文档时优雅返回** | `{"doc_count":0,"active_doc":null}` 比抛异常好——agent 要能自己判断 |

## 5) 验证清单（新桥接一个应用时按序做）

1. `doctor`：桥通不通、cscript 路径、当前文档数 → 期望 `bridge: true`
2. 只读 op：枚举文档/对象计数 → 期望真实数字（无文档时诚实返回 0）
3. **隔离写 op**：新建独立文档 → 画一个对象 → 写一段文字 → 导出 PNG → **不保存关闭**
4. 校验产物：`png_exists: true` + `png_bytes > 0`，并 `ls` 复核落盘
5. 记录真实返回（把 JSON 原样写进文档的"已验证"段），不要只写"成功"

> 第 3 步的关键：**在独立文档里做写操作**，用户正在编辑的文件全程零风险。
> 这是把"能操控"证明给用户看、又不动他数据的最佳方式。

## 6) harness 骨架（CLI-Anything 规范，可直接套）

```text
<app>/agent-harness/
├── setup.py                       # find_namespace_packages(include=["cli_anything.*"])
│                                  # console_scripts: cli-anything-<app>
└── cli_anything/<app>/
    ├── __init__.py
    ├── __main__.py
    ├── <app>_cli.py               # Click 命令组：doctor/info/.../probe/repl
    └── utils/<app>_backend.py     # 上面 run_jsx + 各 op 的 JSX 正文
```

约定（与 CLI-Anything 生态一致，别自创）：
- `--json` 是 **group 级选项**，必须写在子命令**之前**
- 无子命令 → 进 REPL
- 每个子命令是独立进程 → **session 不跨进程**，有状态序列要么传 `--project <file>`，要么进 REPL