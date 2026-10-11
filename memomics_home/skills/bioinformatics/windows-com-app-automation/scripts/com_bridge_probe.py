#!/usr/bin/env python
"""通用 COM 应用探针 —— 只读，安全，任何 COM 可自动化应用都能用。

用法:
    python com_bridge_probe.py                          # 默认探 Illustrator
    python com_bridge_probe.py --progid Photoshop.Application
    python com_bridge_probe.py --jsx my_op.jsx          # 跑自定义 JSX
    python com_bridge_probe.py --jsx my_op.jsx --progid Photoshop.Application

退出码: 0 = 桥通 + JSON 可解析；1 = 桥不通 / JSX 报错；2 = 用法错误。

设计要点（实测）:
  * cscript 动态探测，不硬编码盘符
  * JSX 路径传正斜杠（VBScript 里反斜杠会被当转义）
  * stdout 用 errors="replace"（中文 locale 的报错文本会炸 utf-8 解码）
  * ExtendScript 是 ES3：手拼 JSON，最后一条表达式即返回值
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# --- Adobe 系通用只读 JSX：版本 + 文档数 + 文档明细（无文档时优雅返回）---
JSX_INFO = r"""
function esc(s) {
  s = String(s);
  var out = "", i, c;
  for (i = 0; i < s.length; i++) {
    c = s.charAt(i);
    if (c == '"') out += '\\"';
    else if (c == '\\') out += '\\\\';
    else if (c == '\n') out += '\\n';
    else if (c == '\r') out += '';
    else out += c;
  }
  return out;
}
function q(s) { return '"' + esc(s) + '"'; }

var out = '{';
out += '"version":' + q(app.version) + ',';
out += '"doc_count":' + app.documents.length;
if (app.documents.length > 0) {
  var d = app.activeDocument;
  out += ',"active_doc":' + q(d.name);
  out += ',"saved":' + (d.saved ? 'true' : 'false');
  out += ',"path":' + (d.fullName ? q(d.fullName.fsName) : 'null');
  out += ',"artboard_count":' + d.artboards.length;
  out += ',"layer_count":' + d.layers.length;
  out += ',"text_frame_count":' + d.textFrames.length;
} else {
  out += ',"active_doc":null';
}
out += '}';
out + '';
"""


def find_cscript() -> str:
    found = shutil.which("cscript") or shutil.which("cscript.exe")
    if found:
        return found
    for cand in (r"C:\Windows\System32\cscript.exe", r"C:\Windows\SysWOW64\cscript.exe"):
        if Path(cand).exists():
            return str(Path(cand))
    raise RuntimeError("cscript.exe not found（本探针仅适用于 Windows）")


def run_jsx(jsx_body: str, progid: str, timeout: int = 120) -> dict:
    work = Path(tempfile.mkdtemp(prefix="com_probe_"))
    jsx = work / "op.jsx"
    jsx.write_text(jsx_body, encoding="utf-8")
    vbs = work / "run.vbs"
    vbs.write_text(
        "On Error Resume Next\r\n"
        "Dim app, res\r\n"
        f'Set app = CreateObject("{progid}")\r\n'
        "If Err.Number <> 0 Then\r\n"
        '  WScript.Echo "COM_FAIL|" & Err.Description\r\n'
        "  WScript.Quit 1\r\n"
        "End If\r\n"
        f'res = app.DoJavaScriptFile("{jsx.as_posix()}")\r\n'
        "If Err.Number <> 0 Then\r\n"
        '  WScript.Echo "JS_FAIL|" & Err.Description\r\n'
        "  WScript.Quit 2\r\n"
        "End If\r\n"
        'WScript.Echo "RESULT|" & res\r\n',
        encoding="utf-8",
    )
    p = subprocess.run(
        [find_cscript(), "//nologo", str(vbs)],
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )
    out = (p.stdout or "").strip()
    if p.returncode != 0 or out.startswith(("COM_FAIL|", "JS_FAIL|")):
        raise RuntimeError(f"bridge failed rc={p.returncode}: {out or (p.stderr or '')[:300]}")
    if not out.startswith("RESULT|"):
        raise RuntimeError(f"unexpected bridge output: {out[:400]}")
    return json.loads(out[len("RESULT|"):])


def main() -> int:
    ap = argparse.ArgumentParser(description="通用 COM 应用探针（只读）")
    ap.add_argument("--progid", default="Illustrator.Application",
                    help="COM ProgID，如 Photoshop.Application / InDesign.Application")
    ap.add_argument("--jsx", default=None, help="自定义 JSX 文件（须 ES3、末表达式为返回值）")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()

    try:
        cs = find_cscript()
    except RuntimeError as exc:
        print(json.dumps({"bridge": False, "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"bridge": True, "cscript": cs, "progid": args.progid},
                     ensure_ascii=False, indent=2))

    body = Path(args.jsx).read_text(encoding="utf-8") if args.jsx else JSX_INFO
    try:
        res = run_jsx(body, args.progid, args.timeout)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({"ok": True, "result": res}, ensure_ascii=False, indent=2))
    if res.get("doc_count") == 0:
        print("\n注: doc_count=0 表示目标应用当前没有打开的文档 —— 这是诚实状态，不是失败。")
    return 0


if __name__ == "__main__":
    sys.exit(main())