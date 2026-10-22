# -*- coding: utf-8 -*-
"""离线验证：探针函数对本地假上游的行为（全假，不打真网络）。"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, r"E:\MemOmics-Agent")

from memomics.coding_plans import probe_chat_model  # noqa: E402

HITS = []


class FakeUpstream(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静音
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8")
        HITS.append({"path": self.path, "headers": dict(self.headers), "body": json.loads(raw)})
        model = json.loads(raw).get("model")
        if model == "ok-model":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode())
        elif model == "proto-model":
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"type": "ModelProtocolUnsupported",
                                                   "message": "Model does not support this protocol."}}).encode())
        elif model == "auth-model":
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "Invalid or incorrect API key"}}).encode())
        elif model == "down-model":
            self.send_response(402)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "Upstream request failed: Endpoint is unavailable."}}).encode())
        else:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")


srv = HTTPServer(("127.0.0.1", 0), FakeUpstream)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

provider = {"api": f"http://127.0.0.1:{port}/v1",
            "extra_headers": {"x-opencode-session": "sess-123"}}

print("=== 1) 可用模型 ===")
r = probe_chat_model(provider, "sk-test-key-123456", "ok-model", timeout=10)
print(" ", r)
assert r["usable"] is True and r["status"] == 200, r

print("=== 2) 协议不支持 ===")
r = probe_chat_model(provider, "sk-test-key-123456", "proto-model", timeout=10)
print(" ", r)
assert r["usable"] is False and "协议" in r["error"], r

print("=== 3) key 无效 ===")
r = probe_chat_model(provider, "sk-test-key-123456", "auth-model", timeout=10)
print(" ", r)
assert r["usable"] is False and "401" in r["error"], r

print("=== 4) 端点停用（402）===")
r = probe_chat_model(provider, "sk-test-key-123456", "down-model", timeout=10)
print(" ", r)
assert r["usable"] is False and ("不可用" in r["error"] or "402" in r["error"]), r

print("=== 5) 连不上（端口关掉）===")
srv.shutdown()
r = probe_chat_model(provider, "sk-test-key-123456", "ok-model", timeout=5)
print(" ", r)
assert r["usable"] is False and r["status"] == 0, r

print("\n=== 6) 请求形态检查（第一条 200 的请求）===")
hit = next(h for h in HITS if h["path"].endswith("/chat/completions"))
# 注意：HTTP 头大小写不敏感（服务端第一跳可能把首字母大写），比较要归一化
ci = {k.lower(): v for k, v in hit["headers"].items()}
print("  path:", hit["path"])
print("  Authorization:", ci.get("authorization"))
print("  x-opencode-session:", ci.get("x-opencode-session"))
print("  payload:", json.dumps(hit["body"], ensure_ascii=False))
assert ci.get("authorization") == "Bearer sk-test-key-123456"
assert ci.get("x-opencode-session") == "sess-123", "extra_headers 没带上！"
assert hit["body"]["max_tokens"] == 1 and hit["body"]["stream"] is False
assert hit["body"]["messages"][0]["content"] == "hi"

print("\n✅ 探针离线自测全通过")

# ── 回归钉（2026-10-22）：两条模型下发路径必须口径一致 ─────────────────────
# provider 级清单（/api/providers/{pid}/models）与快速切换列表
# （/api/models/available：会话下拉 + 设置里「已连接的模型」）都要按检测结论过滤。
def test_available_models_filters_probed_failures():
    import io as _io
    src = _io.open(r"E:/MemOmics-Agent/webui/server.py", encoding="utf-8").read()
    for fn in ("async def list_available_models", "async def get_provider_models"):
        i = src.index(fn)
        seg = src[i:i + 3500]
        assert "usable" in seg, f"{fn} 没有按检测结论过滤 —— 不可用的模型会重新出现"
    # list_available_models 必须真的跳过（不是只读字段）
    i = src.index("async def list_available_models")
    seg = src[i:i + 3500]
    assert "_probe_rows" in seg and "_has_pulled" in seg and "continue" in seg, (
        "list_available_models 未按检测结论跳过不可用模型")
    print("✅ 两条下发路径都按检测结论过滤")
