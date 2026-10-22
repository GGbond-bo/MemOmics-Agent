# -*- coding: utf-8 -*-
"""未定义函数扫描 v2（2026-10-22 事故后加的护栏）。

事故背景：index.html 的 openProviderKeyModal() 里调用了不存在的 pkmProbeStatus()，
打开弹窗即抛 ReferenceError → 弹窗打不开，用户报「没办法点击添加key/拉取模型」。

判定策略（逐行，避开「注释夹在名字与括号之间」的坑）：
  1) 逐行提取「标识符 + 紧随的 (」→ 视为候选（跳过 obj.name(、关键字）；
  2) 同一行内出现声明形态（function/var/let/const/class/`=`/`:`）→ 认定已定义；
  3) 未认定的，再到**全文**里找跨行声明形态（如 `xxx = function(...)` 换行写法）。
白名单：浏览器内置、第三方库对象、事件回调参数（resolve/reject）。
离线、不启浏览器、不依赖 node 运行代码（只用 node --check 验语法）。
"""
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "..", "index.html")

WHITELIST = {
    # 浏览器内置 / 构造器
    "Float32Array", "WebSocket", "Uint8Array", "Int32Array", "ArrayBuffer", "Promise",
    "Date", "RegExp", "Map", "Set", "WeakMap", "URL", "Blob", "File", "FormData",
    "Image", "Audio", "Worker", "Error", "TypeError", "AbortController", "Event",
    "CustomEvent", "TextEncoder", "TextDecoder", "ResizeObserver", "MutationObserver",
    "IntersectionObserver", "BroadcastChannel", "XMLHttpRequest", "Headers", "Request",
    "Response", "Notification", "AudioContext", "OffscreenCanvas", "Path2D", "DOMParser",
    # 语言关键字 / 语法噪声 / CSS 文本
    "if", "for", "while", "switch", "catch", "return", "typeof", "function", "await",
    "do", "else", "in", "of", "new", "delete", "void", "throw", "case",
    "calc", "var", "rgba", "inset", "translateX", "repeat", "min", "max", "url",
    # 第三方库（CDN 上）
    "cytoscape", "mermaid", "Chart", "katex", "renderMathInElement", "hljs", "MarkdownIt",
    "Sortable", "anime", "QRCode", "Howl", "L", "d3", "THREE", "XLSX",
    # 需要时由外层提供 / 运行时注入
    "setTimeout", "setInterval", "clearTimeout", "clearInterval", "requestAnimationFrame",
    "cancelAnimationFrame", "fetch", "alert", "confirm", "prompt", "atob", "btoa",
    "parseInt", "parseFloat", "isNaN", "isFinite", "encodeURIComponent", "decodeURIComponent",
    "escapeHtml", "structuredClone", "queueMicrotask",
    # 回调参数（Promise 执行器 / 数组方法）
    "resolve", "reject", "next", "done", "callback", "cb",
    # 本次新增能力中用到的局部闭包名称（定义在函数体内，逐行判定已覆盖，双保险）
    "guEsc", "nbEsc", "_dsEsc", "_jsArg", "_citeAttr", "_citeWrapHtml",
}
# 看起来像调用但其实是文本/正则碎片的常见词（中英文文案、正则分组名）
TEXT_NOISE = re.compile(r"^[A-Z][a-z]+$")


def inline_scripts(html):
    return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)


def strip_strings_and_comments(js):
    """注释/字符串替换为空白（用于语法校验与「代码形态」判定）。"""
    out, i, n = [], 0, len(js)
    while i < n:
        c, two = js[i], js[i:i + 2]
        if two == "//":
            j = js.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif two == "/*":
            j = js.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(" " * (j - i)); i = j
        elif c in "\"'`":
            q, j = c, i + 1
            while j < n:
                if js[j] == "\\":
                    j += 2; continue
                if js[j] == q:
                    j += 1; break
                j += 1
            out.append(" " * (j - i)); i = j
        else:
            out.append(c)
            i += 1

    return "".join(out)


def _strip_comments_only(js):
    """只剥注释、**保留字符串字面量**（字符串里的分隔符/文案才看得到）。

    注意不要在这一层处理字符串：'\\u0001' 里的反斜杠转义会被当成字符串结束误判，
    导致把后面的代码整段吞掉（踩过这个坑）。
    """
    out, i, n = [], 0, len(js)
    while i < n:
        two = js[i:i + 2]
        if two == "//":
            j = js.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif two == "/*":
            j = js.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(" " * (j - i)); i = j
        else:
            out.append(js[i]); i += 1
    return "".join(out)


def strip_regex_literals(code):
    """把正则字面量 /xxx/ 里的内容抹掉（否则 \\u0060( 这种会被当成函数调用）。

    保守处理：只在 `/` 紧跟 `=` `(` `,` `:` `[` `!` `&` `|` `?` `{` `;` `return` 之后、
    且能配对找到收尾 `/` 时，才认为是正则字面量。
    """
    out, i, n = [], 0, len(code)
    prev_sig = "="
    while i < n:
        c = code[i]
        if c == "/" and code[i:i + 2] not in ("//", "/*") and prev_sig in "=(,:![&|?{;>+" :
            j, k = i + 1, i + 1
            closed = False
            while k < n:
                if code[k] == "\\":
                    k += 2
                    continue
                if code[k] == "\n":      # 正则不能跨行
                    break
                if code[k] == "/":
                    closed = True
                    j = k + 1
                    break
                k += 1
            if closed:
                while j < n and code[j].isalpha():   # 跳过 flags
                    j += 1
                out.append(" " * (j - i))
                prev_sig = "/"
                i = j
                continue
        out.append(c)
        if not c.isspace():
            prev_sig = c
        i += 1
    return "".join(out)


