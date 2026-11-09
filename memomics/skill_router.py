# -*- coding: utf-8 -*-
"""Skill 检索路由：把 SKILLS_INDEX.md 变成可检索的候选来源。

为什么需要这个模块（2026-11-06）：
    技能库涨到 406 条后，「触发」只靠两件事——75 条 RED 的关键词匹配，以及
    模型自己读 72KB 索引后自觉调用。实测三类断点：
      1. 提示词教模型调 skill_search，但该工具在运行时从未注册（幻影工具）；
      2. 触发词按作者口径写：「差异分析」命中、「差异表达分析」漏；
      3. 318 条 YEL + 13 条 GRN 完全没有自动入口。
    本模块提供统一的候选检索（名称 / 触发词 / 使用场景 + 中英术语桥），
    同时给 hermes 工具（skill_search）和 webui 的候选注入使用，保证两边
    打分口径一致、不会各写一套。

检索口径：
    · 英文按词、中文按 2-gram 切分，命中名称 > 触发词 > 使用场景；
    · 用 idf 压低「分析 / 数据」这类到处都有的水词；
    · 中文说法先过术语桥（细胞类型→celltype、差异表达→differential expression）
      再匹配英文行——索引里大量技能的描述是纯英文，没有这层就永远 0 命中；
    · 索引 mtime 变化时自动重建缓存（技能增删/改触发词后不必重启进程）。
"""
from __future__ import annotations

import math
import os
import re
import threading

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 字段权重：名称最硬，触发词次之，使用场景是软证据
_W_NAME = 6.0
_W_KW = 4.0
_W_USAGE = 2.0
_RED_BONUS = 0.5  # 同等命中时 RED 略优先，但不改变「候选不是强制」的判定纪律

_HEADER_CELLS = {"#", "icon", "level", "info", "skill", "编号", "red", "yel", "grn", "wht"}

