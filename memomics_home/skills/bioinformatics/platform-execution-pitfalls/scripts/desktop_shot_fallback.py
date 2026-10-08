#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""桌面截图 → 落盘 → 推微信【降级通路】—— 不依赖 cua-driver / lazy_deps 门禁。

为什么需要它
------------
`scripts/desktop_shot.py` 走 cua-driver 后端，前置要过 `hermes-agent/tools/lazy_deps.py`
的 `LAZY_DEPS["tool.computer_use"] = ("mcp==1.26.0", "starlette==1.0.1")` **精确钉版**检查。
在裸 `python`（系统 Python312，starlette 0.52.1）下会在**截图阶段**就抛
`FeatureUnavailable(... "install reported success but packages still not importable")`，
退出码 3、磁盘零产物 —— 连发送那一步都到不了。

本脚本用 `PIL.ImageGrab` 直接抓屏（不碰 cua-driver），再 POST 到 MemOmics 本地服务的
`/api/weixin/send_image`，把「截图 → 发微信」这条链补完。

优先顺序（重要）
----------------
1. **首选**：先按 SKILL.md / `references/desktop-shot-and-wechat-pipeline.md` 的坑一，
   用 `项目根/.venv/Scripts/python.exe scripts/desktop_shot.py` 跑官方脚本 —— 它是正路。
2. **本脚本是 fallback**：官方脚本这条路在当前机器上不可用时才用（或只想快速把图送到微信时）。

用法
----
    python desktop_shot_fallback.py                      # 抓屏 + 推送，默认说明文字
    python desktop_shot_fallback.py --caption "换个说明"
    python desktop_shot_fallback.py --no-wechat          # 只截图，不推送
    python desktop_shot_fallback.py --status             # 只查微信适配器在线状态
    python desktop_shot_fallback.py --retries 3          # 有界重试（默认 3 次）

退出码：0 成功 / 4 微信未送达 / 5 适配器未连接 / 3 截图失败

为什么要重试（2026-09-25 实测）
------------------------------
服务端 `/api/weixin/send_image` 调 `_gate_weixin_send(reserve=True)` —— 它**预占时间槽**
（`_WEIXIN_SEND_GATE["last_ok_ts"] = now`）。而 server 自身的 agent 进度推送也在高频调用
同一把 gate（`min_interval=2.0`），因此**一次性的发图请求可能被静默丢弃**（只累加
`dropped` 计数，连日志都不打）。回执文案「发送失败或被限流（5 秒间隔 / 60 秒去重）」
把「限流」与「真失败」**合并成同一句**，无法据此定性。
⇒ 处置：**换一个全新的图片路径重试**（去重 key 就是图片路径本身），实测重试即成功。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

WEBUI_URL = os.environ.get("MEMOMICS_WEBUI_URL", "http://127.0.0.1:8899")


def out_dir() -> str:
    """截图落地目录：环境变量 > 当前工作目录下的 results/desktop_shots。"""
    d = os.environ.get("MEMOMICS_DESKTOP_SHOT_DIR")
    if d:
        return d
    return os.path.join(os.getcwd(), "results", "desktop_shots")


def grab(out_path: str) -> dict:
    """PIL.ImageGrab 抓全屏（all_screens=True 覆盖多显示器）并落盘。"""
    from PIL import ImageGrab
    img = ImageGrab.grab(all_screens=True)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, "PNG")
    return {"path": os.path.abspath(out_path), "width": img.width, "height": img.height,
            "bytes": os.path.getsize(out_path)}


def _get(url: str, timeout: int = 10) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return {"status": r.status, "body": json.loads(r.read().decode("utf-8", "replace"))}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return {"status": e.code, "body": json.loads(raw)}
        except Exception:
            return {"status": e.code, "body": {"raw": raw}}
    except Exception as e:
        return {"status": None, "body": {"error": "连不上 MemOmics(%s): %s" % (url, e)}}


def wechat_status() -> dict:
    """微信适配器健康探针 —— 回答「适配器是不是活着」，把排障与文案解耦。

    实测回执：{"connected": true, "account_id": "…@im.wechat", "adapter_alive": true,
               "last_error": "", "agent_enabled": true, "msg_count": 8}
    """
    return _get(WEBUI_URL.rstrip("/") + "/api/weixin/status")


def send_to_wechat(image_path: str, caption: str = "") -> dict:
    """POST 本地图片到微信（复用服务端限流与适配器）。"""
    payload = json.dumps({"path": image_path, "caption": caption},
                         ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(WEBUI_URL.rstrip("/") + "/api/weixin/send_image",
                                 data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return {"status": r.status, "body": json.loads(r.read().decode("utf-8"))}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return {"status": e.code, "body": json.loads(raw)}
        except Exception:
            return {"status": e.code, "body": {"raw": raw}}
    except Exception as e:
        return {"status": None, "body": {"error": "连不上 MemOmics(%s): %s" % (WEBUI_URL, e)}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="桌面截图落盘 + 推微信（降级通路，不依赖 cua-driver）")
    ap.add_argument("--caption", default="MemOmics 桌面截图", help="微信图片说明")
    ap.add_argument("--out", default="", help="输出 PNG 路径（默认 results/desktop_shots/desktop_<时间戳>.png）")
    ap.add_argument("--no-wechat", action="store_true", help="只截图不推送")
    ap.add_argument("--status", action="store_true", help="只查微信适配器在线状态")
    ap.add_argument("--retries", type=int, default=3, help="发送重试次数（默认 3，每次换新路径）")
    ap.add_argument("--gap", type=float, default=8.0, help="重试间隔秒（默认 8）")
    a = ap.parse_args(argv)

    if a.status:
        st = wechat_status()
        print("GET %s/api/weixin/status -> HTTP %s" % (WEBUI_URL, st["status"]))
        print("回执: %s" % json.dumps(st["body"], ensure_ascii=False))
        ok = bool(st["body"].get("connected")) and bool(st["body"].get("adapter_alive"))
        print("微信可用: %s" % ("是" if ok else "否（看 last_error / connected）"))
        return 0 if ok else 5

    last = None
    for i in range(1, max(1, a.retries) + 1):
        # 每次换新路径：去重 key 是图片路径，复用同一路径会命中 60s dedup
        if a.out and i == 1:
            path = a.out
        else:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(out_dir(), "desktop_%s%s.png" % (ts, "" if i == 1 else "_r%d" % i))
        try:
            info = grab(path)
        except Exception as e:
            print("截图失败：%r" % (e,), file=sys.stderr)
            return 3
        print("[%d] 截图落盘 OK: %s (%dx%d, %d 字节)"
              % (i, info["path"], info["width"], info["height"], info["bytes"]))
        if a.no_wechat:
            return 0

        res = send_to_wechat(info["path"], a.caption)
        print("[%d] POST %s/api/weixin/send_image -> HTTP %s | %s"
              % (i, WEBUI_URL, res["status"], json.dumps(res["body"], ensure_ascii=False)))
        last = res
        if res["body"].get("ok"):
            print("[%d] 微信已接收 ✅" % i)
            return 0
        if i < a.retries:
            time.sleep(a.gap)

    # 全部重试失败 → 用 status 探针把「适配器问题」与「发送问题」分开报，别只回一句"限流"
    st = wechat_status()
    print("重试 %d 次均未送达。最后回执: %s" % (a.retries, json.dumps((last or {}).get("body", {}), ensure_ascii=False)))
    print("适配器状态: %s" % json.dumps(st["body"], ensure_ascii=False))
    return 4


if __name__ == "__main__":
    sys.exit(main())