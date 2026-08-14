# -*- coding: utf-8 -*-
"""批D UI 冒烟：headless Edge 打开 WebUI，验证新元素 + 触发文献检索 + 运行健康面板。"""
import json
import subprocess
import time
import urllib.request
import tempfile
import os

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def main():
    udd = tempfile.mkdtemp(prefix="memomics_d_")
    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--remote-debugging-port=9333",
         "--remote-allow-origins=*", f"--user-data-dir={udd}",
         "--no-first-run", "--disable-gpu", "http://127.0.0.1:8899/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # 等 CDP 就绪
        ws_url = ""
        for _ in range(60):
            try:
                v = json.loads(urllib.request.urlopen("http://127.0.0.1:9333/json/version", timeout=3).read())
                ws_url = v["webSocketDebuggerUrl"]
                break
            except Exception:
                time.sleep(0.5)
        assert ws_url, "CDP 未就绪"
        ws = websocket.create_connection(ws_url, timeout=30)
        msg_id = [0]

        def cdp(method, params=None):
            msg_id[0] += 1
            ws.send(json.dumps({"id": msg_id[0], "method": method, "params": params or {}}))
            while True:
                m = json.loads(ws.recv())
                if m.get("id") == msg_id[0]:
                    return m

        # 等页面加载完成
        time.sleep(4)
        # 找到页面 target
        targets = json.loads(urllib.request.urlopen("http://127.0.0.1:9333/json/list", timeout=5).read())
        page = next((t for t in targets if t.get("type") == "page" and "8899" in t.get("url", "")), None)
        assert page, "页面 target 未找到"
        pws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
        pid = [0]

        def pcdp(method, params=None):
            pid[0] += 1
            pws.send(json.dumps({"id": pid[0], "method": method, "params": params or {}}))
            while True:
                m = json.loads(pws.recv())
                if m.get("id") == pid[0]:
                    return m

        def js(expr):
            r = pcdp("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
            return r.get("result", {}).get("result", {}).get("value")

        # 1. 新元素存在
        for expr, label in [
            ("!!document.getElementById('kb-science')", "kb-science div"),
            ("!!document.getElementById('science-results')", "science-results div"),
            ("!!document.getElementById('runtime-panel')", "runtime-panel div"),
            ("typeof doScienceSearch === 'function'", "doScienceSearch fn"),
            ("typeof governMemory === 'function'", "governMemory fn"),
            ("typeof deleteProviderKey === 'function'", "deleteProviderKey fn"),
            ("typeof refreshRuntimePanel === 'function'", "refreshRuntimePanel fn"),
        ]:
            print(label, "->", "OK" if js(expr) else "MISSING")
        # 2. 运行健康面板渲染
        js("refreshRuntimePanel()")
        time.sleep(2.5)
        html = js("document.getElementById('runtime-panel').innerHTML")
        print("runtime-panel html:", str(html)[:150])
        # 3. 文献检索触发（openalex 快）
        js("document.getElementById('science-q').value='aging muscle single cell'; document.getElementById('science-source').value='openalex'; doScienceSearch()")
        time.sleep(6)
        n = js("document.querySelectorAll('#science-results a').length")
        print("science results links:", n)
        # 4. 信息面板真实计数
        js("refreshInfoPanel()")
        time.sleep(3)
        print("kb count badge:", js("document.getElementById('info-kb-count').textContent"),
              "| skills badge:", js("document.getElementById('info-skill-count').textContent"))
        ok = (n or 0) > 0
        print("RESULT:", "PASS" if ok else "FAIL")
        pws.close()
        ws.close()
        return 0 if ok else 1
    finally:
        proc.terminate()
        time.sleep(1)
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