def guarded_names(js):
    return set(re.findall(r"typeof\s+([A-Za-z_$][\w$]*)\s*===?\s*['\"]function['\"]", js))


def main():
    html = io.open(INDEX, encoding="utf-8").read()
    raw_js = "\n;\n".join(inline_scripts(html))
    code = strip_regex_literals(strip_strings_and_comments(raw_js))
    print(f"内联脚本 {len(raw_js)} 字符 | 剥注释/字符串/正则后 {len(code)} 字符")

    # 回归钉：事故函数名不得作为代码出现
    ghost = "pkmProbe" + "Status"
    assert not re.search(re.escape(ghost) + r"\s*\(", code), f"{ghost} 又作为代码出现——弹窗会打不开"
    print(f"✅ 回归钉：{ghost} 无代码引用")

    # 回归钉 2（2026-10-22 第二个事故）：模型下拉的选项值分隔符必须是**真 U+0001**。
    # 曾写成 '\\u0001'（字面量反斜杠+u0001），而解析端 split('\u0001') 按真控制字符分，
    # 导致 provider_id 丢失、模型名带尾巴 → 切换时报「模型 'xxx' 未配置 API Key」。
    # 只在**注释之外**查：字符串字面量必须保留（分隔符就在字符串里），所以这里
    # 用一个只剥注释的扫描器，而不是把字符串一起剥掉的那个。
    code_only = _strip_comments_only(raw_js)
    sep_uses = re.findall(r"[\"']\\\\u0001[\"']", code_only)   # 源码里的字面量形态
    assert not sep_uses, (
        f"发现 {len(sep_uses)} 处字面量 '\\\\u0001' 作分隔符——必须是真 U+0001（\\u0001），否则模型切换必失败")
    real_sep = re.findall(r"[\"']\\u0001[\"']", code_only)
    assert len(real_sep) >= 2, f"模型分隔符 U+0001 用法太少（{len(real_sep)} 处），下拉可能被改坏"
    print(f"✅ 回归钉 2：模型下拉分隔符为真 U+0001（{len(real_sep)} 处），无字面量残留")

    # 语法
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(raw_js); tmp = f.name
    try:
        r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
        assert r.returncode == 0, "语法错误:\n" + (r.stderr or "")[:800]
        print("✅ node --check 通过")
    finally:
        os.unlink(tmp)

    guards = guarded_names(raw_js) | guarded_names(code)
    lines = code.split("\n")
    decl_form = re.compile(r"(?:function|var|let|const|class)\s|=\s*function|=>|\w\s*:\s*function")
    line_has = {}
    for ln in lines:
        for m in re.finditer(r"(^|[^\w$.])([A-Za-z_$][\w$]*)\s*\(", ln):
            name = m.group(2)
            if name in WHITELIST or name in guards:
                continue
            prev = name in line_has
            # 同一行有声明形态（function xxx( / xxx = function / xxx = (a) => / {xxx: function）
            if decl_form.search(ln):
                line_has[name] = True
            elif not prev:
                line_has[name] = False

    # 全文跨行兜底
    def declared_anywhere(name):
        n = re.escape(name)
        pats = [
            r"\bfunction\s+" + n + r"\s*\(",
            r"\b(?:const|let|var)\s+" + n + r"\b",
            r"\bclass\s+" + n + r"\b",
            r"\b" + n + r"\s*=\s*(?:async\s*)?(?:function|\()",
            r"\b" + n + r"\s*=\s*[A-Za-z_$][\w$]*\s*=>",
            r"[\w$.)\]]+\s*" + n + r"\s*=\s*(?:async\s*)?(?:function|\()",
            r"\b" + n + r"\s*:\s*(?:async\s*)?(?:function|\()",
        ]
        return any(re.search(p, raw_js) for p in pats)

    bad = []
    for name, ok in sorted(line_has.items()):
        if ok or name in WHITELIST or name in guards:
            continue
        if TEXT_NOISE.match(name) and declared_anywhere(name) is False:
            # 形如 'DCS Cloud (' 的文本碎片：既无声明又无 CamelCase 函数命名习惯 → 视为噪声
            ctxs = re.findall(r".{0,40}" + re.escape(name) + r"\s*\(", raw_js)
            if ctxs and not any("-" in c or "_" in c for c in ctxs[:2]):
                continue
        if declared_anywhere(name):
            continue
        bad.append(name)

    print(f"候选标识符 {len(line_has)} 个 | 未找到声明: {len(bad)}")
    if bad:
        print("❌ 可疑：")
        for n in bad:
            ctx = re.search(r".{0,70}" + re.escape(n) + r"\s*\(", raw_js)
            print(f"   - {n} | 例: {ctx.group(0).strip()[:90] if ctx else ''}")
        sys.exit(1)
    print("✅ 没有「被调用但未定义」的函数")


if __name__ == "__main__":
    main()