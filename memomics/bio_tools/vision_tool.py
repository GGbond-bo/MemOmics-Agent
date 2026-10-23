# -*- coding: utf-8 -*-
"""vision_describe — MemOmics 视觉工具 v3（2026-10-24 视觉路由）。

路由（mode="auto"，默认）：
  当前会话模型能读图（按模型名启发式判定）→ 优先用模型自己的视觉能力读图；
  模型没有视觉 / 视觉调用失败 → 回退本地图像分析管道：
  1. OCR（RapidOCR，服务器 Python312 已装；失败降级跳过）
  2. 颜色分布（主色 + 区域配色）
  3. 坐标轴/图形元素检测（OpenCV；失败降级 PIL）
  4. ASCII 亮度图（文本模型能"读"的粗粒度形状）

mode="local"：强制纯本地管道（门禁/核验场景——机器判据全量在这边）。
mode="model"：强制模型视觉（失败不回退，直接报错）。
也可作为命令行独立运行: python vision_tool.py <图片路径>
"""
import base64
import json
import logging
import os
import re
import sys

logger = logging.getLogger("memomics.vision_tool")

_ASCII_CHARS = " .:-=+*#%@"

# ==================== 视觉能力启发式（2026-10-24）====================
# 用户口径：大模型自己知道自己有没有视觉，不设手工标记——按模型名判定。
# 判不出 → 按无视觉处理（回退本地管道，宁稳不错）。
# 排除项优先：图像「生成」模型（gpt-image/seedream/dall-e/flux…）与
# embedding/tts/rerank 等名字里可能撞上关键词的非视觉理解模型。
_VISION_NEG_RE = re.compile(
    r"(embed|whisper|tts|rerank|bge-|dall|gpt-image|seedream|seedance|flux|"
    r"stable-diffusion|image[-_]?(gen|01)|kolors|hunyuan-dit|cogview)", re.I)
_VISION_POS_RE = re.compile(
    r"(vision|[-_/]vl[-_.\d]|^vl[-_.\d]|qwen[.\d-]*vl|internvl|glm-4[.\d]*v|"
    r"4v\b|4o\b|gpt-4[.\d-]*o|gpt-5|o4-mini|claude[-\d.]|gemini|pixtral|llava|"
    r"minicpm-v|doubao-vision|kimi[-\w]*(?:vision|vl|k2\.[5-9]|k3)|grok-[24]|"
    r"minimax-?m\d|step[-\w]*[.\d]v\b|sensechat-v|hunyuan-vision|ernie-4[.\d]*v|"
    r"abab6.*v|moonshot-v1-\d+k-vision|deepseek[-\w]*(?:v4|flash))", re.I)


def _model_supports_vision(cfg):
    """按模型名启发式判定当前模型是否有视觉。cfg: {model, base_url, api_key,...}。"""
    name = str((cfg or {}).get("model") or "").lower().strip()
    if not name:
        return False
    if _VISION_NEG_RE.search(name):
        return False
    return bool(_VISION_POS_RE.search(name))


