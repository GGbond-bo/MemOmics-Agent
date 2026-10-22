# -*- coding: utf-8 -*-
"""回归钉：chat 端点的候选路径必须覆盖「base 已含 /v1」与「base 不含 /v1」两种网关。

事故（2026-10-22 用户反馈「kimi 编程套餐四个模型明明都能用，为什么又不可以」）：
探针固定拼 <base>/chat/completions，而 Kimi 套餐的 chat 在 /coding/v1/chat/completions
→ 4 个模型全被误判 404 不可用。本测试用「只接受 /v1 路径」的假上游复现并锁死修复。
"""
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, r"E:\MemOmics-Agent")

from memomics.coding_plans import _candidate_chat_urls, probe_chat_model  # noqa: E402

HITS = []


class V1Only(BaseHTTPRequestHandler):
    """/v1/chat/completions 才认（Kimi 套餐风格）。"""

    def log_message(self, *a):
        pass

    def do_POST(self):
        HITS.append(self.path)
        if self.path.endswith("/v1/chat/completions"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"choices":[{"message":{"content":"hi"}}]}')
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"The requested resource was not found"}}')


def main():
    print("=== 1) 候选路径生成 ===")
    cases = {
        "https://api.kimi.com/coding": [
            "https://api.kimi.com/coding/chat/completions",
            "https://api.kimi.com/coding/v1/chat/completions"],
        "https://opencode.ai/zen/go/v1": [
            "https://opencode.ai/zen/go/v1/chat/completions"],
        "https://dcsapi.dcs.cloud/api/aigress/unified/v1": [
            "https://dcsapi.dcs.cloud/api/aigress/unified/v1/chat/completions"],
        "https://api.deepseek.com/v1": ["https://api.deepseek.com/v1/chat/completions"],
    }
    for base, want in cases.items():
        got = _candidate_chat_urls(base)
        print(f"  {base}")
        print(f"    -> {got}")
        assert got == want, f"{base} 候选不对: {got} != {want}"
    print("  ✅ 四类网关（含/不含 /v1）都正确")

    print("\n=== 2) 真跑：假上游只认 /v1（复现 Kimi 场景）===")
    srv = HTTPServer(("127.0.0.1", 0), V1Only)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    provider = {"api": f"http://127.0.0.1:{port}/coding",
                "extra_headers": {"User-Agent": "claude-code/0.1.0"}}
    r = probe_chat_model(provider, "sk-kimi-test-123456", "k3", timeout=10)
    print("  结果:", r)
    print("  请求路径:", HITS)
    assert r["usable"] is True, "必须能回退到 /v1 并成功（修复前这里是 False）"
    assert any(h.endswith("/v1/chat/completions") for h in HITS)
    # 首个候选被 404 后应继续试下一个
    assert HITS[0].endswith("/coding/chat/completions") and len(HITS) >= 2
    srv.shutdown()
    print("  ✅ 404 自动回退到 /v1 成功")

    print("\n✅ chat 端点候选路径回归全通过")


if __name__ == "__main__":
    main()