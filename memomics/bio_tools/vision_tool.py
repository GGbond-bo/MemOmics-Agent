# -*- coding: utf-8 -*-
"""vision_describe — MemOmics 视觉工具（2026-08-14）。

给纯文本模型（deepseek-v4-flash 等）装上眼睛：
- 首选通道: 用户已有的 opencode-go/kimi-k2.6（多模态，实测可用）
- 免费通道: OVHcloud 匿名 Qwen2.5-VL-72B（无 key，~2 req/min/IP）
- 可选通道: 智谱 glm-4.6v-flash（ZAI_API_KEY 存在时）

参考设计: dsh-vision-router（DeepSeek Harness 插件）的 vision_describe 工具。
"""
import base64
import json
import logging
import os
import urllib.request

logger = logging.getLogger("memomics.vision_tool")

_VISION_CANDIDATES = [
    # (provider, base_url, model, api_key_env_or_literal, needs_browser_ua)
    ("opencode-go", "https://opencode.ai/zen/go/v1", "kimi-k2.6", "__opencode_key__", True),
    ("ovh-free", "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1", "Qwen2.5-VL-72B-Instruct", "", True),
    ("zhipu", "https://open.bigmodel.cn/api/paas/v4", "glm-4.6v-flash", "__zai_key__", False),
]

_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _resolve_key(entry):
    """解析 api key: 字面量 / 环境变量 / provider_keys.json。"""
    src = entry
    if src == "__opencode_key__":
        try:
            hh = os.environ.get("HERMES_HOME", "")
            p = os.path.join(hh, "provider_keys.json")
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                return (d.get("opencode-go") or {}).get("api_key", "")
        except Exception:
            pass
        return ""
    if src == "__zai_key__":
        return os.environ.get("ZAI_API_KEY", "")
    return src


def _image_to_data_url(image_path: str) -> str:
    _ext = os.path.splitext(image_path)[1].lower().lstrip(".") or "png"
    if _ext == "jpg":
        _ext = "jpeg"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/{_ext};base64,{b64}"


def _fetch_image_url(url: str) -> str:
    """http(s) 图片下载到临时文件后返回本地路径（失败返回原 url）。"""
    try:
        if not url.lower().startswith(("http://", "https://")):
            return url
        import tempfile
        req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read(10 * 1024 * 1024)
        _ext = ".png"
        _ct = ""
        try:
            _ct = r.headers.get("content-type", "")
        except Exception:
            pass
        if "jpeg" in _ct or "jpg" in _ct:
            _ext = ".jpg"
        elif "webp" in _ct:
            _ext = ".webp"
        fd, tmp = tempfile.mkstemp(suffix=_ext)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return tmp
    except Exception:
        return url


def vision_describe(image_path: str = "", question: str = "描述这张图片的内容",
                    max_tokens: int = 800) -> str:
    """用视觉模型回答关于图片的问题（自动选择可用通道）。"""
    if not image_path:
        return json.dumps({"ok": False, "error": "image_path 必填（本地路径或 http(s) URL）"}, ensure_ascii=False)
    question = (question or "描述这张图片的内容").strip()
    local = _fetch_image_url(image_path)
    if not os.path.isfile(local):
        return json.dumps({"ok": False, "error": f"图片不存在或下载失败: {image_path}"}, ensure_ascii=False)
    try:
        data_url = _image_to_data_url(local)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"读取图片失败: {e}"}, ensure_ascii=False)
    finally:
        if local != image_path:
            try:
                os.remove(local)
            except Exception:
                pass

    errors = []
    for provider, base, model, key_src, ua in _VISION_CANDIDATES:
        key = _resolve_key(key_src)
        if not key and key_src:
            errors.append(f"{provider}: 无 API key")
            continue
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
            "max_tokens": max_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        if ua:
            headers["User-Agent"] = _BROWSER_UA
        req = urllib.request.Request(
            base.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read().decode("utf-8"))
            ans = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if ans and ans.strip():
                return json.dumps({
                    "ok": True, "provider": provider, "model": model,
                    "answer": ans.strip()[:6000],
                    "usage": d.get("usage"),
                }, ensure_ascii=False)
            errors.append(f"{provider}/{model}: 空回复")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            errors.append(f"{provider}/{model}: HTTP {e.code} {body}")
        except Exception as e:
            errors.append(f"{provider}/{model}: {e}")

    return json.dumps({
        "ok": False,
        "error": "所有视觉通道均失败",
        "detail": errors[:6],
        "hint": "可设置 ZAI_API_KEY 增加智谱免费通道；或检查 opencode-go key 是否有效",
    }, ensure_ascii=False)


SCHEMA = {
    "name": "vision_describe",
    "description": (
        "用视觉模型看图回答（当前模型是纯文本模型时的'眼睛'）。"
        "用户发送图片、需要读图（图表/截图/显微镜图/示意图/手绘图）、"
        "核对图片内容时必须调用本工具，禁止凭空猜测图片内容。"
        "image_path 支持本地绝对路径或 http(s) URL。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "image_path": {"type": "string", "description": "图片本地路径或 URL"},
            "question": {"type": "string", "description": "要问的问题（如：图里有什么？x 轴标签是什么？哪个样本异常？）"},
            "max_tokens": {"type": "integer", "default": 800, "description": "回答最大 token 数"},
        },
        "required": ["image_path"],
    },
}


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="vision_describe",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: vision_describe(
                args.get("image_path", ""),
                args.get("question", "描述这张图片的内容"),
                args.get("max_tokens", 800),
            ),
            emoji="👁️",
            max_result_size_chars=8_000,
        )
    except Exception as e:
        logger.warning(f"vision_describe register failed: {e}")


_register()
