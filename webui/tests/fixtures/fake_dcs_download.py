# -*- coding: utf-8 -*-
"""假 dcs 下载器：给「下载队列」回归测试用（真进程、真落盘、分块写、带进度行）。

用法（测试里通过 monkeypatch 把 dc._dl_spawn 指过来）：
    real([sys.executable, "-X", "utf8", <本文件>] + argv[1:])

行为：把 <target>/<basename(--path)> 分 4 块写出来（模拟下载进度），每块之间 sleep；
      最后打印与官方 CLI 同款的 JSON 信封；--path 里含 "fail" 时返回 83003 业务错误。
环境变量：FAKE_SIZE（字节，默认 3 MiB）、FAKE_DELAY（每块秒数，默认 0.6）。
"""
import json
import os
import sys
import time


def _opt(name, default=""):
    args = sys.argv[1:]
    return args[args.index(name) + 1] if name in args else default


def main() -> int:
    path = _opt("--path")
    target = _opt("--target")
    size = int(os.environ.get("FAKE_SIZE", str(3 * 1024 * 1024)))
    delay = float(os.environ.get("FAKE_DELAY", "0.6"))
    if not path or not target:
        print(json.dumps({"data": None, "exit_code": 2,
                          "error": {"type": "cli", "detail": {"message": "缺 --path/--target"}}},
                         ensure_ascii=True))
        return 2
    if "fail" in path:
        print(json.dumps({"data": None, "exit_code": 1, "message": "请先选择项目",
                          "error": {"type": "business",
                                    "detail": {"business_code": 83003, "message": "请先选择项目"}},
                          "request_id": "req-fake-fail"}, ensure_ascii=True))
        return 1
    os.makedirs(target, exist_ok=True)
    dest = os.path.join(target, os.path.basename(path.rstrip("/")))
    chunk = max(1, size // 4)
    with open(dest, "wb") as fh:
        for i in range(4):
            fh.write(b"\0" * chunk)
            fh.flush()
            print("progress %d/4" % (i + 1))
            sys.stdout.flush()
            time.sleep(delay)
    print(json.dumps({"data": {"downloaded": path, "target": target, "local": dest},
                      "exit_code": 0, "message": "", "request_id": "req-fake-ok"}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())