# 中英术语桥：中文说法 → 英文/缩写 token。只收生信用户真实会说、且索引里
# 常用英文表述的领域词；长词优先（细胞类型注释 先于 注释）。
_ZH_EN = {
    "细胞类型注释": ["celltype", "cell type", "annotat"],
    "层级注释": ["hierarch", "annotation", "rollup"],
    "层级回填": ["rollup", "backfill", "hierarch"],
    "注释回填": ["rollup", "backfill", "annotation"],
    "层级": ["hierarch", "level"],
    "合并": ["merge", "rollup", "combine"],
    "回填": ["rollup", "backfill"],
    "细胞类型": ["celltype", "cell type"],
    "细胞通讯": ["cell communication", "cellchat", "ligand", "receptor"],
    "配体受体": ["ligand", "receptor"],
    "差异表达": ["differential expression", "deg"],
    "差异分析": ["differential", "deg"],
    "差异基因": ["deg", "differential"],
    "批次效应": ["batch", "harmony"],
    "批次校正": ["batch", "harmony"],
    "去批次": ["batch", "harmony"],
    "降维聚类": ["cluster", "umap", "tsne", "dimension"],
    "聚类": ["cluster"],
    "降维": ["dimension", "umap", "tsne", "pca"],
    "拟时序": ["pseudotime", "trajectory"],
    "轨迹推断": ["trajectory", "pseudotime"],
    "功能富集": ["enrichment", "gsea", "ora"],
    "富集": ["enrichment", "gsea", "ora"],
    "通路": ["pathway"],
    "质控": ["qc", "quality"],
    "双细胞": ["doublet"],
    "环境rna": ["ambient"],
    "线粒体": ["mitochondri"],
    "单细胞": ["single-cell", "scrna"],
    "空间转录": ["spatial"],
    "多组学": ["multi-omics", "multiomics"],
    "基因组": ["genome"],
    "表观遗传": ["epigen"],
    "甲基化": ["methylation"],
    "可变剪接": ["splicing"],
    "拷贝数": ["copy number", "cnv"],
    "融合基因": ["fusion"],
    "变异": ["variant", "mutation"],
    "免疫浸润": ["immune infiltration", "deconvolution"],
    "细胞比例": ["proportion", "composition"],
    "细胞周期": ["cell cycle"],
    "转录因子": ["transcription factor"],
    "调控网络": ["regulatory network", "network"],
    "蛋白互作": ["protein interaction", "interaction"],
    "信号通路": ["signaling", "pathway"],
    "药物靶点": ["drug", "target"],
    "分子对接": ["docking"],
    "虚拟筛选": ["screening"],
    "序列比对": ["alignment", "blast"],
    "引物设计": ["primer"],
    "质粒": ["plasmid"],
    "基因编辑": ["crispr", "editing"],
    "敲除": ["knockout"],
    "流式细胞": ["flow cytometry"],
    "免疫荧光": ["immunofluorescence", "imaging"],
    "成像": ["imaging", "microscopy"],
    "代谢组": ["metabolom"],
    "微生物组": ["microbiom"],
    "衰老": ["aging", "senescence"],
    "示例组织": ["skeletal muscle", "muscle"],
    "糖尿病": ["diabetes"],
    "炎症": ["inflammat"],
    "纤维化": ["fibrosis"],
    "统计方法": ["statistic"],
    "生存分析": ["survival"],
    "样本量": ["sample size", "power"],
    "实验设计": ["experimental design"],
    "可视化": ["visual", "plot", "figure"],
    "作图": ["figure", "plot"],
    "出图": ["figure", "plot"],
    "配色": ["palette", "color"],
    "排版": ["layout"],
    "字体": ["font"],
    "表格": ["table"],
    "插图": ["illustration", "figure"],
    "海报": ["poster"],
    "演示文稿": ["presentation", "slide", "ppt"],
    "简历": ["resume", "cv"],
    "论文润色": ["polish", "manuscript"],
    "润色": ["polish"],
    "审稿": ["review", "referee"],
    "修回": ["response", "rebuttal"],
    "综述": ["review", "literature"],
    "文献": ["paper", "literature"],
    "翻译": ["translat"],
    "拆解": ["card", "decompose"],
    "基金申请": ["grant", "proposal", "funding"],
    "标书": ["proposal", "grant"],
    "开题": ["proposal"],
    "投稿": ["submit", "submission"],
    "专利": ["patent"],
    "报告": ["report"],
    "代码审查": ["code review", "lint"],
    "调试": ["debug"],
    "部署": ["deploy"],
    "集群": ["cluster", "slurm", "ssh"],
    "云端": ["cloud"],
    "投递": ["submit", "job"],
    "数据下载": ["download"],
    "知识库": ["knowledge base"],
    "记忆": ["memory"],
    "技能": ["skill"],
    # —— 常见实验/平台术语（纯英文技能行靠这些桥接）——
    "峰": ["peak"],
    "基序": ["motif"],
    "染色质": ["chromatin", "atac", "chip"],
    "免疫共沉淀": ["chip", "immunoprecipitation"],
    "显微ct": ["microct", "morphometry"],
    "形态计量": ["morphometry"],
    "纤毛": ["ciliar"],
    "二级结构": ["secondary structure"],
    "必需基因": ["essentiality"],
    "几何": ["geometry"],
    "主动脉": ["aortic", "aorta"],
    "骨": ["bone"],
    "筛选": ["screen"],
    "调控元件": ["ccre", "regulatory element"],
    "启动子": ["promoter"],
    "增强子": ["enhancer"],
    "整合": ["integration", "harmony"],
    "变异调用": ["variant calling"],
    "结构预测": ["structure prediction", "alphafold"],
    "蛋白语言模型": ["protein language model", "esm"],
    "基因嵌入": ["embedding"],
    "细胞分割": ["segmentation"],
    "图像配准": ["registration"],
    "细胞运动": ["motility"],
    "质谱": ["mass spectrometry"],
    "单核转录": ["snrna", "single nucleus"],
    "多组学整合": ["multiome", "multi-omics"],
    "批量测序": ["bulk"],
    "细胞通讯分析": ["cell communication", "cellchat"],
    "基因集": ["gene set"],
    "过表达分析": ["over-representation", "ora"],
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_RE = re.compile(r"[a-z0-9][a-z0-9+#._\-]*")
_STOP_TOKENS = {"the", "and", "for", "with", "you", "need", "use", "when", "this", "that",
                "are", "分析", "数据", "使用", "适用", "需要", "一个", "可以"}

_lock = threading.Lock()
_cache = {"key": None, "rows": [], "df": {}, "n": 0}


def index_path() -> str:
    """索引路径：跟 MemOmics 的 MEMOMICS_HOME 走（server 启动时会设）。"""
    home = os.environ.get("MEMOMICS_HOME") or os.path.join(_REPO_ROOT, "memomics_home")
    return os.path.join(home, "SKILLS_INDEX.md")


def _parse_rows(text: str) -> list:
    """解析索引表格行 → [{name, usage, keywords, level}]（兼容编号/无编号两种格式）。"""
    rows = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[0].isdigit():
            num, name, usage, kw, level = cells
        elif len(cells) == 4:
            name, usage, kw, level = cells
        else:
            continue
        if not name or name.lower() in _HEADER_CELLS or set(name) <= set("-"):
            continue
        rows.append({"name": name, "usage": usage, "keywords": kw, "level": level})
    return rows


def _cjk_tokens(run: str) -> set:
    if len(run) == 1:
        return {run}
    return {run[i:i + 2] for i in range(len(run) - 1)}


def _tokens(text: str) -> set:
    """英文按词、中文按 2-gram 切分。

    中文不保留单字：单字（用/做/把/的）语义弱，但在一堆英文描述里出现得少，
    idf 反而很高 —— 实测「用 harmony 去批次」被单字「用」顶出一个无关的 batch 技能。
    """
    low = (text or "").lower()
    toks = {w for w in _ASCII_RE.findall(low) if len(w) >= 2}
    for run in _CJK_RE.findall(low):
        if len(run) >= 2:
            toks |= _cjk_tokens(run)
    return {t for t in toks if t not in _STOP_TOKENS}


def _bridge(tokens: set) -> set:
    """中文 token → 领域英文 token（术语桥）；长词优先已在词典按整段匹配。"""
    out = set()
    for zh, ens in _ZH_EN.items():
        zh_toks = _tokens(zh)
        if zh_toks and zh_toks <= tokens:
            for en in ens:
                out |= _tokens(en)
    return out - tokens


def _row_fields(row: dict):
    return (
        (row["name"] or "").lower(),
        (row["keywords"] or "").lower(),
        (row["usage"] or "").lower(),
    )


def _load(index_file: str = None):
    """按 mtime 缓存索引；df 用于 idf。"""
    path = index_file or index_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return [], {}, 0
    key = (path, mtime)
    with _lock:
        if _cache["key"] == key:
            return _cache["rows"], _cache["df"], _cache["n"]
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                rows = _parse_rows(f.read())
        except OSError:
            rows = []
        df = {}
        for row in rows:
            seen = set()
            for field in _row_fields(row):
                seen |= _tokens(field)
            for tok in seen:
                df[tok] = df.get(tok, 0) + 1
        _cache.update({"key": key, "rows": rows, "df": df, "n": len(rows)})
        return rows, df, len(rows)


def _family(name: str) -> str:
    """技能家族键：取名称前两个分片（annotate_celltype_scRNA / annotate_celltype_with_panhumanpy
    同族），用于候选去重，避免同族技能把名额占满、挤掉别的意图。"""
    parts = [p for p in re.split(r"[-_\s]+", (name or "").lower()) if p]
    return "-".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else "")


