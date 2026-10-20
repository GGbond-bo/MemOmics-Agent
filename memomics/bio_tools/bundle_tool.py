# -*- coding: utf-8 -*-
"""资产包 agent 工具：对话里直接说「导出/打包」「导入这个包」即可，不依赖设置面板。

UI 只保留「导出」（2026-10-21 用户要求）；导入改由对话完成：
用户把 zip 路径发进来（或用输入框「+」选中文件插入路径），模型调用本工具导入。
"""
import json
import logging

from memomics import bundle as _b

logger = logging.getLogger(__name__)


def bundle_tool(action: str = "list", scopes: str = "kb,skills,memory", topic: str = "",
                path: str = "", out: str = "", redact: bool = True,
                overrides: list = None, backup: bool = True) -> str:
    """action=export 导出打包 / preview 预览包 / import 导入 / list 列出历史包。"""
    act = (action or "list").strip().lower()
    try:
        if act == "export":
            res = _b.export_bundle([s.strip() for s in (scopes or "").split(",") if s.strip()],
                                   out or __import__("os").path.join(_b._home(), "exports"),
                                   topic=topic or None, redact=bool(redact))
            if res.get("ok"):
                man = res.get("manifest") or {}
                res["manifest"] = {k: v for k, v in man.items() if k != "files"}
            return json.dumps(res, ensure_ascii=False)
        if act == "preview":
            return json.dumps(_b.preview_bundle(path), ensure_ascii=False)
        if act == "import":
            ov = {}
            for p in (overrides or []):
                ov[str(p)] = "overwrite"
            return json.dumps(_b.import_bundle(path, overrides=ov, backup=bool(backup)), ensure_ascii=False)
        return json.dumps({"ok": True, "bundles": _b.list_bundles()}, ensure_ascii=False)
    except Exception as exc:
        logger.warning("[bundle_tool] %s 失败: %s", act, exc)
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


SCHEMA = {
    "name": "bundle",
    "description": ("MemOmics 资产包（记忆/知识库/技能）：导出打包、预览、导入。"
                    "用户说「打包我的经验」「导出资产」→ action=export；"
                    "用户给了一个 .zip 路径说「导入这个包」→ 先 action=preview 看冲突，"
                    "再 action=import（默认只新增不覆盖，要覆盖就用 overrides 传包内路径）。"),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["export", "preview", "import", "list"]},
            "scopes": {"type": "string", "description": "导出范围，逗号分隔：kb,skills,memory（默认全部）"},
            "topic": {"type": "string", "description": "只导出某主题（如 deg-analysis），留空=全量"},
            "path": {"type": "string", "description": "包文件路径（preview/import 用）"},
            "out": {"type": "string", "description": "导出目录（默认 memomics_home/exports）"},
            "redact": {"type": "boolean", "description": "导出时脱敏本机路径（默认 true）"},
            "overrides": {"type": "array", "items": {"type": "string"},
                          "description": "要覆盖的包内相对路径（默认跳过冲突）"},
            "backup": {"type": "boolean", "description": "导入前自动备份（默认 true）"},
        },
        "required": ["action"],
    },
}


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="bundle",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: bundle_tool(
                action=args.get("action", "list"),
                scopes=args.get("scopes", "kb,skills,memory"),
                topic=args.get("topic", ""),
                path=args.get("path", ""),
                out=args.get("out", ""),
                redact=arg_redact(args),
                overrides=args.get("overrides"),
                backup=args.get("backup", True),
            ),
            emoji="📦",
            max_result_size_chars=6000,
        )
    except Exception as exc:
        logger.warning("bundle tool register failed: %s", exc)


def arg_redact(args):
    try:
        return bool(args.get("redact", True))
    except Exception:
        return True


_register()
