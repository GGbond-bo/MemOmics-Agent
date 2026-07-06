"""
MemOmics Analysis Pipeline — 4-stage module selection -> todo -> skill -> rail review.
"""
import json, os, re, traceback
from typing import Any, Dict, List, Optional

MODULES = {
    "01": {"id": "01", "name": "深度去污染", "description": "CellBender/SoupX/DoubletFinder", "skills": ["scrna-qc", "cellbender-remove-background"], "note": "探索性分析不建议"},
    "02": {"id": "02", "name": "基础分析", "description": "QC->SCTransform->Harmony->UMAP->Leiden->Annotation->Markers", "skills": ["scrna-clustering", "annotate_celltype_scRNA"], "substeps": [
        {"id": "qc", "name": "QC", "skill": "scrna-qc"},
        {"id": "sct", "name": "SCTransform", "skill": "scrna-clustering"},
        {"id": "harmony", "name": "Harmony", "skill": "create_harmony_embeddings_scRNA"},
        {"id": "umap", "name": "UMAP", "skill": "scrna-clustering"},
        {"id": "cluster", "name": "Leiden", "skill": "scrna-clustering"},
        {"id": "annotate", "name": "Annotation", "skill": "annotate_celltype_scRNA"},
        {"id": "markers", "name": "Markers", "skill": "deg-analysis"},
    ]},
    "03": {"id": "03", "name": "高级分析", "description": "DEG+Enrichment / CellChat / Trajectory / SCENIC", "items": [
        {"id": "deg", "name": "DEG+富集", "skills": ["deg-analysis", "functional-enrichment"]},
        {"id": "cellchat", "name": "CellChat通讯", "skills": ["cellchat-v2"]},
        {"id": "trajectory", "name": "轨迹分析", "skills": ["trajectory-analysis"]},
        {"id": "scenic", "name": "SCENIC调控", "skills": ["grn-pyscenic"]},
    ]},
    "04": {"id": "04", "name": "个性化分析", "description": "按研究方向定制", "skills": ["sasp-scoring", "immune-deconvolution"]},
}

COMBOS = {
    "quick": {"name": "快速组合", "modules": ["02"], "description": "仅基础分析"},
    "standard": {"name": "标准组合(推荐)", "modules": ["02", "03"], "description": "基础+高级"},
}

DIRECTION_MAP = {
    "aging": ["衰老", "aging", "aged", "老年", "elderly", "senescence"],
    "cancer": ["肿瘤", "cancer", "tumor", "癌"],
    "neurodegeneration": ["神经", "neuro", "AD", "ALS", "FSHD", "Alzheimer"],
    "fibrosis": ["纤维化", "fibrosis"],
    "immunology": ["免疫", "immune", "inflammation"],
    "development": ["发育", "development", "embryo"],
    "metabolism": ["代谢", "metabolic", "diabetes"],
    "cardiovascular": ["心脏", "cardiac", "heart"],
    "hepatology": ["肝脏", "liver", "hepatic"],
    "muscle_biology": ["骨骼肌", "muscle", "skeletal"],
}

SPECIES_MAP = {
    "human": ["human", "homo sapiens", "人", "patient"],
    "mouse": ["mouse", "mus musculus", "小鼠", "老鼠"],
    "zebrafish": ["zebrafish"],
    "rat": ["rat", "rattus"],
}


def extract_direction(user_input: str) -> Dict[str, Any]:
    text = user_input.lower()
    species = "auto"
    for sp, keywords in SPECIES_MAP.items():
        for kw in keywords:
            if kw in text:
                species = sp
                break
        if species != "auto":
            break
    directions = []
    for direction, keywords in DIRECTION_MAP.items():
        for kw in keywords:
            if kw in text:
                directions.append(direction)
                break
    return {"species": species, "directions": directions, "has_direction": len(directions) > 0}


def build_module_options() -> list:
    options = []
    for mid, mod in MODULES.items():
        note = mod.get("note", "")
        desc = mod["description"] + (" (" + note + ")" if note else "")
        options.append({"id": f"module:{mid}", "label": f"{mid} {mod['name']}", "description": desc})
    for cid, combo in COMBOS.items():
        options.append({"id": f"combo:{cid}", "label": combo["name"], "description": combo["description"]})
    return options


