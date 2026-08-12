# -*- coding: utf-8 -*-
"""持久 kernel worker（P0-1）：stdin/stdout 行式 JSON 协议

请求: {"id": "1", "code": "..."}
响应: {"id": "1", "stdout": "...", "stderr": "...", "error": null|"..."}

exec 命名空间常驻（_NS），跨请求保留变量/模块状态。
单表达式代码（如 x*2）按 Jupyter cell 语义回显 repr 值。
"""
import ast
import contextlib
import io
import json
import sys
import traceback

_NS = {"__name__": "__main__"}


def _execute(code, out, err):
    """执行代码块；单表达式回显值（Jupyter 语义）"""
    tree = ast.parse(code, "<cell>", mode="exec")
    if len(tree.body) == 1 and isinstance(tree.body[0], ast.Expr):
        val = eval(compile(ast.Expression(body=tree.body[0].value), "<cell>", "eval"), _NS)
        if val is not None:
            out.write(repr(val) + "\n")
    else:
        exec(compile(code, "<cell>", "exec"), _NS)


def _run():
    # EOF：宿主关闭管道 → for 循环自然结束 → 进程退出（已正确处理，不会成孤儿）
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        # 宿主优雅关闭帧 {"type": "shutdown"} → 退出
        if req.get("type") == "shutdown":
            break
        code = req.get("code", "")
        rid = req.get("id", "")
        out, err = io.StringIO(), io.StringIO()
        error = None
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                _execute(code, out, err)
        except BaseException as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
            err.write(traceback.format_exc())
        sys.stdout.write(json.dumps(
            {"id": rid, "stdout": out.getvalue(), "stderr": err.getvalue(), "error": error},
            ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    _run()