# 真实用户一句话常包含多个意图（"先做质控，再聚类，最后出图"）。单查询向量会被
# 其中一个意图主导，其余意图连候选都进不去 —— 所以先分句再轮转合并。
_CLAUSE_SPLIT = re.compile(r"[，,；;。\n]+|然后|接着|最后|顺便|另外|同时")


def _clauses(query: str) -> list:
    parts = [p.strip() for p in _CLAUSE_SPLIT.split(query or "") if p and p.strip()]
    return parts if len(parts) > 1 else [query or ""]


def search(query: str, top_k: int = 8, level: str = "", domain: str = "",
           dedupe_family: bool = True, per_family: int = 2,
           multi: bool = True) -> dict:
    """按自然语言查询检索技能，返回候选（含命中理由）。

    Args:
        query: 用户说法（中文/英文均可）
        top_k: 返回条数（1..30）
        level: 只看某级别（RED/YEL/GRN，空=全部）
        domain: 额外领域词过滤（如 "RNA" / "文献"），命中名称或使用场景才保留
    """
    q = (query or "").strip()
    if not q:
        return {"success": False, "error": "query 不能为空",
                "hint": "传入用户需求原话，例如 skill_search(query='差异表达分析')",
                "results": []}
    try:
        top_k = max(1, min(int(top_k or 8), 30))
    except (TypeError, ValueError):
        top_k = 8

    rows, df, n = _load()
    if not rows:
        return {"success": False, "error": "SKILLS_INDEX.md 不存在或为空",
                "hint": "先运行 python -m webui.skills_registry --build 重建索引",
                "results": []}

    q_tokens = _tokens(q)
    expanded = q_tokens | _bridge(q_tokens)
    q_low = q.lower()
    q_tight = re.sub(r"(?<=[0-9a-z])[ \t]+(?=[^\x00-\x7f])|(?<=[^\x00-\x7f])[ \t]+(?=[0-9a-z])", "", q_low)

    # 多意图句：逐句检索后轮转合并，保证每个意图都有候选名额。
    clauses = _clauses(q) if multi else [q]
    if len(clauses) > 1:
        per = max(2, (top_k + len(clauses) - 1) // len(clauses) + 1)
        buckets = [
            search(c, top_k=per, level=level, domain=domain,
                   dedupe_family=dedupe_family, per_family=per_family, multi=False)["results"]
            for c in clauses
        ]
        merged, seen = [], set()
        for rank in range(max(len(b) for b in buckets)):
            for bucket in buckets:
                if rank >= len(bucket):
                    continue
                item = bucket[rank]
                if item["name"] in seen:
                    continue
                seen.add(item["name"])
                merged.append(item)
                if len(merged) >= top_k:
                    break
            if len(merged) >= top_k:
                break
        return {
            "success": True,
            "query": q,
            "clauses": clauses,
            "count": len(merged),
            "total_scored": sum(len(b) for b in buckets),
            "results": merged,
            "hint": ("命中为空时换更具体的领域词；拿到 name 后用 skill_view(name) 加载全文。"
                     if merged else "没有匹配技能：换用领域术语（如 差异表达/细胞通讯/层级注释）再试。"),
        }

    def idf(tok: str) -> float:
        return math.log(1.0 + n / (1.0 + df.get(tok, 0)))

    scored = []
    for idx, row in enumerate(rows):
        if level and level.upper() not in (row["level"] or "").upper():
            continue
        name_l, kw_l, usage_l = _row_fields(row)
        if domain:
            dom = domain.lower()
            if dom not in name_l and dom not in kw_l and dom not in usage_l:
                continue
        score = 0.0
        matched = []
        for tok in expanded:
            w = 0.0
            if tok in name_l:
                w = _W_NAME
            elif tok in kw_l:
                w = _W_KW
            elif tok in usage_l:
                w = _W_USAGE
            if w:
                # 原词命中 > 术语桥命中：桥接是「可能相关」，不能盖过用户原话。
                if tok not in q_tokens:
                    w *= 0.75
                score += w * idf(tok)
                # 只回报能让人看懂的证据：优先回报原始查询词，桥接词标注来源
                matched.append(tok if tok in q_tokens else tok + "(桥)")
        # 整句直配（"差异表达分析" vs "差异表达分析"）额外加权
        if q_low and (q_low in name_l or q_tight and q_tight in name_l):
            score += 12.0
            matched.append("name-exact")
        elif q_tight and (q_tight in kw_l or q_tight in usage_l):
            score += 5.0
            matched.append("phrase")
        if score <= 0:
            continue
        if "RED" in (row["level"] or "").upper():
            score += _RED_BONUS
        scored.append((score, idx, row, matched))

    scored.sort(key=lambda x: (-x[0], x[1]))
    results = []
    fam_count = {}
    for score, _idx, row, matched in scored:
        # 同族去重：annotate_celltype_scRNA / annotate_celltype_with_panhumanpy 这类
        # 同前缀技能最多占 per_family 个名额，否则一句话里的多个意图会被同族挤掉。
        fam = _family(row["name"]) if dedupe_family else ""
        if dedupe_family and fam:
            if fam_count.get(fam, 0) >= max(1, int(per_family or 2)):
                continue
            fam_count[fam] = fam_count.get(fam, 0) + 1
        results.append({
            "name": row["name"],
            "level": (row["level"] or "").split()[0] if row["level"] else "",
            "when_to_use": (row["usage"] or "")[:200],
            "trigger_keywords": (row["keywords"] or "")[:200],
            "matched_on": matched[:8],
            "score": round(score, 2),
        })
        if len(results) >= top_k:
            break
    return {
        "success": True,
        "query": q,
        "count": len(results),
        "total_scored": len(scored),
        "results": results,
        "hint": ("命中为空时换更具体的领域词；拿到 name 后用 skill_view(name) 加载全文。"
                 if results else "没有匹配技能：换用领域术语（如 差异表达/细胞通讯/层级注释）再试。"),
    }


def list_by_domain(domain: str, limit: int = 40) -> dict:
    """按领域词列出技能（替代模型「凭印象猜技能名」）。"""
    dom = (domain or "").strip().lower()
    if not dom:
        return {"success": False, "error": "domain 不能为空",
                "hint": "例如 skill_list_by_domain(domain='RNA')", "skills": []}
    try:
        limit = max(1, min(int(limit or 40), 200))
    except (TypeError, ValueError):
        limit = 40
    rows, _df, _n = _load()
    hits = []
    for row in rows:
        hay = " ".join([row["name"] or "", row["keywords"] or "", row["usage"] or ""]).lower()
        if dom in hay:
            hits.append({"name": row["name"],
                         "level": (row["level"] or "").split()[0] if row["level"] else "",
                         "when_to_use": (row["usage"] or "")[:160]})
    return {"success": True, "domain": domain, "count": len(hits[:limit]),
            "skills": hits[:limit],
            "hint": "用 skill_view(name) 加载完整指令"}


def load_rows() -> list:
    """给 webui 候选注入用的原始行（只读）。"""
    return _load()[0]