def parse_module_selection(raw_input: str) -> List[str]:
    text = raw_input.strip().lower()
    for cid, combo in COMBOS.items():
        if cid in text or combo["name"].lower() in text:
            return combo["modules"]
    modules = []
    kw_map = {
        "01": ["去污染", "cellbender", "soupx", "doublet", "去背景"],
        "02": ["基础", "qc", "聚类", "cluster", "umap", "sctransform", "harmony"],
        "03": ["高级", "deg", "cellchat", "trajectory", "scenic", "monocle"],
        "04": ["个性化", "定制", "custom"],
    }
    for mid, keywords in kw_map.items():
        for kw in keywords:
            if kw in text:
                if mid not in modules:
                    modules.append(mid)
    return sorted(modules) if modules else ["02"]


def modules_to_todos(selected_modules: List[str], direction_info: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    todos = []
    for mid in selected_modules:
        mod = MODULES.get(mid)
        if not mod:
            continue
        if mid == "02" and "substeps" in mod:
            for step in mod["substeps"]:
                todos.append({"id": f"basic_{step['id']}", "title": step["name"], "module": "02", "skill": step.get("skill", ""), "status": "pending"})
        elif mid == "03" and "items" in mod:
            for item in mod["items"]:
                todos.append({"id": f"advanced_{item['id']}", "title": item["name"], "module": "03", "skills": item.get("skills", []), "status": "pending"})
        elif mid == "01":
            todos.append({"id": "decontamination", "title": "Decontamination", "module": "01", "skills": mod.get("skills", []), "status": "pending"})
        elif mid == "04":
            d = (direction_info or {}).get("directions", [])
            todos.append({"id": "personalized", "title": f"Personalized ({'/'.join(d) if d else 'custom'})", "module": "04", "skills": mod.get("skills", []), "status": "pending"})
    return todos


def get_module_summary(selected_modules: List[str]) -> str:
    lines = []
    for mid in sorted(selected_modules):
        mod = MODULES.get(mid, {})
        lines.append(f"**{mid} {mod.get('name', mid)}**: {mod.get('description', '')}")
    if "03" in selected_modules:
        lines.append("\n高级分析包含: DEG+Enrichment, CellChat, Trajectory, SCENIC")
    return "\n".join(lines)


def memomics_pipeline(action: str = "parse", user_input: str = "", selected_modules: list = None, direction_info: dict = None) -> str:
    """返回 JSON string（非 dict），避免 DeepSeek API 400 content-type error。"""
    try:
        if action == "parse":
            direction = extract_direction(user_input) if user_input else {}
            options = build_module_options()
            return json.dumps({"success": True, "direction": direction, "module_options": options}, ensure_ascii=False, indent=2)
        elif action == "todos":
            if not selected_modules:
                return json.dumps({"success": False, "error": "selected_modules required"}, ensure_ascii=False)
            todos = modules_to_todos(selected_modules, direction_info or {})
            summary = get_module_summary(selected_modules)
            return json.dumps({"success": True, "todos": todos, "summary": summary, "total_todos": len(todos)}, ensure_ascii=False, indent=2)
        elif action == "summary":
            if not selected_modules:
                return json.dumps({"success": False, "error": "selected_modules required"}, ensure_ascii=False)
            return json.dumps({"success": True, "summary": get_module_summary(selected_modules)}, ensure_ascii=False, indent=2)
        return json.dumps({"success": False, "error": f"Unknown action: {action}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


TOOL_SCHEMA = {
    "name": "memomics_pipeline",
    "description": "MemOmics pipeline: extract species/tissue/direction, show 4-stage modules, generate todo list with skill bindings.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["parse", "todos", "summary"], "description": "parse=extract direction+modules, todos=generate task list, summary=describe modules"},
            "user_input": {"type": "string", "description": "User raw message (for parse)"},
            "selected_modules": {"type": "array", "items": {"type": "string"}, "description": "Module IDs like ['02','03'] (for todos)"},
            "direction_info": {"type": "object", "description": "Pre-extracted direction (for todos)"},
        },
        "required": ["action"],
    },
}