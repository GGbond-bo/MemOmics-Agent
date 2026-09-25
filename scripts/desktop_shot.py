#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""桌面截图落盘（computer_use 的「最后一公里」）。

为什么要这个脚本：
  computer_use(action="capture") 返回的 PNG 只进**模型上下文**（Hermes 把 base64 拼进
  tool_result 的图片块），不落盘；而 MemOmics 的「新图片自动推微信」只认磁盘上的图片文件。
  于是「截图 → 发微信」中间缺一环。这个脚本补的就是那一环：用**同一个 cua-driver 后端**
  截图并写文件，写出来的图既能在 WebUI 当产物看，也能被微信推送链路捡走。

用法：
    python scripts/desktop_shot.py                     # 整屏 → results/desktop_shots/desktop_<时间戳>.png
    python scripts/desktop_shot.py --out D:/shot.png     # 指定输出路径（正斜杠在 Windows 也认）
    python scripts/desktop_shot.py --app Edge          # 截指定应用/窗口（默认 screen=整个桌面）
    python scripts/desktop_shot.py --send-wechat       # 存好后立刻推到微信
    python scripts/desktop_shot.py --json              # 机器可读输出

退出码：0 成功 / 2 驱动缺失 / 3 截图失败 / 4 微信发送失败
"""
from __future__ import annotations

import argparse
import base64
import datetime
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SUBDIR = os.path.join("results", "desktop_shots")
WEBUI_URL = os.environ.get("MEMOMICS_WEBUI_URL", "http://127.0.0.1:8899")


def _ensure_import_path() -> None:
    """把仓库根 + hermes-agent 放进 sys.path（agent 的 terminal 里未必设了 PYTHONPATH）。"""
    for p in (REPO_ROOT, os.path.join(REPO_ROOT, "hermes-agent")):
        if p not in sys.path:
            sys.path.insert(0, p)


def default_out_path(now=None) -> str:
    ts = (now or datetime.datetime.now()).strftime("%Y%m%d_%H%M%S")
    return os.path.join(REPO_ROOT, DEFAULT_SUBDIR, "desktop_%s.png" % ts)


def _backend():
    """构造真实后端（可被测试替换）。"""
    _ensure_import_path()
    from webui import cua_bootstrap
    cua_bootstrap.ensure_cua_driver_env(log=lambda m: print(m, file=sys.stderr, flush=True))
    from tools.computer_use.cua_backend import CuaDriverBackend  # type: ignore
    return CuaDriverBackend()


def capture_desktop(out_path: str, app: str = "screen", mode: str = "vision", backend=None) -> dict:
    """截一张图写到 out_path，返回 {path,width,height,bytes,app}。backend 可注入（测试用）。"""
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    be = backend if backend is not None else _backend()
    started = False
    try:
        if hasattr(be, "start"):
            be.start()
            started = True
        cap = be.capture(mode=mode, app=app)
        b64 = getattr(cap, "png_b64", None)
        if not b64:
            raise RuntimeError("后端没有返回 PNG（app=%r 可能命中了不发布画面的覆盖层）" % app)
        data = base64.b64decode(b64)
        if not data:
            raise RuntimeError("截图数据为空")
        with open(out_path, "wb") as f:
            f.write(data)
        return {"path": out_path, "width": getattr(cap, "width", 0), "height": getattr(cap, "height", 0),
                "bytes": len(data), "app": app, "elements": len(getattr(cap, "elements", None) or [])}
    finally:
        if started and hasattr(be, "stop"):
            try:
                be.stop()
            except Exception:
                pass


def send_to_wechat(image_path: str, caption: str = "", url: str = None) -> dict:
    """把图片推给微信（走 8899 的 /api/weixin/send_image，复用服务端限流与适配器）。"""
    import urllib.error
    import urllib.request
    payload = json.dumps({"path": image_path, "caption": caption}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request((url or WEBUI_URL).rstrip("/") + "/api/weixin/send_image",
                                 data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error": "HTTP %s" % e.code}
    except Exception as e:
        return {"ok": False, "error": "连不上 MemOmics(%s): %s" % (url or WEBUI_URL, e)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="桌面截图并落盘（可选推微信）")
    ap.add_argument("--out", default="", help="输出 PNG 路径（默认 results/desktop_shots/desktop_<时间戳>.png）")
    ap.add_argument("--app", default="screen", help="目标：screen=整个桌面（默认），也可给应用名/pid/window_id")
    ap.add_argument("--mode", default="vision", choices=["vision", "som", "ax"], help="capture 模式")
    ap.add_argument("--caption", default="", help="微信图片说明")
    ap.add_argument("--send-wechat", action="store_true", help="保存后立刻推送到微信")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    out = args.out or default_out_path()
    try:
        info = capture_desktop(out, app=args.app, mode=args.mode)
    except ImportError as e:
        print("驱动不可用：%s" % e, file=sys.stderr)
        print("当前解释器：%s" % sys.executable, file=sys.stderr)
        print("先装驱动：hermes computer-use install（装完重跑本脚本即可，webui/cua_bootstrap 会自动定位 cua-driver）",
              file=sys.stderr)
        return 2
    except Exception as e:
        msg = str(e)
        print("截图失败：%r" % (e,), file=sys.stderr)
        print("当前解释器：%s" % sys.executable, file=sys.stderr)
        if "unavailable" in msg or "not importable" in msg:
            # 2026-09-25 实测事故：agent 在某个 python 下跑本脚本，tools.computer_use 的依赖门禁
            # 抛 FeatureUnavailable（mcp/starlette 版本被钉死）。同一台机器换仓库 venv 或 miniconda
            # 都 exit=0，所以这类报错基本都是「python 解释器选错」而不是驱动坏了。
            print("这多半是「python 解释器选错」：请用仓库自带解释器重跑，例如", file=sys.stderr)
            print('  "%s" scripts/desktop_shot.py' % os.path.join(REPO_ROOT, ".venv", "Scripts", "python.exe"),
                  file=sys.stderr)
            print("或按报错提示补齐依赖（如 pip install 'mcp==1.26.0' 'starlette==1.0.1'）", file=sys.stderr)
        return 3

    result = {"ok": True, "shot": info, "wechat": None}
    if args.send_wechat:
        caption = args.caption or "🖼️ 桌面截图"
        wx = send_to_wechat(info["path"], caption)
        result["wechat"] = wx
        if not wx.get("ok"):
            result["ok"] = False
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print("已保存: %s (%dx%d, %d 字节)" % (info["path"], info["width"], info["height"], info["bytes"]))
        if result["wechat"] is not None:
            print("微信: %s" % ("已发送" if result["wechat"].get("ok") else "发送失败 - %s" % result["wechat"].get("error")))
    return 0 if result["ok"] else 4


if __name__ == "__main__":
    sys.exit(main())
