# -*- coding: utf-8 -*-
"""复检逻辑的离线回归（2026-10-22）：验证「换 key / 上游恢复」后旧标记能被清掉。

用户反馈背景：「设置 → 模型(选择默认) 这里，模型明明可用，怎么就显示不可用呢？」
实测有两类：① key 真失效（deepseek 401×2，标记正确）；② 换 key / 上游恢复后
旧结论卡着（标记过期）。本测试针对 ②：用本地假上游让模型恢复可用，
断言复检后 usable 翻正、并从 pruned 里移除；同时断言真失败的仍然保持标记。
"""
import io
import json
import os
import re
import sys
import tempfile
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_PY = os.path.join(HERE, "..", "server.py")

# 状态：哪些模型现在可用（模拟上游恢复）
AVAILABLE = {"m-recovered", "m-ok"}


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        model = (json.loads(self.rfile.read(n).decode("utf-8")) or {}).get("model", "")
        if model in AVAILABLE:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode())
        else:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "Model does not support this protocol."}}).encode())


def extract(name):
    src = io.open(SERVER_PY, encoding="utf-8").read()
    m = re.search(r"^def " + name + r"\(.*?(?=^\S|\Z)", src, re.S | re.M)
    assert m, f"找不到 {name}"
    return m.group(0).replace("\r", "")


def main():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}/v1"

    path = os.path.join(tempfile.mkdtemp(prefix="memomics_recheck_"), "provider_keys.json")
    ns = {
        "_provider_keys": {"demo": {
            "api_key": "sk-demo-key-123456",
            "models": [{"id": "m-ok"}, {"id": "m-recovered"}],
            "probe": {
                "results": {
                    "m-ok": {"id": "m-ok", "usable": True, "status": 200, "error": "", "ms": 10},
                    # 上次判不可用（当时上游确实坏了），现在已恢复
                    "m-recovered": {"id": "m-recovered", "usable": False, "status": 400,
                                    "error": "该模型不支持 OpenAI /chat/completions 协议…", "ms": 10},
                    "m-dead": {"id": "m-dead", "usable": False, "status": 400,
                               "error": "协议不支持", "ms": 10},
                },
                "known_ids": ["m-ok", "m-recovered", "m-dead"],
                "pruned": {"ids": ["m-recovered", "m-dead"], "at": "2026-10-22 00:00:00"},
                "tested": 3, "usable": 1, "failed": 2,
            },
        }},
        "datetime": datetime,
        "_save_provider_keys": lambda: io.open(path, "w", encoding="utf-8").write(
            json.dumps(ns["_provider_keys"], ensure_ascii=False)),
        "_sync_custom_providers_to_memomics": lambda pid=None: None,
        "_PROBE_MAX_WORKERS": 3, "_PROBE_TIMEOUT": 30.0,
        "_PROBE_JOBS": {}, "_PROBE_LOCK": threading.Lock(),
        "_provider_extra_headers_for": lambda api: {},
    }
    # 注入真实实现：探针 + 复检 + 剪除
    import sys as _sys
    _sys.path.insert(0, r"<安装目录>")
    from memomics.coding_plans import probe_chat_model
    ns["probe_chat_model"] = probe_chat_model
    for fn in ("_prune_models_from_saved", "_run_model_recheck"):
        exec(compile(extract(fn), f"<server.py:{fn}>", "exec"), ns)

    print("=== 复检前 ===")
    p = ns["_provider_keys"]["demo"]["probe"]
    print("  m-recovered usable =", p["results"]["m-recovered"]["usable"], "| pruned =", p["pruned"]["ids"])
    assert p["results"]["m-recovered"]["usable"] is False
    assert "m-recovered" in p["pruned"]["ids"]

    print("\n=== 跑复检（本地假上游：m-recovered 已恢复）===")
    ns["_run_model_recheck"]("demo", {"api": base}, "sk-demo-key-123456", ["m-recovered", "m-dead"])
    p2 = ns["_provider_keys"]["demo"]["probe"]
    r = p2["results"]
    print("  m-recovered usable =", r["m-recovered"]["usable"], "|", r["m-recovered"].get("error", ""))
    print("  m-dead      usable =", r["m-dead"]["usable"], "|", r["m-dead"].get("error", "")[:50])
    print("  pruned =", (p2.get("pruned") or {}).get("ids"))
    print("  统计: tested=%s usable=%s failed=%s" % (p2.get("tested"), p2.get("usable"), p2.get("failed")))

    assert r["m-recovered"]["usable"] is True, "恢复的模型必须翻正"
    assert r["m-recovered"].get("error", "") == "", "翻正后不该留旧错误"
    assert r["m-dead"]["usable"] is False, "真不可用的必须保持标记"
    assert "m-recovered" not in ((p2.get("pruned") or {}).get("ids") or []), "翻正的应从 pruned 移除"
    assert "m-dead" in ((p2.get("pruned") or {}).get("ids") or []), "仍失败的保留在 pruned"

    srv.shutdown()
    print("\n✅ 复检离线回归全通过（恢复→翻正清标；真失败→保持标记）")


if __name__ == "__main__":
    sys.exit(main())