def _resize_for_vision(img, max_side=1568, quality=85):
    """缩到视觉 API 常用规格（≤1568px，JPEG q85），控制 base64 体积。"""
    w, h = img.size
    if max(w, h) > max_side:
        r = max_side / float(max(w, h))
        img = img.resize((max(1, int(w * r)), max(1, int(h * r))))
    import io
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _call_model_vision(image_path, question, cfg):
    """用当前会话模型自己的视觉能力读图（OpenAI 兼容 image_url 协议）。

    凭据与请求头规则与 debate_analysis._call_llm_sync 同款（含 opencode 等
    网关的 extra_headers）。任何失败抛异常——调用方负责回退本地管道。
    """
    Image = _load_pil()
    img = Image.open(image_path)
    img.load()
    data = _resize_for_vision(img)
    b64 = base64.b64encode(data).decode("ascii")
    try:
        from memomics.bio_tools.debate_analysis import _provider_extra_headers
        extra = _provider_extra_headers(str(cfg.get("base_url") or ""))
    except Exception:
        extra = {}
    headers = {
        "Authorization": "Bearer %s" % str(cfg.get("api_key") or ""),
        "Content-Type": "application/json",
    }
    headers.update(extra or {})
    prompt = ((question or "描述这张图片的内容").strip()
              + "\n\n要求：只基于图片真实内容回答；图中的数字、文字、坐标轴/图例标签逐一读出，不要猜。"
                "读不出的地方明说读不出。")
    payload = {
        "model": cfg.get("model"),
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
        ]}],
        "max_tokens": 1500,
        "temperature": 0.2,
    }
    import httpx
    base = str(cfg.get("base_url") or "").rstrip("/")
    if not base:
        raise RuntimeError("会话模型配置缺 base_url")
    with httpx.Client(timeout=120) as client:
        resp = client.post(base + "/chat/completions", headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError("HTTP %s %s" % (resp.status_code, resp.text[:200]))
        msg = resp.json()["choices"][0]["message"]
        content = msg.get("content") or ""
        if isinstance(content, list):  # 部分网关把正文分段
            content = "".join(seg.get("text", "") for seg in content if isinstance(seg, dict))
        if not str(content).strip():
            raise RuntimeError("视觉模型返回空内容")
        return str(content).strip()


def _load_pil():
    from PIL import Image
    return Image


def _ascii_art(img, cols=64, rows=32):
    """把图片降采样成 ASCII 亮度图（文本模型可读的粗粒度形状）。"""
    try:
        g = img.convert("L").resize((cols, rows))
        px = g.load()
        lines = []
        for y in range(rows):
            row = ""
            for x in range(cols):
                v = px[x, y]
                row += _ASCII_CHARS[min(len(_ASCII_CHARS) - 1, v * len(_ASCII_CHARS) // 256)]
            lines.append(row.rstrip())
        return "\n".join(lines)
    except Exception:
        return ""


def _dominant_colors(img, max_colors=6):
    """主色统计（量化到 32 级）。"""
    try:
        small = img.convert("RGB").resize((96, 96))
        from collections import Counter
        cnt = Counter()
        for p in small.getdata():
            r, g, b = (v // 32 * 32 for v in p)
            cnt[(r, g, b)] += 1
        total = 96 * 96
        out = []
        for (r, g, b), n in cnt.most_common(max_colors):
            pct = round(n * 100.0 / total, 1)
            out.append({"color": f"#{r:02x}{g:02x}{b:02x}", "percent": pct})
        return out
    except Exception:
        return []


def _detect_chart_elements(img):
    """图形元素检测: 坐标轴/条形/热力网格。失败返回空。"""
    out = {}
    try:
        import cv2
        import numpy as np
        arr = np.array(img.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape
        edges = cv2.Canny(gray, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                                minLineLength=int(w * 0.25), maxLineGap=10)
        horiz = []
        vert = []
        if lines is not None:
            for x1, y1, x2, y2 in lines[:, 0]:
                if abs(y1 - y2) < 6:
                    horiz.append((y1 + y2) // 2)
                elif abs(x1 - x2) < 6:
                    vert.append((x1 + x2) // 2)
        if horiz:
            y_axis = max(set(horiz), key=horiz.count)
            out["axis"] = "检测到横坐标轴 (y≈%d/%d)" % (y_axis, h)
            if any(x < w * 0.25 for x in vert):
                out["axis"] += " + 纵坐标轴 (左侧)"
        if vert:
            x_axis = max(set(vert), key=vert.count)
            out["vertical_axis"] = "检测到纵轴 (x≈%d/%d)" % (x_axis, w)
        # 条形检测: 底部区域按列统计边缘密度
        bottom = edges[int(h * 0.5):, :]
        col_density = bottom.sum(axis=0)
        peaks = int((col_density > col_density.mean() + col_density.std()).sum())
        if peaks > w * 0.15:
            out["bars"] = "底部区域检测到柱状/条带元素"
        # 网格检测: 横向线多 → 可能是表格或热力图
        if len(horiz) >= 4:
            out["grid"] = f"检测到 {len(horiz)} 条水平线（可能含表格/多子图）"
    except Exception as e:
        logger.debug("chart detection unavailable: %s", e)
    return out


_OCR_ENGINE = None
_OCR_DISABLED = os.environ.get("MEMOMICS_VISION_NO_OCR") in ("1", "true", "yes")


def _get_ocr_engine():
    """OCR 引擎懒加载 + 全局缓存（首次调用才加载模型，之后复用）。

    - 磁盘 ~200MB 一次性，CPU 推理每图 1-3 秒，无 GPU 依赖
    - MEMOMICS_VISION_NO_OCR=1 可整体禁用
    - rapidocr_onnxruntime/opencv 均为跨平台（Linux/macOS/Windows 同一套代码）
    """
    global _OCR_ENGINE
    if _OCR_DISABLED:
        return None
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    try:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
        logger.info("RapidOCR engine loaded (lazy, cached)")
        return _OCR_ENGINE
    except Exception as e:
        logger.warning("OCR unavailable: %s", e)
        _OCR_ENGINE = False  # 标记不可用，避免反复重试
        return None


def _ocr_text(img):
    """RapidOCR 文本提取（懒加载+缓存；失败返回空列表）。"""
    try:
        engine = _get_ocr_engine()
        if engine is None:
            return []
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        img.convert("RGB").save(tmp)
        result, _ = engine(tmp)
        os.remove(tmp)
        out = []
        if result:
            for box, text, conf in result:
                if not text or not str(text).strip():
                    continue
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                out.append({
                    "text": str(text).strip(),
                    "x": int(min(xs)), "y": int(min(ys)),
                    "conf": round(float(conf), 2),
                })
        return out
    except Exception as e:
        logger.warning("OCR unavailable: %s", e)
        return []


def _local_describe(image_path):
    """本地图像分析（不调用任何模型/API）。"""
    Image = _load_pil()
    img = Image.open(image_path)
    img.load()
    w, h = img.size
    desc = {
        "ok": True,
        "mode": "local",
        "file": os.path.basename(image_path),
        "size": f"{w}x{h}",
        "format": (img.format or "").upper(),
        "colors": _dominant_colors(img),
        "ocr": _ocr_text(img),
        "chart": _detect_chart_elements(img),
        "ascii": _ascii_art(img),
    }
    return desc


def _format_describe(desc):
    """把描述打包成给文本模型读的中文文本。"""
    lines = [
        "[本地图像分析 · 纯文本模型读图 · 无视觉API]",
        f"尺寸: {desc['size']} ({desc['format']})",
    ]
    if desc.get("colors"):
        _c = ", ".join(f"{x['color']} {x['percent']}%" for x in desc["colors"][:5])
        lines.append(f"主色: {_c}")
    if desc.get("chart"):
        for _k in ("axis", "vertical_axis", "bars", "grid"):
            if desc["chart"].get(_k):
                lines.append(desc["chart"][_k])
    if desc.get("ocr"):
        lines.append(f"OCR 文本 ({len(desc['ocr'])} 条, 按位置排序):")
        for o in sorted(desc["ocr"], key=lambda x: (x["y"], x["x"]))[:40]:
            lines.append(f'  - "{o["text"]}" @({o["x"]},{o["y"]}) 置信={o["conf"]}')
    else:
        _eng = _get_ocr_engine()
        if not _eng:
            lines.append("OCR 文本: 无（OCR 引擎不可用——未安装 rapidocr_onnxruntime 或被 MEMOMICS_VISION_NO_OCR 禁用）")
        else:
            lines.append("OCR 文本: 无（OCR 引擎正常，未检出文本；原图可能无字、字太小或对比度不足）")
    if desc.get("ascii"):
        lines.append("ASCII 亮度图 (64x32, 越亮字符越密):")
        lines.append(desc["ascii"])
    return "\n".join(lines)


def vision_describe(image_path: str = "", question: str = "描述这张图片的内容",
                    max_tokens: int = 800, mode: str = "auto") -> str:
    """看图路由：模型有视觉 → 模型自己读；没有/失败 → 本地 OCR 管道。

    mode: "auto"（默认，按模型能力自动选路）| "model"（强制模型视觉，失败报错）
          | "local"（强制本地管道——门禁/核验要机器判据时用这个）。
    """
    if not image_path:
        return json.dumps({"ok": False, "error": "image_path 必填（本地绝对路径）"}, ensure_ascii=False)
    if not os.path.isfile(image_path):
        return json.dumps({"ok": False, "error": f"图片不存在: {image_path}"}, ensure_ascii=False)
    mode = str(mode or "auto").strip().lower()
    if mode not in ("auto", "model", "local"):
        mode = "auto"
    # 当前会话的模型配置（server.py 每回合经 ContextVar 注入；CLI 独立运行为空 → 本地）
    cfg = {}
    try:
        from memomics.bio_tools.debate_analysis import get_session_model_config
        cfg = get_session_model_config() or {}
    except Exception:
        cfg = {}
    use_model = (mode == "model") or (mode == "auto" and _model_supports_vision(cfg))
    model_err = ""
    if use_model:
        try:
            answer = _call_model_vision(image_path, question, cfg)
            # 附精简本地事实（核验锚点：尺寸 + 主色）；全量机器判据走 mode="local"
            Image = _load_pil()
            img = Image.open(image_path)
            img.load()
            w, h = img.size
            colors = _dominant_colors(img)
            _c = ", ".join(f"{x['color']} {x['percent']}%" for x in colors[:5]) if colors else "（取色失败）"
            text = (f"[模型视觉 · {cfg.get('model', '?')}]\n{answer}\n\n"
                    f"[本地事实] 尺寸 {w}x{h}；主色：{_c}\n"
                    "（需要 OCR 条数/颜色数/ASCII 图等机器判据时，用 mode=\"local\" 取全量本地管道）")
            return json.dumps({
                "ok": True,
                "mode": "model",
                "model": cfg.get("model", ""),
                "describe_text": text,
                "note": "以上正文是当前模型用自己的视觉能力读图的结果（可以据此声称看到了图片内容）；"
                        "本地事实仅供核验锚点。",
            }, ensure_ascii=False)
        except Exception as e:
            model_err = f"{type(e).__name__}: {e}"
            logger.warning("模型视觉调用失败，回退本地管道: %s", model_err)
            if mode == "model":
                return json.dumps({"ok": False, "mode": "model",
                                   "error": f"模型视觉调用失败: {model_err}"}, ensure_ascii=False)
    try:
        desc = _local_describe(image_path)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"本地分析失败: {e}"}, ensure_ascii=False)
    out = {
        "ok": True,
        "mode": "local",
        "describe_text": _format_describe(desc),
        "note": "以上是本地图像分析的事实清单（OCR+颜色+结构+ASCII图）。"
                "请基于这些事实回答用户问题，不要声称'看到了图片'。"
                "关键数字/文字以 OCR 为准；形状布局参考 ASCII 图与元素检测。",
    }
    if model_err:
        out["model_fallback"] = f"模型视觉不可用（{model_err}），已回退本地管道"
    return json.dumps(out, ensure_ascii=False)


SCHEMA = {
    "name": "vision_describe",
    "description": (
        "看图工具（自动选路）：当前模型有视觉时优先用模型自己的读图能力（返回模型对图片的"
        "直接理解与逐项读数）；模型没有视觉时自动回退本地管道（OCR 提取图中文字 + 颜色分布 + "
        "坐标轴/柱状/网格等元素检测 + ASCII 亮度图）。用户发图片、需要核对图表/截图/"
        "示意图内容时必须调用，基于返回内容回答，禁止凭空描述图片内容。"
        "mode 参数平时省略即可（默认 auto 自动选路）；仅当门禁/核验必须要 OCR 条数等"
        "机器判据时才传 \"local\"；强制模型视觉传 \"model\"。image_path 为本地绝对路径。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "image_path": {"type": "string", "description": "图片本地绝对路径"},
            "question": {"type": "string", "description": "要回答的问题（分析结果里取对应事实）"},
            "max_tokens": {"type": "integer", "default": 800, "description": "保留（接口兼容）"},
            "mode": {"type": "string", "default": "auto",
                     "description": "平时省略（=auto 自动选路）；local=强制本地管道（仅门禁/核验要机器判据时）；model=强制模型视觉"},
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
                args.get("mode", "auto"),
            ),
            emoji="👁️",
            max_result_size_chars=12_000,
        )
    except Exception as e:
        logger.warning(f"vision_describe register failed: {e}")


_register()


if __name__ == "__main__":
    # 命令行独立运行: python vision_tool.py <图片路径>
    if len(sys.argv) > 1:
        print(vision_describe(sys.argv[1]))
    else:
        print("用法: python vision_tool.py <图片路径>")
