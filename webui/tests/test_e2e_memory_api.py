# -*- coding: utf-8 -*-
"""P1-12(2026-08-13): 真实 server e2e 测试 — memory API 鉴权/限额链路。

用法（在 E:/MemOmics-Agent 下运行）:
    MEMOMICS_PORT=8897 python webui/tests/test_e2e_memory_api.py

启动一个独立端口的真实 server 实例（uvicorn 子进程），验证:
  1. GET /api/memory 下发 api_token
  2. 无/错 token 写 → 401
  3. 对 token 写 → 200（e2e-test.md，测后清理）
  4. 超限写（12000 字符）→ 413
  5. 无 token 删 → 401；对 token 删 → 200

不干扰 8899 生产实例（独立端口 + 独立 state 访问只读）。
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = int(os.environ.get("MEMOMICS_PORT", "8897"))
BASE = f"http://127.0.0.1:{PORT}"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERVER_PY = os.path.join(ROOT, "webui", "server.py")

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)


def req(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Memory-Token"] = token
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def main():
    # 1. 启动独立端口 server（若该端口已有实例则直接复用）
    proc = None
    try:
        urllib.request.urlopen(BASE + "/api/memory", timeout=3)
        print(f"端口 {PORT} 已有 server 实例，直接复用")
    except Exception:
        env = dict(os.environ)
        env["MEMOMICS_PORT"] = str(PORT)
        log = open(os.path.join(ROOT, "e2e_server.log"), "wb")
        proc = subprocess.Popen(
            [sys.executable, SERVER_PY], cwd=ROOT, env=env,
            stdout=log, stderr=subprocess.STDOUT)
        print(f"启动临时 server pid={proc.pid} (port {PORT})...")
        for _ in range(60):
            try:
                urllib.request.urlopen(BASE + "/api/memory", timeout=3)
                break
            except Exception:
                time.sleep(1)
        else:
            check("server 启动", False, "60s 未就绪")
            if proc:
                proc.terminate()
            sys.exit(1)
        check("server 启动", True)

    try:
        # 2. GET 下发 token
        s, body = req("GET", "/api/memory")
        d = json.loads(body)
        token = d.get("api_token", "")
        check("GET /api/memory 下发 api_token", s == 200 and len(token) >= 16, f"s={s}")

        # 3. 无 token 写 → 401
        s, _ = req("POST", "/api/memory/write", {"target": "e2e-test.md", "content": "x"})
        check("无 token 写 → 401", s == 401, f"s={s}")

        # 4. 错 token 写 → 401
        s, _ = req("POST", "/api/memory/write", {"target": "e2e-test.md", "content": "x"},
                   token="bad" * 10)
        check("错 token 写 → 401", s == 401, f"s={s}")

        # 5. 对 token 写 → 200
        s, body = req("POST", "/api/memory/write",
                      {"target": "e2e-test.md", "content": "e2e test entry"}, token=token)
        check("对 token 写 → 200", s == 200, f"s={s} {body[:100]}")

        # 6. 超限写 → 413
        s, body = req("POST", "/api/memory/write",
                      {"target": "e2e-test.md", "content": "x" * 12000}, token=token)
        check("超限写 → 413", s == 413, f"s={s} {body[:100]}")

        # 7. 无 token 删 → 401
        s, _ = req("DELETE", "/api/memory/e2e-test.md")
        check("无 token 删 → 401", s == 401, f"s={s}")

        # 8. 对 token 删 → 200（清理）
        s, body = req("DELETE", "/api/memory/e2e-test.md", token=token)
        check("对 token 删（清理）→ 200", s == 200, f"s={s} {body[:100]}")
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
            print("临时 server 已关停")

    print()
    if FAILED:
        print(f"❌ {len(FAILED)} 项失败: {FAILED}")
        sys.exit(1)
    print("✅ P1-12 e2e 全部通过")


if __name__ == "__main__":
    main()
