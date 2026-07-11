"""Module selector tool — guides users through analysis module selection."""
import json
import logging

logger = logging.getLogger(__name__)

SCHEMA = {
    "name": "guide_analysis",
    "description": (
        "Guide the user through selecting analysis modules. Returns available "
        "modules (01 decontamination, 02 basic, 03 advanced, 04 personalized) "
        "and combo options. Call this after scan_data to let the user choose "
        "what analysis to run."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "data_stage": {
                "type": "string",
                "description": "Data stage: 'raw' or 'annotated'",
                "enum": ["raw", "annotated"]
            },
            "redo": {
                "type": "boolean",
                "description": "Whether user wants to re-analyze (redo)",
                "default": False
            }
        },
        "required": ["data_stage"]
    }
}

MODULES = {
    "01": {
        "name": "深度去污染",
        "icon": "🧹",
        "desc": "CellBender/SoupX/DoubletFinder — 探索性分析不建议",
        "substeps": [
            {"id": "cellbender", "name": "CellBender 去除环境RNA", "skill": "cellbender-remove-background"},
            {"id": "soupx", "name": "SoupX 去污染", "skill": "soupx-decontamination"},
            {"id": "doublet", "name": "DoubletFinder 去双胞", "skill": "doubletfinder"},
        ]
    },
    "02": {
        "name": "基础分析",
        "icon": "📊",
        "desc": "QC → 标准化 → 批次校正 → 降维 → 聚类 → 注释 → Markers",
        "substeps": [
            {"id": "qc", "name": "质控 QC", "skill": "scrna-clustering"},
            {"id": "normalize", "name": "标准化 (SCTransform)", "skill": "scrna-clustering"},
            {"id": "harmony", "name": "批次校正 (Harmony)", "skill": "create_harmony_embeddings_scRNA"},
            {"id": "dimred", "name": "降维 (PCA+UMAP)", "skill": "scrna-clustering"},
            {"id": "cluster", "name": "聚类 (Leiden)", "skill": "scrna-clustering"},
            {"id": "annotate", "name": "细胞注释 (SingleR+markers)", "skill": "annotate_celltype_scRNA"},
            {"id": "markers", "name": "FindAllMarkers", "skill": "deg-analysis"},
        ]
    },
    "03": {
        "name": "高级分析",
        "icon": "🔬",
        "desc": "DEG+富集 / CellChat / 轨迹 / SCENIC — 基础分析完成后推荐",
        "substeps": [
            {"id": "deg", "name": "差异表达+富集 (DEG+GSEA)", "skill": "deg-analysis"},
            {"id": "cellchat", "name": "细胞通讯 (CellChat v2)", "skill": "cellchat-v2"},
            {"id": "trajectory", "name": "轨迹推断 (Monocle3)", "skill": "trajectory-analysis"},
            {"id": "scenic", "name": "SCENIC调控网络", "skill": "grn-pyscenic"},
        ]
    },
    "04": {
        "name": "个性化分析",
        "icon": "🎯",
        "desc": "方向特异分析（衰老/发育/肿瘤/纤维化/运动/比例变化）",
        "substeps": [
            {"id": "custom", "name": "个性化分析（根据研究方向定制）", "skill": "custom-analysis"},
        ]
    }
}


def guide_analysis(data_stage: str = "raw", redo: bool = False) -> str:
    """Return available analysis modules."""
    options = []

    # Combo options
    options.append({
        "id": "combo:quick",
        "label": "⚡ 快速组合 (基础分析)",
        "description": "02 基础分析 — 适合快速查看数据概况"
    })
    options.append({
        "id": "combo:standard",
        "label": "🔍 标准组合 (基础+高级)",
        "description": "02 基础 + 03 高级 — 推荐的标准分析流程"
    })

    # Individual modules
    for mid, minfo in MODULES.items():
        options.append({
            "id": f"module:{mid}",
            "label": f"{minfo['icon']} {minfo['name']}",
            "description": minfo['desc']
        })

    options.append({
        "id": "custom",
        "label": "✏️ 自定义输入",
        "description": "输入你想做的分析（如：基础分析，高级分析）"
    })

    return json.dumps({
        "data_stage": data_stage,
        "redo": redo,
        "modules": MODULES,
        "options": options,
        "message": "请选择要执行的分析模块："
    }, ensure_ascii=False, indent=2)


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="guide_analysis",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: guide_analysis(
                args.get("data_stage", "raw"),
                args.get("redo", False)
            ),
            emoji="📋",
            max_result_size_chars=20_000,
        )
    except ImportError:
        pass

try:
    _register()
except Exception:
    pass
