# -*- coding: utf-8 -*-
"""后台文献翻译进程（批O3 2026-08-16）。

为什么独立进程：webui/server.py 的 __main__ 在 uvicorn 崩溃时会整进程重启，
长翻译任务若跑在 server 线程里会随重启中断。本脚本直接调用 translate_paper，
独立于 server 运行，且自带断点续译（.part.json），可反复重启直到完成。

用法: python scripts/translate_papers_bg.py <file_or_title> [<file_or_title> ...]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "hermes-agent"))
os.environ.setdefault("HERMES_HOME", os.path.join(ROOT, "hermes_home"))

from memomics.bio_tools import literature_library as LL  # noqa: E402


def main():
    files = sys.argv[1:]
    if not files:
        print("用法: python scripts/translate_papers_bg.py <file_or_title> ...")
        return 1
    for f in files:
        print(f"=== 开始翻译: {f} ===", flush=True)
        try:
            r = json.loads(LL.translate_paper(
                f, force=True,
                progress_cb=lambda ph, d, t, det: print(f"[{ph}] {d}/{t} {det}", flush=True)))
            print(f"=== 结果: ok={r.get('ok')} blocks={r.get('blocks')} "
                  f"{r.get('error') or r.get('note') or ''} ===", flush=True)
        except Exception as e:
            print(f"=== 异常: {e} ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
