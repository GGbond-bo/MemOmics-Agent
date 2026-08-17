# -*- coding: utf-8 -*-
"""vision_describe — MemOmics 视觉工具 v2（2026-08-14）。

纯文本模型"看图"方案：不换模型、不调视觉 API。
本地图像分析管道把图片转成结构化文字描述：
  1. OCR（RapidOCR，服务器 Python312 已装；失败降级跳过）
  2. 颜色分布（主色 + 区域配色）
  3. 坐标轴/图形元素检测（OpenCV；失败降级 PIL）
  4. ASCII 亮度图（文本模型能"读"的粗粒度形状）
→ 文本模型从描述里完成视觉理解。

可选增强（默认关闭）：设置环境变量 MEMOMICS_VISION_MODEL 后，
描述末尾附带一次视觉模型回答（kimi-k2.6 等）。
也可作为命令行独立运行: python vision_tool.py <图片路径>
"""
import json
import logging
import os
import sys

logger = logging.getLogger("memomics.vision_tool")

_ASCII_CHARS = " .:-=+*#%@"


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
        lines.append("OCR 文本: 无（OCR 引擎不可用）")
    if desc.get("ascii"):
        lines.append("ASCII 亮度图 (64x32, 越亮字符越密):")
        lines.append(desc["ascii"])
    return "\n".join(lines)


def vision_describe(image_path: str = "", question: str = "描述这张图片的内容",
                    max_tokens: int = 800) -> str:
    """本地图像分析 → 结构化文字描述（供文本模型理解图片）。

    不调用任何视觉模型。question 参数保留用于接口兼容（描述本身是全面的事实清单，
    文本模型可据此回答任何问题）。
    """
    if not image_path:
        return json.dumps({"ok": False, "error": "image_path 必填（本地绝对路径）"}, ensure_ascii=False)
    if not os.path.isfile(image_path):
        return json.dumps({"ok": False, "error": f"图片不存在: {image_path}"}, ensure_ascii=False)
    try:
        desc = _local_describe(image_path)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"本地分析失败: {e}"}, ensure_ascii=False)
    return json.dumps({
        "ok": True,
        "mode": "local",
        "describe_text": _format_describe(desc),
        "note": "以上是本地图像分析的事实清单（OCR+颜色+结构+ASCII图）。"
                "请基于这些事实回答用户问题，不要声称'看到了图片'。"
                "关键数字/文字以 OCR 为准；形状布局参考 ASCII 图与元素检测。",
    }, ensure_ascii=False)


SCHEMA = {
    "name": "vision_describe",
    "description": (
        "用本地图像分析管道'读图'（不调用视觉模型）：OCR 提取图中文字 + 颜色分布 + "
        "坐标轴/柱状/网格等元素检测 + ASCII 亮度图。用户发图片、需要核对图表/截图/"
        "示意图内容时必须调用，基于返回的事实清单回答，禁止凭空描述图片内容。"
        "image_path 为本地绝对路径。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "image_path": {"type": "string", "description": "图片本地绝对路径"},
            "question": {"type": "string", "description": "要回答的问题（分析结果里取对应事实）"},
            "max_tokens": {"type": "integer", "default": 800, "description": "保留（接口兼容）"},
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
