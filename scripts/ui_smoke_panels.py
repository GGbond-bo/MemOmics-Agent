# -*- coding: utf-8 -*-
"""批L UI 冒烟：各面板切换 + 文献/知识库/图谱视图。"""
import json
import subprocess
import time
import urllib.request
import tempfile

import websocket

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def main():
    udd = tempfile.mkdtemp(prefix="memomics_l_")
    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--remote-debugging-port=9335",
         "--remote-allow-origins=*", "--user-data-dir={0}".format(udd),
         "--no-first-run", "--disable-gpu", "http://127.0.0.1:8899/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                json.loads(urllib.request.urlopen("http://127.0.0.1:9335/json/version", timeout=3).read())
                break
            except Exception:
                time.sleep(0.5)
        targets = json.loads(urllib.request.urlopen("http://127.0.0.1:9335/json/list", timeout=5).read())
        page = next((t for t in targets if t.get("type") == "page" and "8899" in t.get("url", "")), None)
        assert page
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

        time.sleep(4)
        checks = []
        js("switchView('kb'); switchKbView('graph')")
        time.sleep(2)
        checks.append(("图谱视图显示", js("document.getElementById('kb-graph').style.display") != "none"))
        checks.append(("图谱按钮高亮", js("document.getElementById('kb-btn-graph').style.background") == "var(--primary)"))
        js("toggleScienceSearch()")
        time.sleep(1)
        checks.append(("文献视图显示", js("document.getElementById('kb-science').style.display") == "flex"))
        checks.append(("图谱被隐藏", js("document.getElementById('kb-graph').style.display") == "none"))
        checks.append(("文献按钮高亮", js("document.getElementById('kb-btn-sci').style.background") == "var(--primary)"))
        js("toggleKbMatrix()")
        time.sleep(2)
        checks.append(("矩阵显示且文献隐藏", js("document.getElementById('kb-matrix').style.display") == "" and js("document.getElementById('kb-science').style.display") == "none"))
        checks.append(("矩阵按钮高亮", js("document.getElementById('kb-btn-matrix').style.background") == "var(--primary)"))
        js("switchKbView('browse')")
        time.sleep(1)
        checks.append(("回到浏览", js("document.getElementById('kb-list').style.display") == ""))
        js("toggleScienceSearch(); loadLiteratureLibrary()")
        time.sleep(3)
        checks.append(("文献库表格渲染", (js("document.querySelectorAll('#lit-library table tbody tr').length") or 0) > 0))
        checks.append(("绑定提示存在", js("document.getElementById('lit-binding-chip') !== null")))
        js("viewSummary('10.1016_j.freeradbiomed.2024.07.026.pdf')")
        time.sleep(2)
        checks.append(("摘要弹窗显示", js("document.getElementById('lit-summary-modal').style.display") == "flex"))
        js("document.getElementById('lit-summary-modal').style.display='none'")
        for v, el in [("memory", "panel-memory"), ("skills", "panel-skills"), ("results", "panel-results"), ("chat", "panel-info")]:
            js("switchView('{0}')".format(v))
            time.sleep(1.2)
            checks.append(("面板 {0} 显示".format(v), js("document.getElementById('{0}').style.display".format(el)) == ""))
        js("refreshRuntimePanel()")
        time.sleep(2)
        checks.append(("运行健康面板有数据", js("document.getElementById('runtime-panel').innerHTML.indexOf('\u4e2a') >= 0")))
        fails = [c[0] for c in checks if not c[1]]
        for label, ok in checks:
            print(("PASS" if ok else "FAIL"), "|", label)
        print("RESULT:", "ALL PASS" if not fails else "FAIL: {0}".format(fails))
        pws.close()
        return 0 if not fails else 1
    finally:
        proc.terminate()
        time.sleep(1)
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
