# -*- coding: utf-8 -*-
"""Skill 注册表构建器（使用场景 / 触发词 / 触发级别 单一真源）

背景（2026-09-23 审计）：
    hermes_home/SKILLS_INDEX.md 是唯一会被注入 system prompt、且被
    server._match_red_skill_triggers() 解析做自动触发的技能目录。它原先由
    webui/auto_register.py 的「只追加」逻辑维护，结果：
      · 355 个 skill 里只有 ~273 个有行（82 个 skill 对 agent 完全不可见）
      · 84 行列表格错列（表头 5 列，追加的行只有 4 列）
      · 触发词列回退成分类水词（rna, scrna, scrnaseq）→ 一句「scRNA-seq 数据做质控」
        能同时命中 19 个 RED skill
      · 23 行描述是垃圾（> / >-）、64 行触发词为空、15 行重复
    本模块从 SKILL.md frontmatter + 正文 + skill.json + SOUL.md 必触发表重新生成
    整份索引，并回填 skill.json 缺失字段，保证 WebUI / 索引 / 自动触发同一份数据。

用法：
    python -m webui.skills_registry --report                    # 只报告
    python -m webui.skills_registry --build                     # 重建 SKILLS_INDEX.md
    python -m webui.skills_registry --build --backfill-json     # 同时补 skill.json
    python -m webui.skills_registry --check                     # 一致性检查 exit 2
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

BT = chr(96)      # 反引号（写成 chr 便于本文件被各种工具安全处理）
DQ = chr(34)      # 双引号
SQ = chr(39)      # 单引号

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
HERMES_HOME = os.environ.get("HERMES_HOME") or os.path.join(_ROOT, "hermes_home")
SKILLS_DIR = os.path.join(HERMES_HOME, "skills")
INDEX_PATH = os.path.join(HERMES_HOME, "SKILLS_INDEX.md")
SOUL_PATH = os.path.join(HERMES_HOME, "SOUL.md")

# 分类分节（保持既有 15 节顺序与标题，本次不改分类体系）
SECTIONS = [
    ("01_RNA", "01_RNA - 单细胞转录组"),
    ("02_ATAC", "02_ATAC - ATAC/染色质"),
    ("03_空间组", "03_空间组 - 空间转录组"),
    ("04_Bulk", "04_Bulk - Bulk/表观"),
    ("05_蛋白", "05_蛋白 - 蛋白/免疫"),
    ("06_微生物植物", "06_微生物植物 - 微生物/植物"),
    ("07_药物临床", "07_药物临床 - 药物/临床"),
    ("08_报告", "08_报告 - 报告/可视化"),
    ("09_内置", "09_内置 - Hermes系统"),
    ("10_多组学整合", "10_多组学整合 - 多组学整合"),
    ("11_文献搜索", "11_文献搜索 - 文献/数据库"),
    ("12_分子生物学", "12_分子生物学 - 分子克隆"),
    ("13_组织学病理", "13_组织学病理 - 组织学/病理"),
    ("14_细胞生物学实验", "14_细胞生物学实验 - 细胞生物学"),
    ("15_CRISPR基因编辑", "15_CRISPR基因编辑 - CRISPR"),
]
SECTION_TITLES = dict(SECTIONS)
SECTION_ORDER = [k for k, _ in SECTIONS]
DEFAULT_SECTION = "08_报告"

CATEGORY_TO_SECTION = {
    "transcriptomics": "01_RNA", "scrna": "01_RNA", "rna": "01_RNA",
    "epigenomics": "02_ATAC", "atac": "02_ATAC",
    "spatial": "03_空间组",
    "bulk": "04_Bulk", "epigenetics": "04_Bulk",
    "proteomics": "05_蛋白", "protein": "05_蛋白",
    "microbiology": "06_微生物植物", "plant": "06_微生物植物",
    "drug_discovery": "07_药物临床", "clinical": "07_药物临床",
    "visualization": "08_报告", "report": "08_报告", "general": "08_报告",
    "system": "09_内置",
    "multi_omics": "10_多组学整合",
    "literature": "11_文献搜索", "data_retrieval": "11_文献搜索",
    "molecular_biology": "12_分子生物学",
    "histology": "13_组织学病理",
    "cell_biology": "14_细胞生物学实验",
    "genome_editing": "15_CRISPR基因编辑",
}

# 分类水词：作为触发词没有区分度（旧版把它们写进触发词列，导致一触一大片）
BOILERPLATE = {
    "rna", "scrna", "scrnaseq", "sc-rna", "single cell", "single-cell",
    "atac", "atacseq", "chipseq", "chip-seq", "spatial", "bulk", "protein",
    "proteomics", "figure", "report", "literature", "system", "analysis",
    "data", "omics", "bioinformatics", "生信", "分析", "数据", "报告", "文献",
    "论文", "图", "可视化", "工具", "技能", "skill",
}
# 通用动词/语气词：做子串匹配会误触发
GENERIC_STOP = {
    "帮我", "一下", "这个", "那个", "我的", "你的", "怎么", "什么", "可以",
    "help", "please", "the", "and", "for", "with", "use", "used", "using",
    "python", "r",
}
# 名称分词时丢弃的动词/虚词
NAME_TOKEN_STOP = {
    "analyze", "analysis", "create", "generate", "build", "compute", "calculate",
    "perform", "run", "make", "plot", "check", "list", "query", "get", "fetch",
    "with", "from", "into", "using", "based", "out", "and", "for", "the",
}
MIN_KW_LEN, MAX_KW_LEN, MAX_KW = 2, 24, 16   # 人工写满（如 nature 七件套各 15 条）时不截断
MAX_USAGE_CHARS = 120          # 索引里每行的使用场景上限（全文仍在 SKILL.md / skill.json）
PLACEHOLDER_RE = re.compile(r"需使用\s*[^，。]{0,30}功能[，,]?\s*适用于相关生信分析场景")
JUNK_USAGE = {"", ">", ">-", "--", "n/a", "none", "todo", "-"}

FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
USAGE_HEAD_RE = re.compile(
    r"^#{1,4}\s*(使用场景|适用场景|何时使用|什么时候用|应用场景|When to use|When To Use|Use when)\s*[:：]?\s*$",
    re.M | re.I)
USAGE_INLINE_RE = re.compile(
    r"(?:使用场景|适用场景|何时使用|应用场景|When to use)\s*[:：]\s*([^\n]{4,240})", re.I)
KW_INLINE_RE = re.compile(
    r"(?:触发词|触发关键词|trigger_keywords|Trigger keywords|Triggers)\s*[:：]\s*([^\n]{2,300})", re.I)
HEAD_RE = re.compile(r"^#{1,4}\s", re.M)


def _clean(text) -> str:
    """压缩空白 + 去 markdown 强调符（表格单元格不能有换行和竖线）。"""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    t = t.strip("*_ ")
    t = t.replace(BT, "").replace("|", "/").replace("：", ":").strip()
    return t.rstrip("，,;；、/").strip()


def _is_junk_usage(t) -> bool:
    t = _clean(t)
    return (t.lower() in JUNK_USAGE) or len(t) < 6 or bool(PLACEHOLDER_RE.search(t))


def _clip(text, limit: int = MAX_USAGE_CHARS) -> str:
    t = _clean(text)
    if len(t) <= limit:
        return t
    cut = t[:limit]
    for sep in ("。", "；", ";", ". ", "，", ","):
        i = cut.rfind(sep)
        if i >= limit // 2:
            return cut[:i].rstrip("，,;；") + "…"
    return cut.rstrip() + "…"


def _parse_frontmatter(md_text: str) -> dict:
    """解析 SKILL.md 的 YAML frontmatter（不依赖 pyyaml，兼容列表与字符串）。"""
    m = FM_RE.match(md_text or "")
    if not m:
        return {}
    meta, list_key = {}, None
    for raw in m.group(1).split("\n"):
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if re.match(r"^\s*[-*]\s+", line) and list_key:
            meta.setdefault(list_key, [])
            if isinstance(meta[list_key], list):
                meta[list_key].append(_clean(re.sub(r"^\s*[-*]\s+", "", line)).strip(SQ + DQ))
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        list_key = key
        if val == "":
            meta[key] = []
        elif val.startswith("[") and val.endswith("]"):
            meta[key] = [_clean(v).strip(SQ + DQ) for v in val[1:-1].split(",") if v.strip()]
        else:
            meta[key] = _clean(val).strip(SQ + DQ)
    return meta


def _split_keywords(raw) -> list:
    """把各种写法的触发词拆成列表，过滤水词/超长词/重复项/格式噪音。"""
    items, seen = [], set()
    if isinstance(raw, (list, tuple)):
        chunks = [str(x) for x in raw]
    else:
        chunks = re.split(r"[、,，;；|/·]+", str(raw or ""))
    for c in chunks:
        for part in re.split(r"\s{2,}", c):
            k = _clean(part).strip(SQ + DQ + "“”「」（）()*-· :")
            k = re.sub(r"^(?:key\w*|keywords?|trigger\w*|tags?)\s*:\s*", "", k, flags=re.I)
            for ch in ("[", "]", "{", "}"):
                k = k.replace(ch, " ")
            k = k.strip().strip(SQ).strip(DQ).strip(BT).strip(" :")
            if not k:
                continue
            kl = k.lower()
            if len(k) < MIN_KW_LEN or len(k) > MAX_KW_LEN:
                continue
            if kl in BOILERPLATE or kl in GENERIC_STOP:
                continue
            if re.fullmatch(r"[\d.\-+%]+", k):
                continue
            if any(sym in k for sym in ("+", "→", "=", ">", "任何", "推荐", "之类", "等类")):
                continue
            if DQ in k or SQ in k or BT in k:
                continue
            if kl in seen:          # CellBender / cellbender 视为同一个词
                continue
            seen.add(kl)
            items.append(k)
    return items


def _usage_from_body(md_text: str) -> str:
    """正文里找使用场景：先找独立小节，再找行内「使用场景:」。"""
    for m in USAGE_HEAD_RE.finditer(md_text):
        body = md_text[m.end():]
        nxt = HEAD_RE.search(body)
        if nxt:
            body = body[:nxt.start()]
        for line in body.split("\n"):
            line = _clean(re.sub(r"^\s*[-*\d.]+\s*", "", line))
            if len(line) >= 6:
                return line
    m = USAGE_INLINE_RE.search(md_text)
    if m:
        return _clean(m.group(1))
    return ""


def _keywords_from_body(md_text: str) -> list:
    m = KW_INLINE_RE.search(md_text)
    if not m:
        return []
    return _split_keywords(m.group(1))


def _token_keywords(name: str) -> list:
    """把长 snake_case / kebab 名称拆成有信息量的词元当触发词。"""
    toks = [t for t in re.split(r"[-_\s]+", str(name or "").lower())
            if len(t) >= 3 and t not in NAME_TOKEN_STOP and t not in BOILERPLATE]
    return toks[:4]


def _name_keywords(name: str, meta: dict) -> list:
    """从技能名/别名派生触发词（原名 → 空格名 → 名称词元 → 别名）。"""
    out = [name, name.replace("-", " "), name.replace("_", " ")] + _token_keywords(name)
    for k in ("aliases", "alias", "name_zh", "zh_name", "display_name"):
        v = meta.get(k)
        if isinstance(v, (list, tuple)):
            out.extend(str(x) for x in v)
        elif isinstance(v, str) and v.strip():
            out.append(v)
    return _split_keywords(out)


def _strip_name_prefix(text: str, name: str) -> str:
    """去掉描述里的 [skill-name] / skill-name: 前缀噪音。"""
    t = _clean(text)
    if name:
        t = re.sub(r"^\[" + re.escape(name) + r"\]\s*", "", t)
        t = re.sub(r"^" + re.escape(name) + r"\s*[:：—-]\s*", "", t)
    return t.strip()


def extract_usage(md_text: str, meta: dict, sj: dict, name: str = "") -> tuple:
    """使用场景：(文本, 来源)。优先级＝人工填写 > frontmatter > 正文 > 描述 > 首段。"""
    desc = ""
    for v in (sj.get("description"), meta.get("description")):
        if v and not _is_junk_usage(v):
            desc = _strip_name_prefix(v, name)
            break
    for src, val in (("json.when_to_use", sj.get("when_to_use")),
                     ("md.when_to_use", meta.get("when_to_use"))):
        if val and not _is_junk_usage(val):
            t = _strip_name_prefix(val, name)
            # 使用场景过短（如「适用于: 所有scRNA-seq」）时补一句描述，保证路由信号够用
            if len(t) < 30 and desc and desc not in t:
                t = t.rstrip("，,;；:：") + " —— " + desc
            return _clip(t, 200), src
    body = _usage_from_body(md_text)
    if not _is_junk_usage(body):
        return _clip(_strip_name_prefix(body, name), 200), "md.使用场景小节"
    for src, val in (("json.description", sj.get("description")),
                     ("md.description", meta.get("description"))):
        if val and not _is_junk_usage(val):
            return _clip(_strip_name_prefix(val, name), 200), src
    for para in re.split(r"\n\s*\n", md_text or ""):
        p = _clean(re.sub(r"^#{1,4}.*$", "", para, flags=re.M))
        if len(p) >= 20:
            return _clip(_strip_name_prefix(p, name), 200), "md.首段(兜底)"
    return "", "缺失"


def extract_keywords(md_text: str, meta: dict, sj: dict, name: str) -> tuple:
    """触发词：(列表, 来源)。人工填写 > frontmatter > 正文「触发词:」> 名称派生。"""
    trig = meta.get("trigger")
    md_trig = trig.get("when") if isinstance(trig, dict) else None
    for src, raw in (("json.trigger_keywords", sj.get("trigger_keywords")),
                     ("md.trigger_keywords", meta.get("trigger_keywords")),
                     ("md.trigger.when", md_trig)):
        kws = _split_keywords(raw)
        if len(kws) >= 2:
            return kws[:MAX_KW], src
    kws = _keywords_from_body(md_text)
    if len(kws) >= 2:
        return kws[:MAX_KW], "md.触发词行"
    if kws:
        return kws[:MAX_KW], "md.触发词行(少)"
    kws = [k for k in _name_keywords(name, meta) if len(k) >= 3][:6]
    if kws:
        return kws, "名称派生"
    kws = _token_keywords(name)
    if kws:
        return kws, "名称分词"
    return [], "缺失"


def resolve_level(name: str, meta: dict, sj: dict, section: str, soul_red: set) -> tuple:
    """触发级别：SOUL 必触发表（人工口径） > 显式声明 > 系统级内置 > YEL。"""
    if name in soul_red:
        return "RED", "SOUL必触发表"
    for src, val in (("json.trigger_level", sj.get("trigger_level")),
                     ("md.trigger_level", meta.get("trigger_level"))):
        lv = str(val or "").strip().upper()
        if lv in ("RED", "YEL", "GRN", "WHT"):
            return lv, src
    if section == "09_内置":
        return "GRN", "内置技能默认"
    return "YEL", "默认"


def normalize_meta(name: str, data: dict, existing: dict = None) -> dict:
    """把一份 skill.json 元数据规范成索引口径：触发词清洗+限长、使用场景去垃圾、等级与 SOUL 对齐。

    auto_register.auto_generate_skill_json() 会直接从 SKILL.md 搬运 trigger_keywords，
    原文里可能混着逗号粘连的长句、>24 字的英文短语、分类水词；原样写进 skill.json 后，
    索引里就会出现「一格 19 个词」「整句英文当触发词」的脏行，也会把使用场景写成空占位。
    生成 / 回填 skill.json 的任何路径都先过这里，保证「元数据 → 索引」单一口径。

    existing：磁盘上已有的 skill.json。里面已填写且合法的字段优先保留 —— 否则一次
    「补全/重生成」就会把已经定好的触发词换成 SKILL.md 里的另一套写法，索引随之漂移
    （用户视角就是「同一句话昨天命中、今天不命中」）。
    """
    out = dict(data or {})
    if isinstance(existing, dict):
        old_kw = _split_keywords(existing.get("trigger_keywords"))
        if old_kw:
            out["trigger_keywords"] = old_kw[:MAX_KW]
        old_u = _clip(_strip_name_prefix(_clean(existing.get("when_to_use") or ""), name), 200)
        if old_u and not _is_junk_usage(old_u):
            out["when_to_use"] = old_u
        old_lv = str(existing.get("trigger_level") or "").upper()
        if old_lv in ("RED", "YEL", "GRN", "WHT"):
            out["trigger_level"] = old_lv
    kws = _split_keywords(out.get("trigger_keywords"))[:MAX_KW]
    if kws:
        out["trigger_keywords"] = kws
    usage = _clip(_strip_name_prefix(_clean(out.get("when_to_use") or ""), name), 200)
    if _is_junk_usage(usage):
        desc = _clip(_strip_name_prefix(_clean(out.get("description") or ""), name), 200)
        usage = "" if _is_junk_usage(desc) else desc
    if usage:
        out["when_to_use"] = usage
    if name and name in _read_soul_red():
        # SOUL.md 必触发表是人工口径，自动生成时不能被 SKILL.md 的低级别覆盖（例：grill-me）
        out["trigger_level"] = "RED"
    return out


def _section_from_text(*chunks) -> str:
    """按名称/描述里的领域词猜分节（只给索引里还没有的新技能用）。"""
    text = " ".join(str(c or "") for c in chunks).lower()
    rules = [
        ("02_ATAC", ("atac", "archr", "signac", "chip-seq", "chipseq", "chromatin", "染色质", "homer")),
        ("03_空间组", ("spatial", "visium", "merfish", "squidpy", "空间转录")),
        ("04_Bulk", ("bulk", "deseq2", "edger", "limma", "rnaseq", "rna-seq", "表观")),
        ("05_蛋白", ("protein", "proteom", "secretome", "mass spec", "蛋白")),
        ("06_微生物植物", ("microb", "bacteri", "fung", "plant", "植物", "微生物")),
        ("07_药物临床", ("drug", "docking", "admet", "clinical", "survival", "药物", "临床", "预后")),
        ("10_多组学整合", ("multi-omic", "multiomic", "多组学", "mofa", "integration")),
        ("11_文献搜索", ("literature", "paper", "pubmed", "query", "database", "文献", "检索", "下载")),
        ("12_分子生物学", ("clone", "cloning", "primer", "plasmid", "pcr", "blast", "克隆", "引物")),
        ("13_组织学病理", ("histolog", "patholog", "ihc", "组织学", "病理", "免疫组化")),
        ("14_细胞生物学实验", ("cell culture", "viability", "细胞培养", "细胞实验")),
        ("15_CRISPR基因编辑", ("crispr", "cas9", "guide rna", "基因编辑")),
        ("09_内置", ("hermes", "agent", "memory", "系统级")),
        ("01_RNA", ("scrnaseq", "scrna", "seurat", "scanpy", "single-cell", "单细胞", "trajectory", "轨迹")),
        ("08_报告", ("figure", "plot", "visual", "report", "html", "ppt", "docx", "画图", "出图", "报告", "可视化")),
    ]
    for sec, keys in rules:
        if any(k in text for k in keys):
            return sec
    return DEFAULT_SECTION


def _read_soul_red() -> dict:
    """SOUL.md 必触发表 -> {skill: [触发词]}（人工优先级最高，索引 RED 要与它对齐）。

    表格形如：| "心跳" / "监控" / "heartbeat" | skill_view("heartbeat-monitor") | ...
    第一列就是人工写好的用户口径触发词，正好补上 skill.json 里没填的那些技能。
    """
    out = {}
    try:
        with open(SOUL_PATH, encoding="utf-8") as f:
            soul = f.read()
    except OSError:
        return out
    start = soul.find("### 必触发列表")
    end = soul.find("### ⛔ 取消/停止命令处理", start + 1)
    block = soul[start:end if end > 0 else len(soul)] if start >= 0 else soul
    for line in block.split("\n"):
        if not line.startswith("|") or "skill_view(" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        m = re.search(r'skill_view\("([^"]+)"\)', cells[1])
        if not m:
            continue
        kws = _split_keywords(cells[0].replace(DQ, ""))
        cur = out.setdefault(m.group(1), [])
        for k in kws:
            if k not in cur:
                cur.append(k)
    return out


def _existing_sections() -> dict:
    """读旧索引，记录每个技能原有分节（不搬家，保证 diff 可读）。"""
    out = {}
    try:
        with open(INDEX_PATH, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return out
    cur = None
    for line in text.split("\n"):
        if line.startswith("## "):
            m = re.match(r"##\s+(\S+)", line)
            if m and m.group(1) in SECTION_TITLES:
                cur = m.group(1)
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("#", "Skill", "icon"):
            continue
        name = _clean(cells[1] if cells[0].isdigit() else cells[0])
        if name and cur:
            out[name] = cur
    return out


def scan_skills() -> list:
    """扫描 skills/ 下全部已注册技能，返回注册表条目（按分节 + 名称排序）。"""
    soul_map = _read_soul_red()
    soul_red = set(soul_map)
    existing = _existing_sections()
    entries = []
    for root, dirs, files in os.walk(SKILLS_DIR):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        # 只收已注册技能（有 skill.json），与 GET /api/skills/catalog 的 355 个一致；
        # Hermes 框架自带的「只有 SKILL.md」技能不进索引，避免污染触发面。
        if "skill.json" not in files:
            continue
        name = os.path.basename(root)
        md_path = os.path.join(root, "SKILL.md")
        md_text = ""
        if os.path.isfile(md_path):
            with open(md_path, encoding="utf-8", errors="replace") as f:
                md_text = f.read()
        sj = {}
        sj_path = os.path.join(root, "skill.json")
        try:
            with open(sj_path, encoding="utf-8") as f:
                sj = json.load(f) or {}
        except (OSError, ValueError):
            sj = {}
        meta = _parse_frontmatter(md_text)
        section = existing.get(name)
        if not section:
            section = CATEGORY_TO_SECTION.get(str(sj.get("category") or "").strip().lower())
        if not section:
            section = _section_from_text(name, sj.get("description"), meta.get("description"),
                                         meta.get("when_to_use"), md_text[:400])
        level, level_src = resolve_level(name, meta, sj, section, soul_red)
        usage, usage_src = extract_usage(md_text, meta, sj, name)
        kws, kw_src = extract_keywords(md_text, meta, sj, name)
        if soul_map.get(name):
            # SOUL 必触发表里人工写好的用户口径触发词最贴近真实说法，排在前面
            have = []
            for k in list(soul_map[name]) + list(kws):
                if k not in have:
                    have.append(k)
            if have != kws:
                kw_src = (kw_src + "+SOUL必触发表") if kws else "SOUL必触发表"
            kws = have[:MAX_KW]
        entries.append({
            "name": name, "section": section, "usage": usage, "usage_src": usage_src,
            "keywords": kws, "kw_src": kw_src, "level": level, "level_src": level_src,
            "has_md": bool(md_text), "dir": root,
        })
    order = {sec: i for i, sec in enumerate(SECTION_ORDER)}
    entries.sort(key=lambda e: (order.get(e["section"], 99), e["name"].lower()))
    return entries


LEVEL_LABEL = {"RED": "RED 必触发", "YEL": "YEL 讨论触发", "GRN": "GRN 按需触发", "WHT": "WHT 系统级"}


def render_index(entries: list) -> str:
    """渲染 SKILLS_INDEX.md（统一 5 列：编号 | Skill | 使用场景 | 触发词 | Trigger）。"""
    by_sec = {}
    for e in entries:
        by_sec.setdefault(e["section"], []).append(e)
    out = [
        "# MemOmics SKILLS_INDEX",
        "",
        "> LLM startup ephemeral prompt — 由 webui/skills_registry.py 自动生成，请勿手改",
        "> 手改会在下次重建时丢失；要改触发场景请改 SKILL.md frontmatter 或 skill.json",
        "",
        "| icon | level | info |",
        "|---|---|---|",
        "| RED | 必触发 | user mentions -> skill_view immediately |",
        "| YEL | 讨论触发 | confirm plan first then trigger |",
        "| GRN | 按需触发 | only on explicit mention |",
        "| WHT | 系统级 | Hermes internal |",
        "",
        "> 「触发词」列会被 server._match_red_skill_triggers() 用于消息级自动匹配（RED 行），",
        "> 只写有区分度的词，不要写 rna/scrna 这类分类水词。",
        "",
        "---",
        "",
    ]
    for sec in SECTION_ORDER:
        items = by_sec.get(sec, [])
        if not items:
            continue
        out.append("## %s (%d skills)" % (SECTION_TITLES[sec], len(items)))
        out.append("")
        out.append("| # | Skill | 使用场景 | 触发词 | Trigger |")
        out.append("|---|---|---|---|---|")
        for i, e in enumerate(items, 1):
            kw = ", ".join(e["keywords"]) if e["keywords"] else "-"
            usage = e["usage"] or "-"
            out.append("| %d | %s | %s | %s | %s |" % (i, e["name"], usage, kw, LEVEL_LABEL[e["level"]]))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _write_json_backfill(entries: list) -> int:
    """把使用场景/触发词/级别回填 skill.json（只补空字段，不覆盖人工填写值）。"""
    changed = 0
    for e in entries:
        p = os.path.join(e["dir"], "skill.json")
        if not e["has_md"] and not os.path.isfile(p):
            continue
        data = {}
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f) or {}
            except (OSError, ValueError):
                continue
        dirty = False
        if e["usage"] and _is_junk_usage(data.get("when_to_use") or ""):
            data["when_to_use"] = e["usage"]
            dirty = True
        if e["keywords"] and not _split_keywords(data.get("trigger_keywords")):
            data["trigger_keywords"] = e["keywords"]
            dirty = True
        cur_lv = str(data.get("trigger_level") or "").upper()
        if cur_lv not in ("RED", "YEL", "GRN", "WHT"):
            data["trigger_level"] = e["level"]
            dirty = True
        elif e["level"] == "RED" and cur_lv != "RED":
            # SOUL.md 必触发表是人工口径，优先于 skill.json 里手写的低级别
            # （例：grill-me 写 YEL 但 SOUL 要求必触发 → 索引/WebUI 必须都显示 RED）
            data["trigger_level"] = "RED"
            dirty = True
        if dirty:
            try:
                with open(p, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except OSError:
                continue
            changed += 1
    return changed


def report(entries: list, verbose: bool = True) -> dict:
    from collections import Counter
    sec_counts = Counter(e["section"] for e in entries)
    info = {
        "total": len(entries),
        "sections": {k: sec_counts.get(k, 0) for k in SECTION_ORDER if sec_counts.get(k)},
        "levels": dict(Counter(e["level"] for e in entries)),
        "usage_src": dict(Counter(e["usage_src"] for e in entries)),
        "kw_src": dict(Counter(e["kw_src"] for e in entries)),
        "missing_usage": [e["name"] for e in entries if not e["usage"]],
        "missing_keywords": [e["name"] for e in entries if not e["keywords"]],
        "red_without_keywords": [e["name"] for e in entries if e["level"] == "RED" and not e["keywords"]],
    }
    if verbose:
        print("技能总数: %d" % info["total"])
        print("分节:", json.dumps(info["sections"], ensure_ascii=False))
        print("级别:", json.dumps(info["levels"], ensure_ascii=False))
        print("使用场景来源:", json.dumps(info["usage_src"], ensure_ascii=False))
        print("触发词来源:", json.dumps(info["kw_src"], ensure_ascii=False))
        print("缺使用场景: %d %s" % (len(info["missing_usage"]), info["missing_usage"][:10]))
        print("缺触发词: %d %s" % (len(info["missing_keywords"]), info["missing_keywords"][:10]))
        print("RED 但完全没有触发词: %d %s" % (len(info["red_without_keywords"]), info["red_without_keywords"][:10]))
    return info


def check(entries: list = None) -> list:
    """一致性检查：返回问题列表（空 = 索引与磁盘一致且格式合法）。"""
    entries = entries if entries is not None else scan_skills()
    try:
        with open(INDEX_PATH, encoding="utf-8") as f:
            cur = f.read()
    except OSError:
        return ["SKILLS_INDEX.md 不存在"]
    problems = []
    if cur.strip() != render_index(entries).strip():
        problems.append("SKILLS_INDEX.md 与磁盘不同步（跑 --build 重建）")
    rows, seen, sec, sec_n = 0, set(), None, 0
    for line in cur.split("\n"):
        if line.startswith("## "):
            m = re.match(r"##\s+(\S+).*?\((\d+) skills\)", line)
            if m:
                sec, sec_n, rows = m.group(1), int(m.group(2)), 0
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] in ("#", "icon") or set(cells[0]) <= set("-"):
            continue
        if not cells[0].isdigit():
            problems.append("行格式异常（首列非编号）: %s" % line[:80])
            continue
        rows += 1
        if cells[1] in seen:
            problems.append("重复技能行: %s" % cells[1])
        seen.add(cells[1])
        if not cells[2] or cells[2] in JUNK_USAGE or PLACEHOLDER_RE.search(cells[2]):
            problems.append("使用场景缺失/占位: %s" % cells[1])
        if not cells[3] or cells[3] == "-":
            problems.append("触发词为空: %s" % cells[1])
        if "RED" in cells[4] and cells[3] != "-":
            kws = [k.strip().lower() for k in cells[3].split(",")]
            if kws and all(k in BOILERPLATE for k in kws):
                problems.append("RED 行只有分类水词: %s" % cells[1])
        if sec_n and rows > sec_n:
            problems.append("分节 %s 行数超过标题声明" % sec)
    disk = {e["name"] for e in entries}
    problems.extend("索引缺少技能: %s" % n for n in sorted(disk - seen)[:10])
    problems.extend("索引多余技能: %s" % n for n in sorted(seen - disk)[:10])
    return problems


def build(write: bool = True, backfill_json: bool = False) -> dict:
    """重建 SKILLS_INDEX.md。

    顺序很关键：必须「先回填 skill.json，再重新扫描渲染」。
    渲染时 skill.json 的 when_to_use/trigger_keywords 优先级高于 SKILL.md，
    若先渲染再回填，写出的索引会立刻落后于磁盘（渲染结果与文件不一致），
    表现为 build 之后 check 依然报「不同步」、且不收敛。
    """
    info = {}
    if backfill_json:
        n = _write_json_backfill(scan_skills())
        print("已回填 skill.json: %d 个" % n)
        info["json_backfilled"] = n
    entries = scan_skills()
    text = render_index(entries)
    info.update(report(entries))
    info["index_chars"] = len(text)
    info["index_bytes"] = len(text.encode("utf-8"))
    if write:
        with open(INDEX_PATH, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("已写入 %s (%d 行 / %d 字符)" % (INDEX_PATH, text.count("\n") + 1, len(text)))
    return info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Skill 注册表构建器")
    ap.add_argument("--build", action="store_true", help="重建 SKILLS_INDEX.md")
    ap.add_argument("--report", action="store_true", help="只统计不写文件")
    ap.add_argument("--check", action="store_true", help="一致性检查，不一致 exit 2")
    ap.add_argument("--backfill-json", action="store_true", help="同时回填 skill.json 缺失字段")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出统计")
    args = ap.parse_args(argv)
    if args.check:
        problems = check()
        if problems:
            print("发现问题 %d 条:" % len(problems))
            for p in problems[:40]:
                print("  - " + p)
            return 2
        print("SKILLS_INDEX.md 与磁盘一致，格式合法")
        return 0
    info = build(write=True, backfill_json=args.backfill_json) if args.build else report(scan_skills())
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
