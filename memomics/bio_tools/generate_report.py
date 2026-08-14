"""generate_report — 分析报告 HTML 生成工具。

将分析全过程的思考、方法、参数、结果、图片、辩论记录
打包成一个自包含的 HTML 文件，放在桌面。
"""
import json
import os
import base64
import datetime
import logging

logger = logging.getLogger(__name__)

SCHEMA = {
    "name": "generate_report",
    "description": (
        "Generate a self-contained HTML analysis report with thinking "
        "process, methods, parameters, results, images, debate records. "
        "The report is saved to the user's Desktop. "
        "Call this at the end of analysis to produce the final deliverable."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Report title"
            },
            "content_html": {
                "type": "string",
                "description": "Full HTML content of the report body (between <main> tags). Include all sections: requirements, data scan, methods, parameters, results, images (as base64 or file links), debate, conclusion."
            },
            "output_path": {
                "type": "string",
                "description": "输出路径（可选，默认: results/<sid>/reports/，否则桌面）",
                "default": ""
            },
            "figures": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要自动嵌入报告的图片路径列表（base64 内嵌，自包含）"
            }
        },
        "required": ["title", "content_html"]
    }
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Segoe UI','Microsoft YaHei',sans-serif; background:#f5f7fa; color:#333; line-height:1.8; }}
.container {{ max-width:960px; margin:0 auto; padding:40px 20px; }}
header {{ text-align:center; padding:30px 0; border-bottom:3px solid #4fc3f7; margin-bottom:30px; }}
header h1 {{ color:#1565c0; font-size:28px; }}
header .meta {{ color:#888; font-size:14px; margin-top:8px; }}
section {{ background:#fff; border-radius:8px; padding:24px 28px; margin-bottom:20px; box-shadow:0 1px 4px rgba(0,0,0,0.06); }}
section h2 {{ color:#1565c0; font-size:20px; border-left:4px solid #4fc3f7; padding-left:12px; margin-bottom:16px; }}
section h3 {{ color:#37474f; font-size:16px; margin:16px 0 8px; }}
section p {{ margin-bottom:10px; }}
section code {{ background:#f0f4f8; padding:2px 6px; border-radius:3px; font-family:Consolas,monospace; font-size:13px; color:#c62828; }}
section pre {{ background:#263238; color:#eceff1; padding:16px; border-radius:6px; overflow-x:auto; margin:12px 0; }}
section pre code {{ background:transparent; color:inherit; padding:0; }}
section img {{ max-width:100%; border-radius:6px; margin:12px 0; box-shadow:0 2px 8px rgba(0,0,0,0.1); }}
section figure {{ margin:12px 0; }}
section figcaption {{ color:#888; font-size:13px; text-align:center; margin-top:6px; }}
.debate {{ border-left:4px solid #ff9800; }}
.debate h2 {{ border-left-color:#ff9800; color:#e65100; }}
.conclusion {{ border-left:4px solid #4caf50; }}
.conclusion h2 {{ border-left-color:#4caf50; color:#2e7d32; }}
.tag {{ display:inline-block; background:#e3f2fd; color:#1565c0; padding:2px 10px; border-radius:12px; font-size:12px; margin:2px; }}
</style>
</head>
<body>
<div class="container">
<header>
<h1>{title}</h1>
<div class="meta">MemOmics 生信分析报告 · {timestamp}</div>
</header>
{content}
</div>
</body>
</html>"""


def _embed_figures(figures) -> str:
    """把图片路径列表转成内嵌 base64 的 HTML 段落（失败的文件降级为文字链接）。"""
    if not figures:
        return ""
    items = []
    for fp in figures:
        fp = str(fp or "").strip()
        if not fp:
            continue
        name = os.path.basename(fp)
        if os.path.isfile(fp):
            ext = os.path.splitext(fp)[1].lower().lstrip(".")
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "svg": "image/svg+xml", "gif": "image/gif", "webp": "image/webp"}.get(ext)
            if mime:
                try:
                    with open(fp, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    items.append(
                        f'<figure><img src="data:{mime};base64,{b64}" alt="{name}">'
                        f"<figcaption>{name}</figcaption></figure>")
                    continue
                except Exception as e:
                    logger.warning("figure embed failed: %s %s", fp, e)
        items.append(f'<p><a href="file:///{fp}">{name}</a>（未嵌入）</p>')
    if not items:
        return ""
    return ('<section><h2>📊 分析图片</h2>'
            + "".join(items) + "</section>")


def _default_output_path(title: str) -> str:
    """默认输出: 会话 results/<sid>/reports/ 优先，否则桌面。"""
    try:
        from memomics.bio_tools.debate_analysis import get_session_results_dir
        rd = get_session_results_dir()
        if rd:
            reports = os.path.join(rd, "reports")
            safe_title = "".join(c for c in title if c.isalnum() or c in "._- ")[:50]
            return os.path.join(reports, f"report_{safe_title}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    except Exception:
        pass
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.join(os.path.expanduser("~"), "桌面")
    if not os.path.isdir(desktop):
        desktop = os.path.expanduser("~")
    safe_title = "".join(c for c in title if c.isalnum() or c in "._- ")[:50]
    return os.path.join(desktop, f"MemOmics_{safe_title}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html")


def generate_report(title: str, content_html: str, output_path: str = "",
                    figures=None) -> str:
    """生成自包含 HTML 报告（2026-08-15 升级：figures 自动 base64 内嵌）。

    - figures: 图片路径列表，自动内嵌为自包含报告（可离线打开/分享）
    - 默认输出: 会话 results/<sid>/reports/，否则桌面（旧行为）
    """
    figures = figures or []
    if not output_path:
        output_path = _default_output_path(title)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    figures_html = _embed_figures(figures)
    body = content_html + figures_html
    html = HTML_TEMPLATE.format(title=title, timestamp=timestamp, content=body)

    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
    except OSError as e:
        return json.dumps({"success": False, "error": f"无法创建输出目录: {e}"}, ensure_ascii=False)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return json.dumps({
        "success": True,
        "report_path": output_path,
        "title": title,
        "timestamp": timestamp,
        "size_kb": round(len(html) / 1024, 1),
        "embedded_figures": len(figures),
    }, ensure_ascii=False, indent=2)


def _register():
    from tools.registry import registry
    registry.register(
        name="generate_report",
        toolset="memomics",
        schema=SCHEMA,
        handler=lambda args, **kw: generate_report(
            args.get("title", "MemOmics分析报告"),
            args.get("content_html", ""),
            args.get("output_path", ""),
            args.get("figures", []),
        ),
        emoji="📄",
        max_result_size_chars=50_000,
    )

_register()
