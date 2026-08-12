"""OpenAI-images-compatible image generation backend (bring-your-own endpoint).

Covers any provider exposing the OpenAI ``images/generations`` (and
``images/edits``) REST protocol on a custom ``base_url`` — e.g.

* Volcengine Ark / 豆包 Seedream: ``https://ark.cn-beijing.volces.com/api/v3``
* Zhipu AI (智谱):                ``https://open.bigmodel.cn/api/paas/v4``
* OpenAI official:                ``https://api.openai.com/v1``
* any OpenAI-compatible gateway

Configure in ``config.yaml``::

    image_gen:
      provider: openai-compatible
      openai_compatible:
        base_url: https://ark.cn-beijing.volces.com/api/v3
        api_key: sk-...
        model: doubao-seedream-5-0-260628
        size: "1024x1024"   # square default ("1K"/"2K" for Volcengine, ...)
        landscape_size: "2K"   # optional aspect overrides
        portrait_size: "2K"
        n: 1                   # images per call (extras returned in response.extra)
        edits: true            # allow image edit via images/edits when refs given
        max_reference_images: 4

Environment fallbacks (lower precedence than config): ``OPENAI_COMPATIBLE_BASE_URL``,
``OPENAI_COMPATIBLE_API_KEY``, ``OPENAI_COMPATIBLE_MODEL``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

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

PROVIDER = "openai-compatible"
DISPLAY_NAME = "OpenAI 兼容（火山/智谱/自定义端点）"


def _load_config() -> Dict[str, Any]:
    """Read ``image_gen.openai_compatible`` from config.yaml, overlaid by the
    standalone ``<HERMES_HOME>/image_gen_config.json`` (written by the WebUI
    settings page, higher precedence)."""
    merged: Dict[str, Any] = {}
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else {}
        if isinstance(section, dict):
            sub = section.get("openai_compatible")
            if isinstance(sub, dict):
                merged.update(sub)
    except Exception as exc:
        logger.debug("Could not load image_gen.openai_compatible config: %s", exc)
    try:
        import json

        home = os.environ.get("HERMES_HOME", "")
        path = os.path.join(home, "image_gen_config.json") if home else "hermes_home/image_gen_config.json"
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            sub = data.get("openai_compatible")
            if isinstance(sub, dict):
                merged.update(sub)
    except Exception as exc:
        logger.debug("Could not load image_gen_config.json: %s", exc)
    return merged


def _cfg_value(cfg: Dict[str, Any], key: str, env: Optional[str] = None, default: Any = None) -> Any:
    """Config first, env fallback, then default."""
    if key in cfg and cfg[key] not in (None, ""):
        return cfg[key]
    if env:
        val = os.environ.get(env)
        if val:
            return val
    return default


def _resolve_endpoint() -> Tuple[str, str, str]:
    """Return ``(base_url, api_key, model)`` from config/env."""
    cfg = _load_config()
    base_url = str(_cfg_value(cfg, "base_url", "OPENAI_COMPATIBLE_BASE_URL", "")).strip().rstrip("/")
    api_key = str(_cfg_value(cfg, "api_key", "OPENAI_COMPATIBLE_API_KEY", "")).strip()
    # Generic escape hatch: some users configure a shared key in provider_keys.
    if not api_key:
        api_key = os.environ.get("IMAGE_API_KEY", "").strip()
    model = str(_cfg_value(cfg, "model", "OPENAI_COMPATIBLE_MODEL", "")).strip()
    return base_url, api_key, model


def _load_image_bytes(ref: str) -> Tuple[bytes, str]:
    """Load image bytes from a URL, data URL or local path."""
    ref = ref.strip()
    lower = ref.lower()
    if lower.startswith(("http://", "https://")):
        import requests

        resp = requests.get(ref, timeout=60)
        resp.raise_for_status()
        name = ref.split("?", 1)[0].rsplit("/", 1)[-1] or "image.png"
        return resp.content, name
    if lower.startswith("data:"):
        import base64

        header, _, b64 = ref.partition(",")
        ext = "png"
        if "image/" in header:
            ext = header.split("image/", 1)[1].split(";", 1)[0] or "png"
        return base64.b64decode(b64), f"image.{ext}"
    from agent.file_safety import raise_if_read_blocked

    raise_if_read_blocked(ref)
    with open(ref, "rb") as fh:
        data = fh.read()
    name = os.path.basename(ref) or "image.png"
    return data, name


class OpenAICompatibleImageGenProvider(ImageGenProvider):
    """BYO-endpoint backend for any OpenAI ``images`` compatible service."""

    @property
    def name(self) -> str:
        return PROVIDER

    @property
    def display_name(self) -> str:
        return DISPLAY_NAME

    def is_available(self) -> bool:
        base_url, api_key, _model = _resolve_endpoint()
        if not base_url or not api_key:
            return False
        try:
            import openai  # noqa: F401
        except ImportError:
            return False
        return True

    def list_models(self) -> List[Dict[str, Any]]:
        _base, _key, model = _resolve_endpoint()
        if not model:
            return []
        return [
            {
                "id": model,
                "display": model,
                "strengths": "OpenAI-compatible endpoint (config: image_gen.openai_compatible.model)",
                "price": "per provider",
            }
        ]

    def default_model(self) -> Optional[str]:
        _base, _key, model = _resolve_endpoint()
        return model or None

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": DISPLAY_NAME,
            "badge": "config",
            "tag": "火山方舟 Seedream / 智谱 GLM-Image / OpenAI 官方 / 任意兼容端点 — 在 config.yaml 的 image_gen.openai_compatible 配置",
            "env_vars": [
                {"key": "OPENAI_COMPATIBLE_API_KEY", "prompt": "API key", "url": ""},
                {"key": "OPENAI_COMPATIBLE_BASE_URL", "prompt": "Base URL（如 https://ark.cn-beijing.volces.com/api/v3）", "url": ""},
            ],
        }

    def capabilities(self) -> Dict[str, Any]:
        cfg = _load_config()
        edits = bool(_cfg_value(cfg, "edits", default=True))
        max_refs = int(_cfg_value(cfg, "max_reference_images", default=4))
        return {
            "modalities": ["text", "image"] if edits else ["text"],
            "max_reference_images": max_refs,
        }

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

        base_url, api_key, model = _resolve_endpoint()
        if not base_url or not api_key:
            return error_response(
                error=(
                    "openai-compatible 未配置：请在 config.yaml 的 image_gen.openai_compatible "
                    "设置 base_url 和 api_key（或设置 OPENAI_COMPATIBLE_BASE_URL / "
                    "OPENAI_COMPATIBLE_API_KEY 环境变量）"
                ),
                error_type="auth_required",
                provider=PROVIDER,
                aspect_ratio=aspect,
            )
        if not model:
            return error_response(
                error="openai-compatible 未配置 model（config.yaml → image_gen.openai_compatible.model）",
                error_type="invalid_argument",
                provider=PROVIDER,
                aspect_ratio=aspect,
            )

        try:
            import openai
        except ImportError:
            return error_response(
                error="openai Python package not installed (pip install openai)",
                error_type="missing_dependency",
                provider=PROVIDER,
                model=model,
                aspect_ratio=aspect,
            )

        cfg = _load_config()
        n = int(_cfg_value(cfg, "n", default=1))
        size = str(_cfg_value(cfg, "size", default="1024x1024"))
        if aspect == "landscape":
            size = str(_cfg_value(cfg, "landscape_size", default=size))
        elif aspect == "portrait":
            size = str(_cfg_value(cfg, "portrait_size", default=size))

        sources: List[str] = []
        if isinstance(image_url, str) and image_url.strip():
            sources.append(image_url.strip())
        for ref in (normalize_reference_images(reference_image_urls) or []):
            sources.append(ref)
        max_refs = int(_cfg_value(cfg, "max_reference_images", default=4))
        sources = sources[: max(1, max_refs)]
        is_edit = bool(sources)

        edits_allowed = bool(_cfg_value(cfg, "edits", default=True))
        if is_edit and not edits_allowed:
            return error_response(
                error=(
                    "该端点未启用图生图/编辑（config: image_gen.openai_compatible.edits=false）。"
                    "请使用纯文生图提示词。"
                ),
                error_type="unsupported",
                provider=PROVIDER,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        client = openai.OpenAI(base_url=base_url, api_key=api_key)
        modality = "image" if is_edit else "text"

        try:
            if is_edit:
                import io

                files = []
                for ref in sources:
                    data, fname = _load_image_bytes(ref)
                    bio = io.BytesIO(data)
                    bio.name = fname
                    files.append(bio)
                response = client.images.edit(
                    model=model,
                    image=files if len(files) > 1 else files[0],
                    prompt=prompt,
                    size=size,
                    n=n,
                )
            else:
                response = client.images.generate(
                    model=model,
                    prompt=prompt,
                    size=size,
                    n=n,
                )
        except Exception as exc:
            logger.debug("openai-compatible image generation failed", exc_info=True)
            return error_response(
                error=f"图像生成失败: {exc}",
                error_type="api_error",
                provider=PROVIDER,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        data = getattr(response, "data", None) or []
        if not data:
            return error_response(
                error="API 返回了空结果（无 data）",
                error_type="api_error",
                provider=PROVIDER,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        # Save every returned image; primary is the first one.
        saved: List[str] = []
        prefix = "image" + ("_edit" if is_edit else "")
        for item in data:
            b64 = getattr(item, "b64_json", None) or (item.get("b64_json") if isinstance(item, dict) else None)
            url = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None)
            try:
                if b64:
                    saved.append(str(save_b64_image(b64, prefix=prefix)))
                elif url:
                    saved.append(str(save_url_image(url, prefix=prefix)))
                else:
                    logger.warning("Image item had neither b64_json nor url: %r", item)
            except Exception as exc:
                logger.warning("Could not persist generated image: %s", exc)
                if url:
                    saved.append(url)
                elif b64:
                    saved.append(f"data:image/png;base64,{b64[:80]}…")

        if not saved:
            return error_response(
                error="图像生成成功但无法保存/解析返回数据",
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
    ctx.register_image_gen_provider(OpenAICompatibleImageGenProvider())
