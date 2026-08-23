# -*- coding: utf-8 -*-
"""test_action_promise.py — 反"说而不做"检测函数回归测试（批E，2026-08-16）。

通过 AST 从 webui/server.py 提取 _detect_action_promise 单独执行，
避免 import server.py 引发的完整服务初始化。
覆盖 memomics-2274ab75 事故文本 + 防误伤用例。
"""
import ast
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent / "webui" / "server.py"


def load_fn():
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_detect_action_promise":
            mod = ast.Module(body=[node], type_ignores=[])
            ns = {}
            exec(compile(ast.fix_missing_locations(mod), "<extract>", "exec"), ns)
            return ns["_detect_action_promise"]
    raise SystemExit("FAIL: _detect_action_promise not found in server.py")


CASES = [
    # (text, expected)
    # 1. 事故原文本：先并行扫描 + 产物词 → 必须触发
    ("收到！你重跑了 8 基因版去神经打分，我来：① 扫描新 meta 确认 Denervation 列变化 ② 对比新旧打分 ③ 重出五效应热图 + Fig7。\n\n先并行扫描新文件 + 确认旧文件的 Denervation 基线：", True),
    # 2. 完成叙述 → 不触发
    ("已完成全部分析，结果如下：", False),
    # 3. 条件式提议 → 不触发
    ("如果需要的话我可以先跑一下质控脚本，你确认一下？", False),
    # 4. 征询式结尾（问号/吗）→ 不触发
    ("我先看一下数据分布，你看行吗", False),
    # 5. 纯解释无承诺 → 不触发
    ("AUCell 打分原理是基于基因集排序富集，共 8 个基因。", False),
    # 6. 旧词表保留：先读回 + 结果 → 触发
    ("先读回上一步的结果文件，确认列名。", True),
    # 7. Tier B：编号计划 + 计划动词 + 无完成叙述 → 触发
    ("我来：① 扫描新 meta ② 对比打分 ③ 出五效应图", True),
    # 8. Tier B：编号列表但是交付物本身（建议方案，无计划动词）→ 不触发
    ("建议方案：① 用 Seurat ② 用 monocle3。", False),
    # 9. 结尾在正文前部有承诺、尾部已交付 → 不触发（旧三重 AND 的末尾 300 字符窗口）
    ("先查一下文献。……以上是完整文献综述，供参考。", False),
    # 10. 先重跑 + 打分（v4 新词）→ 触发
    ("先重跑去神经打分，对比新旧分数。", True),
    # 11. 先确认 + 基线（v4 新词）→ 触发
    ("先确认旧文件的 Denervation 基线：", True),
    # 12. 末尾 300 字符窗口：承诺在长回复开头、尾部无承诺 → 不触发
    ("先看一下文件内容。" + "补充说明。" * 80, False),
]


def main():
    fn = load_fn()
    fails = 0
    for i, (text, expected) in enumerate(CASES, 1):
        got = fn(text, [{"tool": "scan_data"}])
        ok = got == expected
        if not ok:
            fails += 1
        print(f"case {i:2d}: got={got} expected={expected} {'PASS' if ok else 'FAIL'} | {text[:46]}")
    print("RESULT:", "ALL PASS" if fails == 0 else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
