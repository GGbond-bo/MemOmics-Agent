"""Alibaba DashScope image generation backend (qwen-image / wan 万相).

Uses DashScope's native async multimodal-generation protocol:

* create task: ``POST https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation``
  with header ``X-DashScope-Async: enable``
* poll task:   ``GET https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}``

Configure in ``config.yaml``::

    image_gen:
      provider: dashscope
      dashscope:
        api_key: sk-...
        model: qwen-image-3.0        # qwen-image-3.0 / wan2.7-image / ...
        size: "1024*1024"            # DashScope 格式，星号分隔
        landscape_size: "1280*720"
        portrait_size: "720*1280"
        n: 1
        watermark: false             # 透传给 parameters.watermark

Environment fallback: ``DASHSCOPE_API_KEY``.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    normalize_reference_images,
    resolve_aspect_ratio,
    save_b64_image,
    save_url_image,
    success_response,
)

logger = logging.getLogger(__name__)

PROVIDER = "dashscope"
DISPLAY_NAME = "阿里云 DashScope（千问 qwen-image / 万相 wan）"

_BASE = "https://dashscope.aliyuncs.com"
_CREATE_URL = f"{_BASE}/api/v1/services/aigc/multimodal-generation/generation"
_TASK_URL = f"{_BASE}/api/v1/tasks/{{task_id}}"

_POLL_INTERVAL = 1.0
_POLL_TIMEOUT = 180.0


def _load_config() -> Dict[str, Any]:
    """Read ``image_gen.dashscope`` from config.yaml, overlaid by the standalone
    ``<HERMES_HOME>/image_gen_config.json`` (WebUI settings page, higher precedence)."""
    merged: Dict[str, Any] = {}
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else {}
        if isinstance(section, dict):
            sub = section.get("dashscope")
            if isinstance(sub, dict):
                merged.update(sub)
    except Exception as exc:
        logger.debug("Could not load image_gen.dashscope config: %s", exc)
    try:
        import json

        home = os.environ.get("HERMES_HOME", "")
        path = os.path.join(home, "image_gen_config.json") if home else "hermes_home/image_gen_config.json"
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            sub = data.get("dashscope")
            if isinstance(sub, dict):
                merged.update(sub)
    except Exception as exc:
        logger.debug("Could not load image_gen_config.json: %s", exc)
    return merged


def _resolve_key() -> str:
    cfg = _load_config()
    key = str(cfg.get("api_key", "") or "").strip()
    if not key:
        key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    return key


def _load_image_ref(ref: str) -> str:
    """Normalize a reference image to a data URL DashScope accepts."""
    ref = ref.strip()
    lower = ref.lower()
    if lower.startswith(("http://", "https://", "data:")):
        return ref
    from agent.file_safety import raise_if_read_blocked

    raise_if_read_blocked(ref)
    import base64
    import mimetypes

    with open(ref, "rb") as fh:
        data = fh.read()
    mime = mimetypes.guess_type(ref)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


class DashScopeImageGenProvider(ImageGenProvider):
    """Alibaba DashScope native async image generation backend."""

    @property
    def name(self) -> str:
        return PROVIDER

    @property
    def display_name(self) -> str:
        return DISPLAY_NAME

    def is_available(self) -> bool:
        return bool(_resolve_key())

    def list_models(self) -> List[Dict[str, Any]]:
        cfg = _load_config()
        model = str(cfg.get("model", "") or "").strip()
        if not model:
            return []
        return [
            {
                "id": model,
                "display": model,
                "strengths": "DashScope 原生协议（config: image_gen.dashscope.model）",
                "price": "per provider",
            }
        ]

    def default_model(self) -> Optional[str]:
        cfg = _load_config()
        model = str(cfg.get("model", "") or "").strip()
        return model or None

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": DISPLAY_NAME,
            "badge": "config",
            "tag": "千问 qwen-image / 万相 wan — 在 config.yaml 的 image_gen.dashscope 配置",
            "env_vars": [
                {"key": "DASHSCOPE_API_KEY", "prompt": "DashScope API key", "url": "https://dashscope.aliyuncs.com"},
            ],
        }

    def capabilities(self) -> Dict[str, Any]:
        return {
            "modalities": ["text", "image"],
            "max_reference_images": 4,
        }

    def _submit(self, model: str, prompt: str, size: str, n: int, sources: List[str], watermark: bool) -> str:
        api_key = _resolve_key()
        content: List[Dict[str, Any]] = [{"text": prompt}]
        for ref in sources:
            content.append({"image": _load_image_ref(ref)})
        body = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {"size": size, "n": n},
        }
        if watermark:
            body["parameters"]["watermark"] = True
        resp = requests.post(
            _CREATE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable",
            },
            json=body,
            timeout=120,
        )
        resp.raise_for_status()
        payload = resp.json()
        task_id = (payload.get("output") or {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"DashScope 未返回 task_id: {payload}")
        return task_id

    def _poll(self, task_id: str) -> List[str]:
        api_key = _resolve_key()
        deadline = time.monotonic() + _POLL_TIMEOUT
        while time.monotonic() < deadline:
            resp = requests.get(
                _TASK_URL.format(task_id=task_id),
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
            output = payload.get("output") or {}
            status = (output.get("task_status") or "").upper()
            if status == "SUCCEEDED":
                urls = [r.get("url") for r in (output.get("results") or []) if r.get("url")]
                if not urls:
                    raise RuntimeError(f"DashScope 任务成功但无结果 URL: {payload}")
                return urls
            if status in ("FAILED", "CANCELED", "UNKNOWN"):
                msg = output.get("message") or output.get("code") or status
                raise RuntimeError(f"DashScope 任务失败: {msg}")
            time.sleep(_POLL_INTERVAL)
        raise RuntimeError(f"DashScope 任务轮询超时（{int(_POLL_TIMEOUT)}s）")

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        *,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        aspect = resolve_aspect_ratio(aspect_ratio)

        if not prompt:
            return error_response(
                error="Prompt is required and must be a non-empty string",
                error_type="invalid_argument",
                provider=PROVIDER,
                aspect_ratio=aspect,
            )

        api_key = _resolve_key()
        if not api_key:
            return error_response(
                error="dashscope 未配置：config.yaml → image_gen.dashscope.api_key 或环境变量 DASHSCOPE_API_KEY",
                error_type="auth_required",
                provider=PROVIDER,
                aspect_ratio=aspect,
            )

        cfg = _load_config()
        model = str(cfg.get("model", "") or "").strip()
        if not model:
            return error_response(
                error="dashscope 未配置 model（config.yaml → image_gen.dashscope.model，如 qwen-image-3.0）",
                error_type="invalid_argument",
                provider=PROVIDER,
                aspect_ratio=aspect,
            )

        n = int(cfg.get("n", 1) or 1)
        watermark = bool(cfg.get("watermark", False))
        size = str(cfg.get("size", "1024*1024") or "1024*1024")
        if aspect == "landscape":
            size = str(cfg.get("landscape_size", size) or size)
        elif aspect == "portrait":
            size = str(cfg.get("portrait_size", size) or size)

        sources: List[str] = []
        if isinstance(image_url, str) and image_url.strip():
            sources.append(image_url.strip())
        for ref in (normalize_reference_images(reference_image_urls) or []):
            sources.append(ref)
        sources = sources[:4]
        modality = "image" if sources else "text"

        try:
            task_id = self._submit(model, prompt, size, n, sources, watermark)
            urls = self._poll(task_id)
        except Exception as exc:
            logger.debug("DashScope image generation failed", exc_info=True)
            return error_response(
                error=f"图像生成失败: {exc}",
                error_type="api_error",
                provider=PROVIDER,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        saved: List[str] = []
        for i, url in enumerate(urls):
            try:
                saved.append(str(save_url_image(url, prefix=f"image{'_edit' if modality == 'image' else ''}")))
            except Exception as exc:
                logger.warning("Could not persist DashScope image: %s", exc)
                saved.append(url)

        if not saved:
            return error_response(
                error="图像生成成功但无法保存返回图片",
                error_type="api_error",
                provider=PROVIDER,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        extra: Dict[str, Any] = {"size": size, "count": len(saved)}
        if len(saved) > 1:
            extra["images"] = saved[1:]
        return success_response(
            image=saved[0],
            model=model,
            prompt=prompt,
            aspect_ratio=aspect,
            provider=PROVIDER,
            modality=modality,
            extra=extra,
        )


def register(ctx) -> None:
    ctx.register_image_gen_provider(DashScopeImageGenProvider())
