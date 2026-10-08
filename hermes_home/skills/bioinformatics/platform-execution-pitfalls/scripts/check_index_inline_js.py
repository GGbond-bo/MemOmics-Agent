#!/usr/bin/env python3
"""webui/index.html 内联 <script> 语法自检（node --check）。

改完前端后确认内联 JS 没语法错误，不需要开浏览器。
抽出所有不带 src 的 <script> 块 → 逐个写临时 .js → node --check。

用法：
    .venv/Scripts/python.exe <skill_dir>/scripts/check_index_inline_js.py
    # 或指定别的 html：
    .venv/Scripts/python.exe .../check_index_inline_js.py path/to/other.html

退出码：0=全部 OK，1=有块语法错误。
自带仓库根自动发现（向上找含 webui/index.html 的目录），脚本放哪都能跑。
"""
import os
import re
import subprocess
import sys
import tempfile


def _find_repo_root(start):
    """自 start 向上找含 webui/index.html 的目录。"""
    d = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(d, "webui", "index.html")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            raise SystemExit("找不到仓库根（缺 webui/index.html）")
        d = parent


def main(argv):
    if len(argv) > 1:
        index = os.path.abspath(argv[1])
    else:
        root = _find_repo_root(os.path.dirname(os.path.abspath(__file__)))
        index = os.path.join(root, "webui", "index.html")

    if not os.path.isfile(index):
        raise SystemExit("找不到 %s" % index)

    with open(index, encoding="utf-8") as fh:
        html = fh.read()

    # 只取内联块：<script ...> 但不能带 src=
    blocks = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
    print("%s -> inline script blocks: %d" % (index, len(blocks)))

    failed = 0
    for i, code in enumerate(blocks):
        if not code.strip():
            continue
        fd, path = tempfile.mkstemp(suffix=".js")
        os.close(fd)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(code)
            r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
            lines = code.count("\n") + 1
            if r.returncode != 0:
                failed += 1
                print("block %d: FAIL (%d lines)" % (i, lines))
                print(r.stderr.strip()[:1200])
            else:
                print("block %d: OK (%d lines)" % (i, lines))
        finally:
            os.unlink(path)

    print("RESULT: %s" % ("FAIL" if failed else "OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))