"""
MemOmics 代码级强制执行层
- 拦截 tool_start / tool_complete，自动触发 rail_review / debate_analysis
- 追踪会话状态（skill加载、知识库搜索、审查、辩论）
- 分析级别检测（闲聊 vs 分析）
"""
import os, json, re, time
from datetime import datetime
from pathlib import Path

# === 分析级别判定 ===
ANALYSIS_KEYWORDS = {
    "analysis": [
        "分析", "analysis", "analyze", "QC", "质控", "聚类", "cluster", "降维", "DEG", "差异",
        "CellBender", "cellbender", "去背景", "background", "SoupX", "归一化", "normalize", "SCTransform",
        "轨迹", "trajectory", "拟时序", "pseudotime", "Monocle", "Slingshot",
        "细胞通讯", "CellChat", "cellchat", "转录因子", "SCENIC", "空间转录组", "spatial",
        "富集分析", "GO", "KEGG", "pathway", "生存分析", "survival",
        "整合", "integration", "multi-omics", "多组学", "bulk", "ATAC",
        # 多组学覆盖（2026-08-13 补：代谢/蛋白/微生物/表观也要进辩论门控）
        "代谢", "代谢组", "metabolomics", "metabolite", "脂质", "lipid", "lc-ms", "lcms",
        "质谱", "mass spec", "xcms", "msdial", "蛋白", "蛋白组", "proteomics", "maxquant",
        "dia-nn", "diann", "磷酸化", "phospho", "微生物", "microbiome", "16s",
        "宏基因组", "metagenome", "otu", "asv", "qiime", "甲基化", "methylation",
        "chip-seq", "chipseq", "cut&tag", "cuttag", "dmr", "表观",
        "画图", "可视化", "出图", "画出来", "画个", "热图", "火山图", "小提琴图", "箱线图",
        "umap", "tsne", "pca", "注释", "annotat", "figure", "plot", "chart", "graph", "volcano", "heatmap", "generate", "create", "draw",
        "报告", "report", "html",
        "差异表达", "differential expression", "deg",
        "跑", "执行", "开始", "start",
        "subset", "抽", "取", "子集", "subsample",
    ],
    "statistical": [
        "统计", "statistical", "statistic", "t-test", "ttest", "wilcoxon", "回归", "regression",
        "相关性", "correlation", "p-value", "p value", "显著性", "significant",
    ],
}


def detect_analysis_level(user_message: str) -> str:
    """检测分析级别：chat / lightweight / statistical / analysis"""
    msg_lower = user_message.lower()
    score = 0
    for kw in ANALYSIS_KEYWORDS["analysis"]:
        if kw.lower() in msg_lower:
            score += 2
    for kw in ANALYSIS_KEYWORDS["statistical"]:
        if kw.lower() in msg_lower:
            score += 1
    
    # 有分析关键词 + 执行意图 → analysis（含中文动作词：画/绘/读/跑）
    has_action = any(kw in msg_lower for kw in ["run", "do", "go", "start", "generate", "create", "draw", "plot",
                                                "subset", "exec", "画", "绘", "读", "跑"])
    if score >= 3 or (score >= 2 and has_action):
        return "analysis"
    elif score >= 1:
        return "statistical"
    return "chat"


# === 只读命令豁免（2026-08-14 循环/速度优化）===
# 观察类命令不产出分析结果：不触发 铁律24 record_run 门禁、不要求 rail_review(post)，
# 消除 terminal→record_run→rail_review 的三连开销（实测把单个命令的 API 往返放大 3 倍）。
_READONLY_CMDS = (
    "ls", "dir", "type", "cat", "head", "tail", "wc", "echo", "pwd", "cd",
    "find", "where", "grep", "findstr", "which", "tasklist", "nvidia-smi",
    "get-content", "get-childitem", "get-location", "test", "[ ",
)
_WRITE_SIGNALS = (" > ", ">>", "| tee ", "rm ", "rmdir", "del ", "move ", "copy ", "mkdir",
                  "touch", "sed -i", "saveRDS", "write.csv", "write.table", "ggsave",
                  "pdf(", "png(", "svg(", "open(", "write(")
_READONLY_FORBIDDEN = ("rscript", "python", "pip ", "conda", "curl", "wget", "git clone", "npm", "node ")


def _is_readonly_terminal(cmd: str) -> bool:
    """判断 terminal 命令是否为纯观察（只读）命令。"""
    try:
        _c = (cmd or "").strip().lower()
        if not _c:
            return False
        if any(w in _c for w in _WRITE_SIGNALS):
            return False
        if any(w in _c for w in _READONLY_FORBIDDEN):
            return False
        _first = _c.lstrip()
        for _ro in _READONLY_CMDS:
            if _first == _ro or _first.startswith(_ro + " "):
                return True
        return False
    except Exception:
        return False


# ==================== P2 辩论门控 (2026-08-10) ====================
# 设计依据: docs/debate-core-design.md §5.5 — 全量辩论有害（iMAD, AAAI 2026 Oral）,
# 选择性触发省 92% token 且准确率反升 13.5%。三级门控:
#   L0 跳过 | L1 轻量（单对正反+裁判 或 3采样投票，≈1/4 成本）| L2 完整 8 角色

DEBATE_L0, DEBATE_L1, DEBATE_L2 = 0, 1, 2
DEBATE_LEVEL_NAMES = {0: "L0-跳过", 1: "L1-轻量辩论", 2: "L2-完整辩论"}

# P3(2026-09-22): 意图确认弹窗期间禁止执行的工具（读/查类不拦，避免把澄清本身卡死）
_FORM_GATED_TOOLS = {
    "terminal", "execute_r", "execute_python", "execute_code", "run_script",
    "generate_report", "add_figure", "save_knowledge", "submit_skill",
    "knowledge_write", "conclusion_save", "write_report", "deliver",
}
_FORM_PENDING_TTL = 1800.0  # 30 分钟无答复自动失效（用户走开不该永久锁死）

# 高影响工具：命中即强制 L2（入库/报告/结论产物，不可降级）
_DEBATE_HIGH_IMPACT_TOOLS = {
    "generate_report", "add_figure", "save_knowledge", "submit_skill",
    "knowledge_write", "conclusion_save", "write_report", "deliver",
}
# 失败信号工具（terminal/脚本执行，重试≥2 或报错 → 升级 L2）
_DEBATE_EXEC_TOOLS = {"terminal", "execute_r", "execute_python", "execute_code", "run_script"}

# 远程集群工具（2026-09-19 接入）：复合工具，只有真在集群上跑代码的 action
# 才算"执行类"（要过辩论门控/审查门禁/报错重试检测）；check/status/logs/jobs/
# push/pull/cancel 是只读或运维动作，不该被当成执行代码拦下来。
_REMOTE_CLUSTER_TOOL = "remote_cluster"
_REMOTE_CLUSTER_EXEC_ACTIONS = {"run", "submit"}


def _location_mismatch(es, tool_name, args):
    """执行位置与 rail_review(pre) 的审查位置对不上 → 软提醒（2026-10-09，不硬拦）。

    用户实测事故：本地缺 RUVSeq，rail_review(pre)（老逻辑只查本机）把**集群投递**硬拦了，
    而集群 R4.41 里其实装着。现在 pre 会自报 location（local/cluster/cloud），这里负责在
    "审查位置 ≠ 执行位置" 时提示重审 —— 只提醒不 block：拦死会造出新的死锁（正是要修的坑）。
    """
    loc = str(getattr(es, "rail_pre_location", "") or "")
    if not loc or not getattr(es, "rail_pre_done", False):
        return ""
    is_remote_tool = tool_name == _REMOTE_CLUSTER_TOOL
    remote_exec = is_remote_tool and _is_exec_call(tool_name, args)
    local_exec = (not is_remote_tool) and _is_exec_call(tool_name, args)
    if remote_exec and loc == "local":
        return ("⚠️ 这次是**集群**执行，但上一次 rail_review(pre) 按**本机**环境审的"
                "（本地包清单 ≠ 集群包清单：本地缺的包集群上可能有，反之亦然，别据此拒跑）。"
                "请重审：rail_review(phase='pre', location='cluster', node=<节点>, env=<环境>)；"
                "包清单用 remote_cluster(action='r_packages', packages=[...]) 查集群。")
    if local_exec and loc in ("cluster", "cloud"):
        return ("⚠️ 上一次 rail_review(pre) 按 **%s** 审的，但这次在**本机**跑"
                "（execute_r/terminal 用的是本机 R）。本地任务请用 location='local' 重审，"
                "否则本地缺包会被漏掉。" % ("集群" if loc == "cluster" else "云平台"))
    return ""


def _args_as_dict(args):
    if isinstance(args, dict):
        return args
    try:
        return json.loads(str(args))
    except Exception:
        return {}


def _is_exec_call(tool_name: str, args) -> bool:
    """这次调用是否算"执行代码"（门禁/重试/参数核查共用判定）。"""
    if tool_name == _REMOTE_CLUSTER_TOOL:
        action = str(_args_as_dict(args).get("action") or "").strip().lower()
        return action in _REMOTE_CLUSTER_EXEC_ACTIONS
    return tool_name in _DEBATE_EXEC_TOOLS

# 参数核查清单规则（2026-08-13）：按代码关键词定向注入核查项——零 token
# 成本（纯字符串匹配，不跑 R、不调 LLM），意图识别=关键词命中。只在该
# 类代码执行前出现在辩论门控消息里，引导 agent 辩脚本设计时逐项核查，
# 提前拦截参数语义错误（如 Harmony 的 sample 列实为 cells）→ 正确一遍过。
_PARAM_CHECK_RULES = [
    (("harmony", "runharmony", "group.by.vars", "vars.to.regress", "integrat"),
     "batch/整合变量语义：该列是样本级还是细胞级？唯一值数≈细胞总数 = 疑似 cells 当 sample（必须实查唯一值数与每水平平均细胞数）"),
    (("findallmarkers", "findmarkers", "deg", "wilcox"),
     "marker/DEG 参数：分组列正确性、only.pos/min.pct/logfc.threshold 取值依据、多重检验校正方法"),
    (("resolution", "findclusters", "leiden"),
     "聚类 resolution：与细胞数的匹配度（细胞越多 resolution 越要低），取值是否有依据"),
    (("doubletfinder", "doublets", "scds", "scrublet"),
     "双联体参数：预期 doublet 率是否按上样细胞数推算（~0.8%/1000 细胞）"),
    (("percent.mt", "percent.mito", "nfeature", "ncount", "subset"),
     "QC 过滤阈值：MT%/nFeature/nCount 阈值是否有本数据依据（默认值未必合适，需看分布再定）"),
    (("sctransform", "normalize", "log10"),
     "归一化方法：SCTransform vs LogNormalize 选择依据、vars.to.regress 是否必要且正确"),
    # 多组学核查（2026-08-13 扩展：ATAC/空间/bulk/代谢/蛋白/微生物/表观）
    (("deseq2", "edger", "limma", "design", "contrast"),
     "bulk 设计矩阵：design 公式与因子水平是否正确（对照/处理命名、交互项——设计错了结论全错，必须与用户确认）"),
    (("macs2", "callpeak", "fragments", "tss", "motif"),
     "ATAC/ChIP：fragment 数过滤阈值（<1000 低质量）、peak calling q 值、TSS 富集 QC、input 对照/motif 背景选择"),
    (("spatial", "spot", "deconvol", "cell2location", "stlearn"),
     "空间组：spot 分辨率与组织切片匹配度、空间聚类参数、去卷积方法选择依据"),
    (("metabol", "代谢", "xcms", "msdial", "lipid", "m/z", "peakpicking"),
     "代谢组：归一化方法（内标/TIC/quantile）选择、QC 样本 RSD 过滤、log2 转换、单变量 vs 多变量检验适用性"),
    (("proteom", "蛋白", "maxquant", "diann", "lfq", "imputation"),
     "蛋白组：缺失值填补策略（低丰度=随机缺失 vs 高丰度=非随机）、归一化方法、差异检验适用性"),
    (("microbiom", "微生物", "16s", "qiime", "dada2", "otu", "asv", "raref"),
     "微生物组：抽平深度选择、相对丰度 vs 绝对丰度、多样性指数与距离矩阵选择的适用性"),
    (("methylation", "甲基化", "dmr", "bisulfite", "cut&tag", "cuttag"),
     "表观组：DMR 检验方法（bumphunter/DSS）适用性、对照组设置、低覆盖位点过滤"),
]


def _param_checklist(code: str) -> list:
    """按代码内容生成定向参数核查清单（零成本；无命中返回空列表）。"""
    cl = (code or "").lower()
    checks = []
    for keywords, item in _PARAM_CHECK_RULES:
        if any(k in cl for k in keywords):
            checks.append(item)
    return checks


def _error_fingerprint(text: str) -> str:
    """报错文本指纹：规范化（去数字/路径/内存地址/时间戳/换行）→ md5。

    用于判断"同一段代码的报错是不是同一种"——同一指纹连续出现
    = 重复相同报错（盲目重试无效）。
    """
    if not text:
        return ""
    t = str(text)
    # 去掉易变内容：十六进制地址、数字、反斜杠路径、时间戳、行号
    t = re.sub(r'0x[0-9a-fA-F]+', '0xADDR', t)
    t = re.sub(r'[A-Za-z]:[\\/][^\s"\']*', 'PATH', t)
    t = re.sub(r'\b\d+\b', 'N', t)
    t = re.sub(r'\s+', ' ', t)
    t = t.strip().lower()
    if len(t) < 20:
        return t
    import hashlib
    return hashlib.md5(t.encode("utf-8", errors="replace")).hexdigest()[:16]


def _looks_like_encoding_garbage(text: str) -> bool:
    """识别编码乱码特征（GBK/UTF-8 解码失败产物），用于提示"这是乱码不是新报错"。

    覆盖：
    - Python 报错关键词：UnicodeDecodeError / illegal multibyte / can't decode byte
    - 替换字符 U+FFFD（�）
    - GBK 经典乱码：锟斤拷（UTF-8 被 GBK 读）、�����（\ufffd 重复）
    - 中文正常输出不算乱码（科研输出常含中文）
    """
    if not text:
        return False
    t = str(text)
    markers = ("unicodedecodeerror", "illegal multibyte sequence",
               "can't decode byte", "codec can't decode",
               "\\ufffd", "\ufffd", "锟斤拷", "锘匡拷")
    low = t.lower()
    for m in markers:
        if m in low:
            return True
    # 大量替换字符（≥5 个连续 �）也是乱码特征
    if t.count("\ufffd") >= 5:
        return True
    return False


# P1(2026-09-22): 线性/只读命令 —— 没有方案分歧，辩不出新东西
_LINEAR_CMD_RE = re.compile(
    r"^\s*(ls|dir|cat|head|tail|wc|file|which|whereis|pwd|cd|cp|mv|mkdir|rmdir|touch|"
    r"wget|curl|unzip|tar|zip|scp|rsync|git|conda|mamba|pip|pip3|md5sum|sha256sum|du|df|"
    r"find|grep|rg|sed|awk|sort|uniq|tree|stat|echo)\b", re.I)


# ==================== P3 辩论门控 v3（2026-10-12 用户口径重写）====================
# 用户原话（2026-10-12）：
#   「方案/脚本/设计 … 图/绘图/配色 —— 这些不需要辩论，意义不大。
#    统计分析，这类结果有问题，grill me 进行询问即可，最多触发 L1 辩论，但是不要拖延时间；
#    什么时候辩论呢，就是得到的结果太离谱。
#    重要辩论在什么时候触发：生信分析 + 有重要参数 + 结论跟实际/预期不一样、真实数据差异很大
#    → 正方反方找证据链，这才是辩论。
#    辩论是从不同方向寻找证据链：知识库已验知识（L0/L1/L2/L3）、统计学（统计方法和过程有没有问题）、
#    生信（步骤有没有错误、方法有没有错误）。」
#
# 决定"辩不辩"的是**题目类型**（kind），不是"有没有结论"：
#   design  方案/脚本/设计/流程/参数选型/排版       → 永不辩（L0）
#   figure  图/绘图/配色/版式/可视化                → 永不辩（L0）
#   stats   统计分析                                → 只有"结果离谱"才先 grill 用户；最多 L1 且限时
#   bioinfo 生信分析                                → 有重要参数 + 结论与预期/实际不符 → L2 证据链辩论
#   other   其它                                    → 仅硬信号（高影响/失败重试/冲突/离谱）才辩
_DEBATE_KIND_DESIGN = "design"
_DEBATE_KIND_FIGURE = "figure"
_DEBATE_KIND_STATS = "stats"
_DEBATE_KIND_BIOINFO = "bioinfo"
_DEBATE_KIND_LITERATURE = "literature"   # 2026-10-25：文献阅读/总结类（用户口径：不辩论）
_DEBATE_KIND_OTHER = "other"
_DEBATE_KIND_LABELS = {
    _DEBATE_KIND_DESIGN: "方案/脚本/设计",
    _DEBATE_KIND_FIGURE: "图/绘图/配色",
    _DEBATE_KIND_STATS: "统计分析",
    _DEBATE_KIND_BIOINFO: "生信分析",
    _DEBATE_KIND_LITERATURE: "文献阅读/总结",
    _DEBATE_KIND_OTHER: "其它",
}

_KIND_FIGURE_RE = re.compile(
    r"绘图|画图|出图|做图|配色|色标|色板|palette|版式|布局|可视化|热图|火山图|箱线图|"
    r"点图|小提琴|面板|figure|plot|colou?r|layout|matplotlib|ggplot", re.I)
_KIND_DESIGN_RE = re.compile(
    r"方案|脚本|代码|设计|流程|架构|重构|依赖|环境配置|参数(选型|选择|决策)|口径|"
    r"命名规范|目录结构|重构|模板|写作|润色|排版|schedule|design|refactor", re.I)
_KIND_STATS_RE = re.compile(
    r"统计|检验|显著性|fdr|p\s*[-_ ]?值|p-?value|效应量|功效|样本量|多重比较|混杂|"
    r"模型(选择|假设|拟合)|自由度|置信区间|贝叶斯|permutation|null 分布", re.I)
_KIND_BIOINFO_RE = re.compile(
    r"生信|测序|snrna|scrna|单细胞|atac|deg|差异表达|差异基因|比对|比对率|注释|富集|"
    r"聚类|降维|拟时序|变异|甲基化|grn|细胞类型|marker|表达矩阵|counts?|归一化|批次校正|"
    r"h5ad|seurat|scanpy|star|cellranger|featurecounts|deseq|edger|limma", re.I)
# 2026-10-25（用户反馈）：文献阅读类不辩（"读一篇文献找结论"不是分析，更不是要对抗的结论）。
# 放在 design/bioinfo 之前判定：论文正文里常出现"方案/统计/测序"等词，先判文献类避免误入生信/统计线。
_KIND_LITERATURE_RE = re.compile(
    r"文献|论文|paper|文献库|综述|精读|阅读|读全文|全文对照|摘要|abstract|preprint|"
    r"bibliograph|literature|reference|citation|引文|读完|读一下|帮我读|读这|解读|"
    r"总结这篇|提炼这篇|paper_reading|nature-reader|paper-summary|paper_download", re.I)


def classify_topic_kind(text: str) -> str:
    """按用户口径给辩题分类（决定"要不要辩"）。

    顺序很关键：**图 > 设计 > 统计 > 生信**。画图的脚本里也会出现"统计/生信"字样，
    但按用户口径图类不辩；脚本设计类里也可能写"统计方法"，同样不辩。
    """
    t = str(text or "")
    if not t.strip():
        return _DEBATE_KIND_OTHER
    if _KIND_FIGURE_RE.search(t):
        return _DEBATE_KIND_FIGURE
    # 2026-10-25：文献类优先于设计/统计/生信（读文献场景误触辩论的主修点）
    if _KIND_LITERATURE_RE.search(t):
        return _DEBATE_KIND_LITERATURE
    if _KIND_DESIGN_RE.search(t):
        return _DEBATE_KIND_DESIGN
    if _KIND_STATS_RE.search(t):
        return _DEBATE_KIND_STATS
    if _KIND_BIOINFO_RE.search(t):
        return _DEBATE_KIND_BIOINFO
    return _DEBATE_KIND_OTHER


# "结果离谱"信号：统计线的唯一辩论入口；生信线也要它才算"结论对不上"
_ABSURD_RESULT_RE = re.compile(
    r"与预期(不符|相反|不一致)|不符合预期|预期之外|远超预期|超出预期|"
    r"差异(极|很|非常|特别|巨)大|结果(太|极其|非常|有点)?离谱|离谱|荒唐|"
    r"(异常|意外)(偏高|偏低|升高|降低|增高|变大|变小)|假阳性|假阴性|"
    r"自相矛盾|互相矛盾|矛盾|不可能(出现|发生)|反直觉|说不通|"
    r"unexpected|contradict\w*|discrepan\w*|absurd|outlier|inconsistent|too good to be true",
    re.I)


def looks_absurd(text: str) -> str:
    """"结果离谱/与预期不符"的具体措辞（空串 = 没这信号）。"""
    m = _ABSURD_RESULT_RE.search(str(text or ""))
    return m.group(0) if m else ""


def _debate_require_payload(kind: str, level: int, reasons: list) -> tuple:
    """按「辩什么」生成 require 工具 + 给模型的指令文本（用户口径：辩论 = 找证据链）。

    stats  → 先 ask_user grill 用户（带选项表单）；用户答复后无明显分歧就不辩
    bioinfo→ debate_analysis，且必须按"证据链对抗"出结论（KB 分级 / 统计线 / 生信线）
    """
    if kind == _DEBATE_KIND_STATS:
        qs = [
            "这批结果里哪些数字/现象与您的预期或已有结论不一致？（指标 + 数值）",
            "统计方法与流程里有没有您已知的可疑环节（批次、配对、多重检验、过滤阈值、样本量、模型假设）？",
            "您期望的方向/量级是什么（用来判定“离谱”的基线）？",
        ]
        return ["ask_user"], (
            "\n❓ 统计线规矩（用户口径）：先把上面这几点用 ask_user 弹确认表单问清楚，别猜、别直接开辩论：\n"
            + "\n".join(f"  • {q}" for q in qs)
            + "\n  用户答复后：若仍无明显分歧 → 结论标注低置信直接给，**不开辩论**；"
              "确有分歧才 debate_analysis(level='L1')，限时（≤180s），且每条论点必须带证据链。")
    if kind == _DEBATE_KIND_BIOINFO:
        return ["debate_analysis"], (
            "\n🧬 辩论形态 = **证据链对抗**（不是观点辩论）：正反方各自独立取证，每条论点必须挂证据节点 ——\n"
            "  • 知识库已验知识：标注证据级别（L0 无来源 / L1 有来源未验证 / L2 湿实验验证 / L3 临床级）+ locator；\n"
            "  • 统计线：统计方法与过程有没有问题（混杂/批次/多重检验/样本量/模型假设/效应量）；\n"
            "  • 生信线：步骤与方法有没有错误（上游质控/注释版本/参考基因组/工具与参数/可复现性）。\n"
            "  裁判只按证据链完整度出分并列 missing；无证据的论点必须标 [仅是推理]。")
    return [], ""


def _debate_worthiness(signals: dict):
    """P1(2026-09-22): "值不值得辩"前置判断 —— 返回跳过理由字符串（None = 值得辩）。

    用户原话："怎么什么问题都辩论呢？要分清楚情况。"
    不辩的情况（辩论必须至少有 2 条活选项，且选哪条会改变下一步动作）：
      ① 只有 ≤1 条可选路径（没有分歧）② 线性执行/已知流程
      ③ 事实查询/只读获取（有唯一正确答案）④ 同一议题已辩过
      ⑤ 调用方显式标注 no_debate
    """
    if signals.get("no_debate"):
        return "调用方标注 no_debate：跳过辩论"
    n = signals.get("n_options")
    if n is not None:
        try:
            if int(n) < 2:
                return f"只有 {int(n)} 条可选路径（没有分歧，辩不出新东西）：跳过辩论"
        except Exception:
            pass
    if signals.get("fact_lookup"):
        return "事实查询/只读获取（有唯一正确答案）：跳过辩论"
    if signals.get("readonly"):
        return "只读观察步骤（不产生新结论）：跳过辩论"
    if signals.get("repeat_topic"):
        return "同一议题已辩过（去重）：跳过辩论"
    if signals.get("linear"):
        return "线性执行/已知流程（无方案分歧）：跳过辩论"
    _cmd = str(signals.get("cmd") or "")
    if (_cmd and _LINEAR_CMD_RE.match(_cmd)
            and not signals.get("uncertainty") and not signals.get("conflict")
            and not signals.get("failed_retries")):
        return "线性执行命令（无方案分歧、无异常信号）：跳过辩论"
    return None


def debate_gate(es: "EnforcementState", stage: str = "conclusion",
                signals: dict = None) -> tuple:
    """三级门控判定 — 什么时候该辩论。

    P1(2026-09-22) 分情况矩阵（用户要求"不要为了辩论而辩论"）：
      只读/事实查询/线性执行/重复议题/活选项<2 → L0 不辩
      analysis 级脚本设计与执行（首次，且脚本里有可争议参数）→ L1
      结论合成：有 ≥2 条活选项 / 不确定 / 低置信 → L2；没有分歧 → L1
      高影响（入库/报告/结论产物）、失败重试≥2、rail_review(post) 未通过 → L2（强制，不降级）

    Args:
        es: EnforcementState（读取 analysis_level / debate_count / debated_topics / budget）
        stage: "before_script" | "after_script" | "conclusion"
        signals: dict，可含
            - high_impact: bool  命中入库/报告/结论工具 → 强制 L2 不可降级
            - failed_retries: int 同命令重试次数（≥2 升级）
            - last_error: bool    最近一次执行报错
            - conflict: bool      rail_review(post) 未通过 / 与上次结果冲突
            - uncertainty: bool   候选参数≥2 / 犹豫措辞 / 自评低置信

    Returns:
        (level: int, reasons: list[str], force: bool)
        force=True 表示不可降级（高影响），预算护栏不得削减
    """
    signals = signals or {}
    reasons = []
    level = DEBATE_L0
    force = False

    # 2026-10-18（风险分级降时延）：小规模/低风险任务直接 L0，不辩论。
    # 实测背景：一场自动辩论曾吃掉 550s（judge 反复 ReadTimeout + 回退链），
    # 而真正的分析只用了 0.45s —— 这正是用户感知的"卡住/繁琐"。
    try:
        from webui.runtime import risk_tier as _rt
        _tier = _rt.current_tier(es)
        if _rt.max_debate_level(_tier) == 0:
            return DEBATE_L0, [
                f"风险分级={_tier}（{_rt.describe(_tier)}）：本任务不触发辩论。"
                "需要对抗审查时显式调用 debate_analysis 即可。"], False
    except Exception:
        pass

    if es.analysis_level in ("chat", "lightweight"):
        return DEBATE_L0, ["chat/lightweight 级：无分析对象，跳过辩论"], force

    # ① 题目类型决定"要不要辩"（用户口径 2026-10-12）
    kind = signals.get("topic_kind") or classify_topic_kind(
        signals.get("topic") or signals.get("cmd") or signals.get("text")
        or getattr(es, "topic_hint", ""))
    dev = str(signals.get("deviation") or "").strip()
    # 2026-10-25：文献阅读类不做"结果离谱"扫描 —— 读文献时 _last_terminal_result 就是论文
    # 正文/摘要，"unexpected/矛盾/inconsistent" 几乎必出现，会假触发 L2 多角色辩论。
    if not dev and kind != _DEBATE_KIND_LITERATURE:
        _scan = " ".join([str(getattr(es, "_last_terminal_result", "") or ""),
                          str(getattr(es, "topic_hint", "") or "")])
        dev = looks_absurd(_scan)
    has_dev = bool(dev)
    impact = bool(signals.get("high_impact"))
    failures = int(signals.get("failed_retries", 0) or 0) + (1 if signals.get("last_error") else 0)
    conflict = bool(signals.get("conflict"))
    uncertainty = bool(signals.get("uncertainty"))
    _opts = signals.get("fork_options") or []
    _fork = bool(signals.get("has_fork")) or (isinstance(_opts, (list, tuple, set)) and len(_opts) >= 2)
    _hard = impact or failures >= 2 or conflict

    # ② 方案/脚本/设计、图/绘图/配色、文献阅读/总结 —— 永不辩
    #    （用户原话："这些不需要辩论，意义不大"；2026-10-25 追加文献类：
    #     "读一篇文献找结论也要辩论吗？这个触发场景不对"）
    if kind in (_DEBATE_KIND_DESIGN, _DEBATE_KIND_FIGURE, _DEBATE_KIND_LITERATURE):
        return DEBATE_L0, [
            f"{_DEBATE_KIND_LABELS[kind]}类不辩论（用户口径：辩论=找证据链，这类辩不出证据）"], force

    # ③ 值不值得辩（事实查询/只读/线性/活选项<2/重复议题/显式 no_debate）—— 硬信号/离谱信号豁免
    if not (_hard or has_dev):
        _skip = _debate_worthiness(signals)
        if _skip:
            return DEBATE_L0, [_skip], force

    if kind == _DEBATE_KIND_STATS:
        # ④ 统计线：只有"结果离谱/与预期不符"才辩；先 grill 用户；最多 L1 且限时（不要拖延时间）
        if not (has_dev or conflict or failures >= 2):
            return DEBATE_L0, ["统计分析未见离谱/冲突信号：不辩论（结果有问题时先问用户）"], force
        level = DEBATE_L1
        reasons.append("统计分析结果离谱/与预期不符：先 grill 用户澄清，最多 L1 且限时 180s"
                       + (f"（信号：{dev}）" if dev else ""))
        if impact:
            reasons.append("高影响工具（入库/报告）：统计线仍只用 L1 限时辩，不做 8 角色")
    elif kind == _DEBATE_KIND_BIOINFO:
        # ⑤ 生信线（用户指定的"重要辩论"）：重要参数 + 结论与预期/实际不符（数据差异大）→ L2 证据链辩论
        _params = bool(signals.get("important_params")) or bool(signals.get("param_checklist"))
        if not _params:
            return DEBATE_L0, ["生信分析但无重要参数分歧：不辩论"], force
        if has_dev or conflict or failures >= 2:
            level = DEBATE_L2
            reasons.append("生信分析 + 重要参数 + 结论与预期/实际不符（数据差异大）→ L2 证据链辩论"
                           + (f"（信号：{dev}）" if dev else ""))
            # 只有高影响才"强制不可降级"；"结果离谱"虽然值一场 L2，但仍受会话预算护栏约束
            # （用户口径：一个重要话题辩一场，但一个会话别辩几十场）
            force = bool(impact)
        elif uncertainty or _fork:
            level = DEBATE_L1
            reasons.append("生信分析 + 重要参数 + 存在分歧：L1 轻量证据链辩论")
        else:
            return DEBATE_L0, ["生信分析：参数与结果一致、无异常信号：不辩论"], force
    else:
        # ⑥ 其它类型：只有硬信号（高影响/失败重试/冲突）或"结果离谱"才辩
        if not (_hard or has_dev):
            return DEBATE_L0, ["未识别到需要证据链对抗的信号：不辩论"], force
        if impact:
            level = DEBATE_L2
            reasons.append("高影响（入库/报告/结论产物）：强制 L2")
            force = True
        elif has_dev or failures >= 2 or conflict:
            level = DEBATE_L2
            reasons.append("结果离谱/冲突/连续失败：升级证据链辩论")
        else:
            level = DEBATE_L1
            reasons.append("存在分歧/不确定性：L1 轻量辩论")

    # ⑦ 预算护栏：非强制时**真停**（一个会话不要辩几十场）
    # 2026-10-18 用户口径「辩论不要预算上限」：budget <= 0 = 不限场次（跳过本节），
    # 不再把"停止辩论"写进 reasons（否则用户看到的就是「预算护栏：已辩论 N 次 ≥ budget=M」）。
    if (not force and level >= DEBATE_L1 and es.debate_budget > 0
            and es.debate_count >= es.debate_budget):
        level = DEBATE_L0
        reasons.append(f"预算护栏：本会话已辩论 {es.debate_count} 次 ≥ budget={es.debate_budget}，"
                       "停止辩论（非强制场次不再降级续辩）")

    # C3(2026-08-11): token 预算护栏（cost 治理）— token_budget>0 时生效
    if not force and level >= DEBATE_L1 and es.token_budget > 0 and es.token_used >= es.token_budget:
        level = DEBATE_L0
        reasons.append(f"token 预算耗尽：已用 {es.token_used} ≥ budget={es.token_budget}，降级 L0")

    return level, reasons, force


# 自动标题总结钩子：由 server.py 在 import 本模块后注入（rail_review(post) 完成时回调）
_title_summary_hook = None


class EnforcementState:
    """会话级强制执行状态追踪"""

    def __init__(self, session_id: str, results_dir: str = ""):
        self.session_id = session_id
        self.results_dir = results_dir
        self.skills_loaded: set = set()
        self.knowledge_searched: bool = False
        self.rail_pre_done: bool = False
        self.rail_post_done: bool = False
        # 2026-10-09 用户要求：审查要区分「在哪审的」（本机/集群/云）
        # 存 rail_review(pre) 自报的位置，执行时对不上就软提醒（不硬拦）
        self.rail_pre_location: str = ""      # local | cluster | cloud | ""
        self.rail_pre_line: str = ""          # 审查结果里那句「📍 审查位置：…」
        self.debate_done: bool = False  # 🔧 P2(2026-08-10): 保留兼容字段，新逻辑用 debated_topics
        self.debated_topics: set = set()  # P2: topic 级去重 — 同一主题只辩一次
        self.debate_count: int = 0  # P2: 单会话辩论次数（预算护栏）
        self.debate_budget: int = 3  # P2: 预算上限（config debate.budget 可覆盖）
        # P2(2026-09-22): 裁决必须驱动下一步 —— 行动方案 + 由它生成的待办
        self.debate_plan: dict = {}          # 最近一次裁决 {decision,next_actions,fallback,...}
        self.debate_todos: list = []         # next_actions(owner=ai) → 会话待办
        self.debate_enforce_blocks: bool = True  # config debate.enforce_blocks（默认开）
        self._debate_block_hits: int = 0
        # P3(2026-09-22): 意图确认弹窗未答复前，不许执行（用户要求"先问清楚再动手"）
        self.awaiting_form_id: str = ""       # 正在等用户答复的表单 id
        self.awaiting_form_question: str = ""  # 表单问题（用于拦截提示）
        self.awaiting_form_ts: float = 0.0
        # 2026-10-18：grill 前置门禁状态（开工前先澄清；强度见 config grill.mode）
        self.grill_done: bool = False
        self.grill_ts: float = 0.0
        self.grill_armed: bool = False
        self.grill_reason: str = ""
        # P3(2026-09-22) 预置意图确认门禁：高代价任务第一轮就置位（不依赖模型自觉），
        # 模型调 ask_user 弹表单（或用户直接回消息）即解除。
        self.intent_confirm: bool = False
        self.intent_confirm_reason: str = ""
        self.intent_confirm_ts: float = 0.0
        self.form_block_hits: int = 0
        self.form_answers: list = []          # 用户已提交的表单答复（审计用）
        # P4(2026-09-22): 代码修改模式 —— 用户给脚本/代码让"改一下"时，只许改不许跑
        # 用户原话："如果我给一些脚本和代码让 MemOmics 帮我改，它会不会自己跑去执行？"
        self.code_edit: bool = False          # 代码修改模式已置位（未获准执行）
        self.code_edit_reason: str = ""
        self.code_edit_ts: float = 0.0
        self.code_edit_verify: bool = False   # 用户已同意"用我的数据跑一遍验证"
        self.code_edit_block_hits: int = 0
        self.code_edit_data: list = []        # 记忆里可供验证的数据路径（弹窗/提示用）
        self.token_used: int = 0  # C3(2026-08-11): 本会话辩论累计 token（usage 统计）
        self.token_budget: int = 0  # C3: token 预算上限（config debate.token_budget，0=不限）
        self._pending_high_impact: bool = False  # P2: 高影响工具已调用，待门控消费
        self.analysis_level: str = "chat"
        # 2026-10-18 风险分级：trivial|low|medium|high（决定本回合是否上重审查）
        self.risk_tier: str = ""
        self._pending_record: bool = False  # 上一步 terminal 完成后还没 record
        self._pending_record_warned: bool = False  # 2026-08-22: execute 门禁软拦截已提醒一次（不卡死）
        self._exec_error_hist: dict = {}  # 2026-08-22: 每个命令的报错指纹历史 {cmd_key: [fp,...]}
        self._exec_error_repeat: set = set()  # 已判定"连续相同报错"的 cmd_key（防重复提醒）
        self._exec_garbage_warned: set = set()  # 已提醒过"编码乱码"的 cmd_key
        self._error_recorded: int = 0  # P1-11: 本会话自动 record_error 次数（限 2 防刷屏）
        self._block_kind: str = ""  # P0-1(2026-08-13): 阻断原因类别 rail_pre/rail_post/""
        self._block_reason: str = ""  # P0-1: 阻断原因描述（注入被拦工具的错误消息）
        self._last_terminal_result: str = ""  # 最近 terminal 输出（提取参数用）
        self._exec_retries: dict = {}  # P2: 命令/脚本重试计数 {cmd: n}
        self._last_exec_error: bool = False  # P2: 最近一次执行是否报错
        # P3(2026-10-12): 最近一条用户消息 —— 辩论门控据此判断题目类型
        # （方案/脚本/图 → 不辩；统计 → 结果离谱才 grill；生信 → 重要参数+结论对不上才辩）
        self.topic_hint: str = ""
        self.terminal_count: int = 0
        self.tool_history: list = []
        self.warnings: list = []
        self.blocked: bool = False
        self._blocked_attempts: int = 0  # 2026-08-17: 连续被拦次数（重试风暴压制）
        self.conclusions_dir: str = ""

    def get_conclusions_dir(self) -> str:
        """获取结论目录路径"""
        if not self.conclusions_dir and self.results_dir:
            cdir = os.path.join(self.results_dir, "conclusions")
            os.makedirs(cdir, exist_ok=True)
            self.conclusions_dir = cdir
        return self.conclusions_dir

    def to_dict(self) -> dict:
        return {
            "skills_loaded": list(self.skills_loaded),
            "knowledge_searched": self.knowledge_searched,
            "rail_pre_done": self.rail_pre_done,
            "rail_post_done": self.rail_post_done,
            "rail_pre_location": self.rail_pre_location,
            "rail_pre_line": self.rail_pre_line,
            "debate_done": self.debate_done,
            "debated_topics": list(self.debated_topics),  # P2
            "debate_count": self.debate_count,  # P2
            "debate_budget": self.debate_budget,  # P2
            "debate_decision": (self.debate_plan or {}).get("decision", ""),  # P2
            "debate_todos": [{"id": t.get("id"), "title": t.get("title"), "status": t.get("status"),
                              "blocks": t.get("blocks")} for t in (self.debate_todos or [])],  # P2
            "debate_blocks_pending": len(pending_debate_blocks(self)),  # P2
            "debate_block_hits": self._debate_block_hits,  # P2
            "awaiting_form_id": self.awaiting_form_id,  # P3
            "awaiting_form_question": self.awaiting_form_question,  # P3
            "intent_confirm": self.intent_confirm,  # P3（预置门禁）
            "intent_confirm_reason": self.intent_confirm_reason,  # P3
            "form_answers": len(self.form_answers or []),  # P3
            "form_block_hits": self.form_block_hits,  # P3
            "code_edit": self.code_edit,  # P4
            "code_edit_verify": self.code_edit_verify,  # P4
            "code_edit_block_hits": self.code_edit_block_hits,  # P4
            "code_edit_data": len(self.code_edit_data or []),  # P4
            "token_used": self.token_used,  # C3
            "token_budget": self.token_budget,  # C3
            "analysis_level": self.analysis_level,
            "terminal_count": self.terminal_count,
            "warnings": self.warnings[-5:],
        }


# === 全局会话级状态存储 ===
# P3(2026-09-22) 修复模块分裂：enforcement.py 可能同时被加载成两个模块对象 ——
#   `import enforcement`（webui/ 在 sys.path，脚本启动路径）
#   `from webui import enforcement`（仓库根在 sys.path，server.py 里的用法）
# 两者各自维护 _session_enforcement → 门禁状态分裂（ask_user 在一个实例置位，
# tool_start_cb 在另一个实例查不到，门禁形同虚设）。
# 修法：把状态字典挂到进程级共享模块上，两个实例拿到同一个 dict。
def _shared_state_registry() -> dict:
    import sys as _sys
    import types as _types
    _name = "_memomics_enforcement_registry"
    _mod = _sys.modules.get(_name)
    if _mod is None:
        _mod = _types.ModuleType(_name)
        _mod.states = {}
        _sys.modules[_name] = _mod
    return _mod.states


_session_enforcement: dict = _shared_state_registry()


def get_enforcement(session_id: str) -> EnforcementState:
    if session_id not in _session_enforcement:
        _session_enforcement[session_id] = EnforcementState(session_id)
    return _session_enforcement[session_id]


def reset_enforcement(session_id: str):
    _session_enforcement.pop(session_id, None)


def clear_hard_block(session_id: str) -> bool:
    """2026-08-16: 用户新消息 = 新指令 → 解除审查硬阻断残留（fail-open）。

    阻断只应约束"当前一轮执行流"，不应跨用户回合永久锁死执行类工具
    （12G Seurat 对象读取案例：rail_review(post) 未通过残留使 execute_r
    一直被拦，重跑 pre 也解不开 → 死锁）。审查门禁会在新一轮自动重新武装
    （执行完成后照常要求 rail_review(post)）。
    """
    es = _session_enforcement.get(session_id)
    if not es:
        return False
    was = bool(es.blocked or es._pending_record)
    es.blocked = False
    es._block_kind = ""
    es._block_reason = ""
    es._blocked_attempts = 0
    es._pending_record = False  # record_run 门禁同样只约束当轮
    es._pending_record_warned = False  # 2026-08-22: 软拦截计数随回合重置
    return was


def _grill_cfg() -> str:
    """grill 强度：config.yaml grill.mode（off|auto|required），默认 auto。"""
    try:
        import yaml as _y
        _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memomics_home", "config.yaml")
        if os.path.exists(_p):
            _d = _y.safe_load(open(_p, encoding="utf-8")) or {}
            _m = str((_d.get("grill") or {}).get("mode") or "auto").strip().lower()
            if _m in ("off", "auto", "required"):
                return _m
    except Exception:
        pass
    return "auto"


_GRILL_SKIP_WORDS = ("直接做", "不用问", "别问", "按默认", "你自己定", "别废话", "just do it", "go ahead")
_GRILL_TASK_VERBS = ("分析", "跑", "画", "优化", "筛选", "统计", "写", "生成", "做", "比对",
                     "预测", "注释", "降维", "聚类", "差异", "富集", "预处理", "建模")
# 具体线索 = 路径分隔符 / 盘符 / 数字（阈值、样本量等）。中文泛称（"那个数据"）不算，
# 否则"帮我分析一下那个数据"会被当成交代清楚而不澄清 —— 实测踩过。
_GRILL_SPECIFICS = (os.sep, "/", ":", "：")


def should_grill(user_text: str) -> bool:
    """auto 强度下是否该先澄清：像任务 + 没说清输入/判据 + 用户没让直接做。

    刻意保守（宁可不问）：只在“确实是任务动词”且“完全没给具体线索”时才武装门禁，
    这样日常问答/明确指令不会被拖慢 —— 对应「执行不繁琐」这条目标。
    """
    t = (user_text or "").strip()
    if len(t) < 4:
        return False
    low = t.lower()
    if any(w in low for w in _GRILL_SKIP_WORDS):
        return False
    if not any(v in t for v in _GRILL_TASK_VERBS):
        return False
    # 给了路径/数字等具体线索 → 视为已交代，不打扰（数字：阈值/样本量/分组数）
    if any(s in t for s in _GRILL_SPECIFICS) or any(ch.isdigit() for ch in t):
        return False
    # 纯提问句式（怎么/为什么/是什么/能不能）不强制澄清
    if t.rstrip().endswith(("?", "？")) and not any(v in t for v in ("帮我", "给我", "跑", "做")):
        return False
    return True


def arm_grill(es: "EnforcementState", reason: str = "") -> None:
    """武装 grill 门禁：下一个执行类工具必须先澄清。"""
    es.grill_armed = True
    es.grill_done = False
    es.grill_ts = time.time()
    es.grill_reason = str(reason or "")[:200]


def clear_grill(es: "EnforcementState") -> None:
    """新用户消息 → 清空上一轮的 grill 状态（然后按需重新武装）。"""
    es.grill_armed = False
    es.grill_done = False
    es.grill_ts = 0.0
    es.grill_reason = ""


def note_grill_activity(es: "EnforcementState", tool_name: str, args) -> None:
    """模型已澄清的证据：加载 grill-me 技能 / 用 ask_user、clarify 发问。"""
    try:
        name = str(tool_name or "").lower()
        blob = str(args or "").lower()
        if "grill" in blob or "grill" in name:
            es.grill_done = True
            return
        if name in ("ask_user", "ask_user_question", "clarify"):
            es.grill_done = True
    except Exception:
        pass


def grill_gate(es: "EnforcementState", tool_name: str, args):
    """执行类工具的前置 grill 门禁。返回 block dict 或 None（放行）。"""
    try:
        mode = _grill_cfg()
    except Exception:
        mode = "auto"
    if mode == "off":
        return None
    if not _is_exec_call(tool_name, args):
        return None
    if getattr(es, "grill_done", False):
        return None
    if mode == "auto" and not getattr(es, "grill_armed", False):
        return None
    if mode == "required" and not getattr(es, "grill_armed", False):
        # required：逢任务必问 —— 首个执行类工具就武装
        arm_grill(es, "required：每个任务开工前先澄清")
    _why = getattr(es, "grill_reason", "") or "需求还不够清楚"
    return {"blocked": True,
            "message": ("⛔ 开工前置未完成：先澄清再执行（%s）。\n"
                        "正确做法：① skill_view(name='grill-me') 取拷问清单；② 用**一次**提问把"
                        "「目标 · 输入数据与位置 · 验收判据」问清（≤3 问）；③ 用户答复后再执行工具。\n"
                        "若用户已明确“直接做/不用问”，可忽略本提示并在回复里说明依据。" % _why)}


def create_enforcement_callbacks(session: dict, session_emit_fn, agent_ref: list = None):
    """
    创建强制执行回调，注入到 AIAgent。
    
    Args:
        session: MemOmics 会话 dict (含 id, results_dir, messages 等)
        session_emit_fn: _session_emit 函数
        agent_ref: [agent] 单元素列表，用于在回调中引用 agent（避免循环导入）
    
    Returns:
        dict with tool_start_callback, tool_complete_callback, tool_progress_callback
    """
    sid = session.get("id", "")
    es = get_enforcement(sid)
    es.results_dir = session.get("results_dir", "")
    es.conclusions_dir = ""
    # P2(2026-08-10): 预算护栏从 config.yaml debate.budget 读取（缺省 3）
    try:
        import yaml as _y
        _cfg_p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memomics_home", "config.yaml")
        if os.path.exists(_cfg_p):
            _d = _y.safe_load(open(_cfg_p, encoding="utf-8")) or {}
            # 2026-10-18（用户口径：辩论不要预算上限）：budget <= 0 = 不限场次。
            # 旧实现只认正数 → 写 0 被静默忽略并回退默认 3，用户仍会被"预算护栏"停掉。
            _b = (_d.get("debate") or {}).get("budget")
            if isinstance(_b, int):
                es.debate_budget = _b
            # P2(2026-09-22): 裁决 blocks 是否硬约束（默认开；可 config 关掉）
            _eb = ((_d.get("debate") or {}).get("enforce_blocks"))
            if isinstance(_eb, bool):
                es.debate_enforce_blocks = _eb
    except Exception:
        pass

    def _detect_tool_name(args_str: str) -> str:
        """从工具调用参数中提取技能/工具名"""
        try:
            if not args_str:
                return ""
            args = json.loads(args_str) if isinstance(args_str, str) else args_str
            return args.get("name", args.get("tool", args.get("command", "")))
        except Exception:
            return ""

    def _emit(etype: str, **kwargs):
        try:
            msg = {"type": etype, "session_id": sid, "ts": datetime.now().strftime("%H:%M:%S")}
            msg.update(kwargs)
            session_emit_fn(session, msg)
            # P2-6(2026-08-10): 门控提示注入 agent 上下文 —
            # require 事件通过 MemOmics 原生 _pending_steer 通道注入，
            # 下一批工具调用后 LLM 就能看到（零底座改动，运行中即时生效）
            if etype == "enforcement" and kwargs.get("action") == "require" and agent_ref:
                _inject_agent_hint(agent_ref[0], "【系统强制提示】" + str(kwargs.get("message", "")))
        except Exception:
            pass

    def _inject_agent_hint(agent, text: str) -> bool:
        """把提示注入 agent 上下文（MemOmics 原生 _pending_steer 通道）。"""
        try:
            lock = getattr(agent, "_pending_steer_lock", None)
            if lock is not None:
                with lock:
                    agent._pending_steer = (agent._pending_steer + "\n" + text) if agent._pending_steer else text
            else:
                existing = getattr(agent, "_pending_steer", None)
                agent._pending_steer = (existing + "\n" + text) if existing else text
            return True
        except Exception:
            return False

    def tool_start_cb(tool_call_id: str, tool_name: str, args):
        """工具执行前拦截。

        P0-1(2026-08-13) 硬阻断接线：返回值协议 —
          None                                = 放行
          {"blocked": True, "message": str}   = 阻断（tool_executor 会检查并拦截执行）
        修复类工具（rail_review/skill_evolution/debate_analysis 等）永远放行，避免死锁。
        """
        es.tool_history.append({"tool": tool_name, "args": str(args)[:200], "time": time.time(), "phase": "start"})

        # 2026-10-18（借鉴 DSH permission-presets）：权限档位门禁 —— 统一在这里强制，
        # read-only 拦写/执行；workspace-write 只允许写会话工作区。默认 danger-full-access = 不拦。
        try:
            from webui.runtime import permission_presets as _pp
            _p_ok, _p_why = _pp.check(tool_name, args, session)
            if not _p_ok:
                _emit("enforcement", action="blocked", message="⛔ " + _p_why,
                      permission_mode=_pp.get_mode())
                return {"blocked": True, "message": "⛔ " + _p_why}
        except Exception:
            pass

        # P0-1: es.blocked 置位（rail_review pre/post 未通过）→ 拦截执行类工具
        # 修复类工具不在 _DEBATE_EXEC_TOOLS，天然放行。
        if es.blocked and _is_exec_call(tool_name, args):
            # 2026-08-17 重试风暴压制（memomics-0228a136 案例：单响应 150+ 次
            # execute_r 被拦，模型疯狂重试烧 token）：第 2 次起注入强制引导，
            # 让模型停止重试执行工具、先跑 rail_review 解绑。
            es._blocked_attempts = int(getattr(es, "_blocked_attempts", 0)) + 1
            _base = es._block_reason or "⛔ 执行被拦截：前序审查未通过。"
            _hint = ("（解除：修复问题后重新 rail_review 通过自动解绑；或用户发新消息重置本轮审查状态）")
            if es._blocked_attempts >= 2:
                _emit("enforcement", action="require", require=["rail_review"],
                      message=(f"⛔ 已连续 {es._blocked_attempts} 次尝试执行被拦截！"
                               f"停止重试 {tool_name}。正确路径：先调用 rail_review 通过拿到"
                               "解绑（检查 required_packages 是否与实际环境一致），"
                               "解绑后执行工具才会放行；反复被拦请检查 rail_review 的参数。"))
            return {"blocked": True,
                    "message": _base + f"（已连续拦截 {es._blocked_attempts} 次）" + _hint}

        # 2026-10-18（用户决策1）：>100MB 数据/产物 → 先问用户要不要持久化（硬门禁）
        try:
            import re as _re, os as _os
            _blob = str(args or "")
            _paths = _re.findall(r"([A-Za-z]:[\\/][^\s\"'\,;]+)", _blob)
            if _paths:
                from memomics.bio_tools import dataset_cache as _dc
                _rd = getattr(es, "results_dir", "") or ""
                _big = []
                for _p in _paths[:20]:
                    try:
                        if _os.path.isfile(_p) and _os.path.getsize(_p) >= _dc.ASK_THRESHOLD_MB * 1024 * 1024:
                            _big.append({"path": _p,
                                         "size": _os.path.getsize(_p),
                                         "mb": round(_os.path.getsize(_p) / (1024.0 * 1024.0), 1)})
                    except Exception:
                        continue
                if _big:
                    _known = {_os.path.normcase(_os.path.abspath(it.get("path", "")))
                              for it in (_dc._load(_rd).get("datasets") or [])} if _rd else set()
                    _todo = [b for b in _big if _os.path.normcase(_os.path.abspath(b["path"])) not in _known]
                    if _todo and not getattr(es, "_bigdata_asked", False):
                        es._bigdata_asked = True
                        _msg = _dc.build_ask_message(_todo)
                        _emit("enforcement", action="blocked", message=_msg, bigdata=True)
                        return {"blocked": True, "message": _msg}
        except Exception:
            pass

        # 2026-10-18（用户口径：先问清再动手）：grill 前置门禁
        try:
            note_grill_activity(es, tool_name, args)
            _gb = grill_gate(es, tool_name, args)
            if _gb:
                _emit("enforcement", action="blocked", message=_gb["message"], grill=True)
                return _gb
        except Exception:
            pass

        # 2026-10-09：执行位置 vs 审查位置对不上 → 软提醒（只提醒一次，不拦）
        _lm = _location_mismatch(es, tool_name, args)
        if _lm and getattr(es, "_loc_warned", "") != _lm[:60]:
            es._loc_warned = _lm[:60]
            _emit("enforcement", action="warning", message=_lm)

        # P3(2026-09-22): 意图确认门禁 —— 问完了没等到答复，不许开工
        _fg = _form_gate(es, tool_name, args)
        if _fg:
            _emit("enforcement", action="blocked", message=_fg["message"],
                  awaiting_form_id=_fg.get("awaiting_form_id", ""))
            return _fg

        # P4(2026-09-22): 代码修改模式门禁 —— 用户要的是"改代码"，不是"跑分析"
        _ce = code_edit_gate(es, tool_name, args)
        if _ce:
            _emit("enforcement", action="blocked", message=_ce["message"], code_edit=True)
            return _ce

        if tool_name == "skill_view":
            skill = _detect_tool_name(str(args))
            if skill:
                es.skills_loaded.add(skill)
                _emit("enforcement", action="skill_loaded", skill=skill, skills=list(es.skills_loaded))

        elif tool_name == "search_knowledge":
            es.knowledge_searched = True

        elif tool_name == "rail_review":
            phase = ""
            try:
                a = json.loads(str(args)) if isinstance(args, str) else args
                phase = a.get("phase", "")
            except Exception:
                pass
            if phase == "pre":
                es.rail_pre_done = True
            elif phase == "post":
                es.rail_post_done = True

        elif tool_name == "debate_analysis":
            es.debate_done = True
            # P2(2026-08-10): topic 级去重 — 记录辩论主题
            try:
                a = json.loads(str(args)) if isinstance(args, str) else args
                t = str(a.get("topic", ""))[:120]
            except Exception:
                t = ""
            if t:
                es.debated_topics.add(t)
            es.debate_count += 1
            _emit("enforcement", action="debate_started",
                  topic=t, count=es.debate_count,
                  message=f"💬 辩论 #{es.debate_count} 开始" + (f": {t}" if t else ""))

        elif _is_exec_call(tool_name, args) and tool_name != "terminal":
            # P2(2026-08-10): 失败重试信号 — execute_r/python/code 同命令重试计数
            # 参数键兼容 command/code/script（execute_r/python 用 code，terminal 用 command）
            _cmd = ""
            if isinstance(args, dict):
                _cmd = str(args.get("command") or args.get("code") or args.get("script") or "")
            else:
                _cmd = str(args)
            _key = _cmd.strip()[:120]
            es._exec_retries[_key] = es._exec_retries.get(_key, 0) + 1
            es._last_exec_error = False  # 由 complete 分支更新
            # 2026-08-22: 执行前检查——该代码已被判定"连续相同报错"，阻止盲目重试
            if _key in es._exec_error_repeat:
                _emit("enforcement", action="warning",
                      message=("🔄 这段代码此前已连续多次相同报错（已标记）。"
                               "请勿原样重试——先排查根因（环境/依赖/数据/编码），"
                               "修改代码或换方案后再执行。"))
            # P2-7(2026-08-10): 钩子① — 执行前辩论门控（P3 2026-10-12 按用户口径重写）。
            # 用户口径：**方案/脚本/设计类不辩**；生信类要"重要参数 + 已经出现离谱结果/冲突/
            # 连续失败"才在动手前先辩（证据链）；统计类先 grill 用户，最多 L1 且限时。
            if (es.analysis_level in ("analysis", "statistical") and es._exec_retries[_key] == 1
                    and not es.debated_topics):
                _checks = _param_checklist(_cmd)
                _b_kind = classify_topic_kind(_cmd)
                _b_sig = {"cmd": _cmd, "topic_kind": _b_kind,
                          "important_params": bool(_checks), "param_checklist": _checks}
                if _is_readonly_terminal(_cmd):
                    _b_sig["readonly"] = True
                _b_level, _b_reasons, _b_force = debate_gate(es, stage="before_script", signals=_b_sig)
                if _b_level < DEBATE_L1 and _b_reasons:
                    # 不辩也要说清楚为什么不辩（用户要求"分清楚情况"，不是静默跳过）
                    _emit("enforcement", action="info",
                          message=f"💬 执行前不辩论（{_DEBATE_KIND_LABELS.get(_b_kind, '')}）：{_b_reasons[0]}")
                if _b_level >= DEBATE_L1:
                    _req_tools, _req_text = _debate_require_payload(_b_kind, _b_level, _b_reasons)
                    _check_txt = ""
                    if _checks:
                        _check_txt = ("\n🔍 参数核查清单（找证据链时必逐项核查，用工具实查，不许猜）：\n"
                                      + "\n".join(f"  • {c}" for c in _checks))
                    _emit("enforcement", action="require",
                          level=DEBATE_LEVEL_NAMES[_b_level],
                          reasons=_b_reasons,
                          message=(f"💬 执行前辩论门控 → {DEBATE_LEVEL_NAMES[_b_level]}：{'；'.join(_b_reasons[:2])}。{_check_txt}{_req_text}"),
                          require=_req_tools or ["debate_analysis"])
            # 🔧 2026-08-22: 自进化门禁扩展 — execute_r/execute_python 完成后未 record_run
            # 时，下一次执行调用注入软提醒（不阻断执行，避免持久内核迭代被卡死）：
            # 提醒模型自检目标产物 → 已完成则 record_run 沉淀；未完成则【继续完成目标】。
            # （区别于 terminal 的硬阻断：execute 是迭代开发，硬卡会打断修复链；
            #   软提醒 = 持续督促"完成目标 → 沉淀"，绝不卡死；回合末有产物终检兜底）
            if es._pending_record and es.analysis_level != "chat":
                if not es._pending_record_warned:
                    es._pending_record_warned = True
                    _emit("enforcement", action="warning",
                          message=("⚠️ 上一步 execute 完成但未沉淀经验。请先检查目标产物是否已生成"
                                   "（文件存在、大小非空、内容正确）："
                                   "已生成 → 调用 skill_evolution(action='record_run') 沉淀；"
                                   "未生成 → 继续完成未完成的目标，全部完成后必须 record_run 沉淀再交付。"),
                          missing=["skill_evolution(record_run)"])
                # 不阻断：目标未完成时模型继续执行以完成目标；完成后 record_run 解除。

        elif tool_name in _DEBATE_HIGH_IMPACT_TOOLS:
            # P2(2026-09-22): 裁决硬约束优先 —— "不做 X 不许出 Y" 的 Y 就是这里
            _blk = _debate_block_gate(es, tool_name)
            if _blk:
                _emit("enforcement", action="blocked", message=_blk["message"],
                      debate_blocks=_blk.get("debate_blocks", []))
                return _blk
            # P2(2026-08-10): 高影响工具 — 记录待触发信号（强制 L2）
            es._pending_high_impact = True
            _emit("enforcement", action="info",
                  message=f"📌 高影响工具 {tool_name}：结论将入库/出报告 → 辩论强制 L2（不可降级）")

        elif tool_name == "terminal":
            # 🔧 bug③ 修复(2026-08-01): 合并自杀检测到主分支
            # 之前: 此处有独立的 elif terminal 分支(153行)在前面，导致这里整个不可达
            _cmd = str(args.get("command", "")) if isinstance(args, dict) else str(args)
            _cmd_lower = _cmd.lower()
            # 2026-08-14: 只读观察命令豁免（不触发 record_run 门禁 / rail_review(post) 要求）
            _ro = _is_readonly_terminal(_cmd)
            # P2(2026-08-10): terminal 也计入重试信号
            _key = _cmd.strip()[:100]
            es._exec_retries[_key] = es._exec_retries.get(_key, 0) + 1
            es._last_exec_error = False
            _danger = [
                ("taskkill", "/im python", "禁止 /IM python.exe，会把 MemOmics 自己杀掉！请用 /F /PID <具体PID>"),
                ("taskkill", "/im python3", "禁止 /IM python3.exe，会把 MemOmics 自己杀掉！请用 /F /PID <具体PID>"),
                ("killall", "python", "禁止 killall python！请用 kill <具体PID>"),
                ("pkill", "python", "禁止 pkill python！请用 kill <具体PID>"),
            ]
            for _tool, _pattern, _msg in _danger:
                if _tool in _cmd_lower and _pattern in _cmd_lower:
                    es.warnings.append(f"terminal: 自杀命令被拦截 - {_cmd[:80]}")
                    _emit("enforcement", action="blocked", message=f"⛔ 拦截：{_msg}")
                    # P0-1: 自杀命令硬阻断（一次性，不置位 es.blocked）
                    return {"blocked": True, "message": f"⛔ 拦截：{_msg}"}

            es.terminal_count += 1
            # 🔧 自进化门禁：上一个 terminal 完成后还没 record_run → 硬阻断（P0-1 接线）
            if es._pending_record and es.analysis_level != "chat" and not _ro:
                es.warnings.append(f"terminal#{es.terminal_count}: 上一步未完成 record_run")
                _emit("enforcement", action="blocked",
                      message="⛔ 上一步 terminal 完成后未记录经验！请先调用 skill_evolution(action='record_run') 沉淀经验，再执行下一步。",
                      require=["skill_evolution"])
                return {"blocked": True,
                        "message": "⛔ 上一步 terminal 完成后未记录经验（铁律）。"
                                   "请先调用 skill_evolution(action='record_run') 沉淀经验，再执行下一步。"}
            # 分析级操作且未加载 skill → 警告
            if es.analysis_level in ("analysis", "statistical") and not es.skills_loaded and not _ro:
                es.warnings.append(f"terminal#{es.terminal_count}: 未加载任何 skill")
                _emit("enforcement", action="warning",
                      message=f"⚠️ 未加载 skill 就执行 terminal。SOUL.md 铁律 #1 要求先 skill_view。",
                      missing=["skill_view"])

            # 分析级操作且未做 pre 审查 → 警告
            if es.analysis_level in ("analysis", "statistical") and not es.rail_pre_done and es.terminal_count == 1 and not _ro:
                es.warnings.append(f"terminal#{es.terminal_count}: 未执行 rail_review(pre)")
                _emit("enforcement", action="warning",
                      message=f"⚠️ 未执行 rail_review(pre) 审查。铁律 #3 要求分析前先审查。",
                      missing=["rail_review(pre)"])

            # 无知识库搜索 → 温和提醒
            if es.analysis_level in ("analysis",) and not es.knowledge_searched and es.terminal_count == 1 and not _ro:
                _emit("enforcement", action="info",
                      message="💡 建议先 search_knowledge() 获取参数推荐。铁律 #2。")

        # 2026-08-16: 状态有界化 — 长会话（35h+/数千次工具调用）历史/告警/重试表
        # 无限增长造成内存缓慢泄漏；只保留最近窗口
        if len(es.tool_history) > 200:
            es.tool_history = es.tool_history[-200:]
        if len(es.warnings) > 50:
            es.warnings = es.warnings[-50:]
        if len(es._exec_retries) > 100:
            es._exec_retries = dict(list(es._exec_retries.items())[-100:])

    def tool_complete_cb(tool_call_id: str, tool_name: str, args, result):
        """工具执行后拦截 — 自动触发后续动作"""
        es.tool_history.append({"tool": tool_name, "args": str(args)[:200], "time": time.time(), "phase": "complete"})
        if len(es.tool_history) > 200:
            es.tool_history = es.tool_history[-200:]

        if tool_name == "terminal" or (_is_exec_call(tool_name, args) and tool_name != "terminal"):
            es.rail_post_done = False
            # 2026-08-14: 只读观察命令不进入沉淀/审查门禁
            _cmd = ""
            if isinstance(args, dict):
                _cmd = str(args.get("command") or args.get("code") or args.get("script") or "")
            else:
                _cmd = str(args)
            _ro = _is_readonly_terminal(_cmd)
            # 保存结果用于后续参数提取
            es._last_terminal_result = str(result)[:1000] if result else ""
            # P2(2026-08-10): 报错信号 — 结果含错误标记
            _rstr = str(result).lower() if result else ""
            es._last_exec_error = any(k in _rstr for k in (
                "traceback", "error:", "exception", "exit code 1", "nonzero",
                "not found", '"status": "error"', '"status":"error"', "kernel error"))
            # 2026-08-22: 重复相同报错检测 + 乱码识别（用户需求：同一代码跑多次，
            # 要区分"相同的报错乱码"（盲目重试无效）和"正常执行"）
            if not _ro:
                _key2 = _cmd.strip()[:120] or tool_name
                _full_res = str(result) if result else ""
                _is_err = es._last_exec_error
                _is_garbage = _looks_like_encoding_garbage(_full_res)
                if _is_err:
                    _fp = _error_fingerprint(_full_res)
                    _hist = es._exec_error_hist.setdefault(_key2, [])
                    _hist.append(_fp)
                    if len(_hist) > 10:
                        _hist.pop(0)
                    # 连续 ≥3 次同一指纹 → 重复相同报错，提醒换思路
                    _tail = _hist[-3:]
                    if len(_tail) >= 3 and len(set(_tail)) == 1 and _tail[0] and _key2 not in es._exec_error_repeat:
                        es._exec_error_repeat.add(_key2)
                        _g_hint = ("。⚠️ 且输出疑似编码乱码（GBK/UTF-8 解码问题），"
                                   "请检查 PYTHONUTF8/编码设置或改用 UTF-8 读写" if _is_garbage else "")
                        _emit("enforcement", action="warning",
                              message=(f"🔄 检测到同一段代码连续 {len(_hist)} 次相同报错"
                                       f"（指纹 {_fp[:8]}）。盲目重试无效——请先排查根因："
                                       f"① 环境/依赖缺失 ② 数据路径/格式 ③ 换一种实现方案"
                                       f"{_g_hint}"))
                elif _is_garbage and _key2 not in es._exec_garbage_warned:
                    # 执行"成功"但输出是乱码 → 单独提示编码问题（不算失败）
                    es._exec_garbage_warned.add(_key2)
                    _emit("enforcement", action="info",
                          message=("⚠️ 该代码执行完成但输出疑似编码乱码（GBK/UTF-8 解码问题）。"
                                   "结果可能被误读——请确认输出编码（PYTHONUTF8=1 / utf-8-sig / 文件编码）后再交付。"))
            # 设置 pending 标记：所有非闲聊级别都需要 record
            if es.analysis_level != "chat" and not _ro:
                es._pending_record = True

            # 自动提示：需要 rail_review(post)
            if es.analysis_level in ("analysis", "statistical", "lightweight") and not _ro:
                _emit("enforcement", action="require",
                      message="🔍 terminal 执行完毕。请先调用 skill_evolution(action='record_run') 沉淀本次运行经验（否则下一个 terminal 会被铁律24拦截），再调用 rail_review(post) 进行执行后审查。",
                      require=["rail_review(post)"])

        elif tool_name == "rail_review":
            # rail_review 完成后同步状态
            try:
                r = json.loads(str(result)) if isinstance(result, str) else result
                if isinstance(r, dict):
                    phase = ""
                    try:
                        a = json.loads(str(args)) if isinstance(args, str) else args
                        phase = a.get("phase", "")
                    except Exception:
                        pass
                    if phase == "pre" or r.get("phase") == "pre":
                        es.rail_pre_done = True
                        # 2026-10-09：记住这次审查是按哪个位置审的（本机/集群/云），
                        # 执行时位置对不上就软提醒——本地包清单不该拿来判集群任务
                        es.rail_pre_location = str(r.get("location") or r.get("env_source") or "")
                        es.rail_pre_line = str(r.get("location_line") or "")
                        should_proceed = r.get("should_proceed", True)
                        if not should_proceed:
                            issues = r.get("issues", [])
                            # 2026-10-18（风险分级）：低风险小规模任务，rail(pre) 的问题不硬阻断，
                            # 只记录+提示 —— 否则跑个 12 行数据的均值也要先过重审查，用户嫌"繁琐"。
                            _skip_block = False
                            try:
                                from webui.runtime import risk_tier as _rt2
                                _skip_block = not _rt2.rail_block_allowed(_rt2.current_tier(es))
                            except Exception:
                                _skip_block = False
                            if _skip_block:
                                _emit("enforcement", action="notice",
                                      message=("🛡️ 风险分级：低风险小规模任务，rail_review(pre) 的问题记为提示"
                                               "（不硬阻断）：" + "; ".join(str(x) for x in issues[:3])))
                                es.rail_pre_done = True
                                es.blocked = False
                            es.blocked = es.blocked if _skip_block else True  # P0-1: 硬阻断接线 — 后续执行类工具被拦
                            es._block_kind = "rail_pre"
                            es._block_reason = (f"🛡️ rail_review(pre) 发现问题: {'; '.join(issues[:3])}。"
                                                "请修复后重新 rail_review(phase='pre') 通过再执行。")
                            _emit("enforcement", action="blocked", message=es._block_reason)
                        else:
                            # 2026-08-16: 任一阶段审查通过即解除硬阻断。此前只解除同阶段
                            # （elif es._block_kind == "rail_pre"）——post 失败残留时重跑 pre
                            # 通过也解不开 → execute_r/terminal 被永久锁死（12G Seurat 读取案例）
                            es.blocked = False
                            es._block_kind = ""
                            es._block_reason = ""
                            es._blocked_attempts = 0
                    elif phase == "post" or r.get("phase") == "post":
                        es.rail_post_done = True
                        # 🔧 bug② 修复(2026-08-01): rail_review 返回键是 "passed" 不是 "should_proceed"
                        # 之前: r.get("should_proceed", True) 永远默认True → 审查失败也被当通过
                        should_proceed = r.get("passed", r.get("should_proceed", True))
                        if not should_proceed:
                            issues = r.get("issues", [])
                            # 2026-08-17 用户要求：后审查不硬阻断——产出已存在，
                            # 达标就放行交付；不达标给修复指引让 agent 继续解决问题，
                            # 绝不 es.blocked 拦死执行工具（修复产出本身就需要执行工具）。
                            es._block_reason = (f"🛡️ rail_review(post) 发现问题: {'; '.join(issues[:3])}。"
                                                "请修复后重新 rail_review(phase='post') 通过再交付。")
                            _emit("enforcement", action="require", require=["rail_review"],
                                  message=(es._block_reason
                                           + "（不拦截执行工具：直接修复问题重新产出，再跑 post 审查）"))
                        else:
                            # 2026-08-16: 任一阶段审查通过即解除硬阻断（对称解绑，防死锁残留）
                            es.blocked = False
                            es._block_kind = ""
                            es._block_reason = ""
                            es._blocked_attempts = 0
            except Exception:
                pass

            # rail_review(post) 完成后 → 自动 record_run + 触发 debate
            if es.rail_post_done:
                # 自动标题总结钩子（分析完成 = 项目进度里程碑 → server 侧后台总结会话主题）
                if _title_summary_hook:
                    try:
                        _title_summary_hook(sid)
                    except Exception:
                        pass
                # 自动记录成功运行到 skill（自进化）— 扩展到所有非闲聊级别
                if es.analysis_level != "chat" and es.skills_loaded:
                    try:
                        import importlib.util as _iu2
                        import os as _os2, re as _re
                        _sep2 = _iu2.spec_from_file_location(
                            "skill_evolution",
                            _os2.path.join(_os2.path.dirname(_os2.path.abspath(__file__)),
                                      "..", "memomics", "bio_tools", "skill_evolution.py")
                        )
                        _se = _iu2.module_from_spec(_sep2)
                        _sep2.loader.exec_module(_se)
                        # 尝试从 terminal 输出提取参数
                        _params = "{}"
                        _species, _tissue, _direction = "", "", ""
                        _tr = es._last_terminal_result.lower()
                        for _kw, _f in [("human", "human"), ("mouse", "mouse"), ("monkey", "monkey"), ("macaque", "macaque")]:
                            if _kw in _tr: _species = _f; break
                        for _kw, _f in [("muscle", "muscle"), ("brain", "brain"), ("liver", "liver"), ("blood", "blood"), ("lung", "lung")]:
                            if _kw in _tr: _tissue = _f; break
                        _m = _re.search(r'(\d+)\s*(?:cells|细胞)', _tr)
                        if _m: _params = f'{{"cell_count": {_m.group(1)}}}'

                        # P1-11(2026-08-13): query_logs 接线 — 查历史 proven 参数兜底
                        if _params == "{}":
                            try:
                                _ql = _se.skill_evolution(action="query_logs",
                                                          skill_name=es.skills_loaded[0])
                                if isinstance(_ql, str):
                                    _ql = json.loads(_ql) if _ql.strip().startswith("{") else {}
                                if isinstance(_ql, dict):
                                    _proven = _ql.get("proven_runs", []) or []
                                    for _pr in _proven:
                                        if isinstance(_pr, dict) and _pr.get("params_used"):
                                            _params = str(_pr["params_used"])
                                            break
                            except Exception:
                                pass

                        # P1-11(2026-08-13): record_error 接线 — 本步骤有执行错误 →
                        # 沉淀错误经验（每会话限 2 次防刷屏）
                        if es._last_exec_error and es._error_recorded < 2:
                            es._error_recorded += 1
                            try:
                                _err_snip = (es._last_terminal_result or "")[-800:]
                                _se.skill_evolution(
                                    action="record_error",
                                    skill_name=es.skills_loaded[0],
                                    error_message=_err_snip,
                                    error_type="execution",
                                    root_cause="see error message",
                                    fix_applied="",
                                    species=_species, tissue=_tissue,
                                    direction=_direction,
                                    script_name=f"session_{sid}_terminal{es.terminal_count}",
                                )
                            except Exception:
                                pass

                        # P1-11(2026-08-13): score 去硬编码 — 自动记录未经用户批准，
                        # user score=0（不假装认可），auto_score 由 rail_review 提供（无则 0）
                        for _sk in es.skills_loaded:
                            _se.skill_evolution(
                                action="record_run",
                                skill_name=_sk,
                                script_name=f"session_{sid}_terminal{es.terminal_count}",
                                species=_species, tissue=_tissue, direction=_direction,
                                params_used=_params,
                                result_summary=f"rail_review(post) passed. session={sid}",
                                score=0, approved=False, auto_score=0.0
                            )
                        _emit("enforcement", action="recorded",
                              message=f"🧬 自动 record_run: {', '.join(es.skills_loaded)} species={_species} tissue={_tissue}")
                        es._pending_record = False  # 已记录，清除标记
                    except Exception as _e:
                        _emit("enforcement", action="warning",
                              message=f"⚠️ record_run 失败: {_e}")
                # 触发 debate（P3 2026-10-12：按用户口径只在这几种情况辩）
                _g_topic = (getattr(es, "topic_hint", "") or str(es._last_terminal_result or "")[:200])
                _g_kind = classify_topic_kind(_g_topic)
                _g_signals = {
                    "high_impact": getattr(es, "_pending_high_impact", False),
                    "failed_retries": max(es._exec_retries.values()) if es._exec_retries else 0,
                    "last_error": es._last_exec_error,
                    "conflict": not should_proceed if es.rail_post_done else False,
                    "uncertainty": False,
                    # 用户口径的关键两票：题目类型 + "结果离谱/与预期不符"
                    "topic_kind": _g_kind,
                    "important_params": bool(_param_checklist(str(es._last_terminal_result or ""))),
                    "deviation": looks_absurd(str(es._last_terminal_result or "")),
                }
                _g_level, _g_reasons, _g_force = debate_gate(es, stage="after_script", signals=_g_signals)
                es._pending_high_impact = False
                # 钩子③ 结论辩论（P3 2026-10-12 重写）：结论阶段不再"无条件 L1"，
                # 只有 生信+重要参数+结论对不上 / 统计+结果离谱 / 其它硬信号 才辩；
                # 方案/脚本/图 一律不辩；超预算非强制直接停（见 debate_gate ⑦）。
                _c_level, _c_reasons, _c_force = debate_gate(es, stage="conclusion", signals=_g_signals)
                if _c_level > _g_level:
                    _g_level, _g_reasons, _g_force = _c_level, _c_reasons, _c_force
                if _g_level >= DEBATE_L1:
                    _mode_hint = {
                        # C2(2026-08-11): L1 轻量采样 / L2 完整 8 角色，都默认单模型上下文切断
                        DEBATE_L1: "level='L1'（轻量采样辩论，成本约 1/3，限时 180s）",
                        DEBATE_L2: "level='L2'（完整 8 角色证据链辩论）",
                    }[_g_level]
                    _req_tools, _req_text = _debate_require_payload(_g_kind, _g_level, _g_reasons)
                    _emit("enforcement", action="require",
                          level=DEBATE_LEVEL_NAMES[_g_level],
                          reasons=_g_reasons,
                          message=(f"💬 辩论门控（{_DEBATE_KIND_LABELS.get(_g_kind, '')}）→ {DEBATE_LEVEL_NAMES[_g_level]}："
                                   f"{'；'.join(_g_reasons[:2])}。{_mode_hint}。{_req_text}"),
                          require=_req_tools or ["debate_analysis"])
                elif _g_reasons:
                    # 用户要求可见：为什么这次不辩
                    _emit("enforcement", action="info",
                          message=f"💬 不辩论（{_DEBATE_KIND_LABELS.get(_g_kind, '')}）：{_g_reasons[0]}")

        elif tool_name == "debate_analysis":
            es.debate_done = True
            # 保存辩论结论
            _save_debate_conclusion(es, result, args)
            # P2(2026-09-22): 裁决 → 行动方案 + 待办（辩论必须驱动下一步）
            _plan = _ingest_debate_plan(es, result)
            if _plan:
                _n = len(es.debate_todos)
                _emit("enforcement", action="plan",
                      decision=_plan.get("decision", ""),
                      next_actions=[t.get("title") for t in es.debate_todos],
                      fallback=(_plan.get("fallback") or {}).get("path", ""),
                      decision_source=_plan.get("decision_source", ""),
                      message=("🎯 裁决行动方案：" + (_plan.get("decision") or "(无 decision)")[:200]
                               + (f"；已生成 {_n} 条会话待办" if _n else "")))
            # C3(2026-08-11): token 用量回收 — 辩论结果的 usage 累加到会话级预算
            try:
                _r = json.loads(result) if isinstance(result, str) else result
                _u = (_r.get("usage") or {}).get("total", 0) if isinstance(_r, dict) else 0
                es.token_used += int(_u or 0)
            except Exception:
                pass

        elif tool_name == "skill_evolution":
            # P0-1(2026-08-13): agent 手动调 skill_evolution(record_run) → 解除 pending_record 门禁
            try:
                a = json.loads(str(args)) if isinstance(args, str) else args
                if isinstance(a, dict) and a.get("action") in ("record_run", "record_success"):
                    es._pending_record = False
                    es._pending_record_warned = False  # 2026-08-22: 沉淀完成 → 软拦截计数重置
            except Exception:
                pass
    def tool_progress_cb(event_type: str, **kwargs):
        """工具进度回调 — 用于心跳和状态同步"""
        if event_type == "tool.started":
            pass  # tool_start_cb 已处理
        elif event_type == "tool.completed":
            pass  # tool_complete_cb 已处理

    return {
        "tool_start_callback": tool_start_cb,
        "tool_complete_callback": tool_complete_cb,
        "tool_progress_callback": tool_progress_cb,
    }


# ==================== P2(2026-09-22): 裁决驱动下一步 ====================
# 用户原话："辩论结果有用于下一步的进程吗？没有，辩论什么？"
# 做法：裁决的 next_actions 落成会话待办（前端可见、可被标记完成），
# 其中的 blocks 成为硬约束：待办没完成前，高影响产物（入库/报告/结论）被拦住。

def _ingest_debate_plan(es: EnforcementState, result) -> dict:
    """解析辩论结果 → 存下行动方案 + 生成待办（owner=ai 的才生成）。"""
    try:
        r = result
        if isinstance(r, str):
            try:
                r = json.loads(r)
            except Exception:
                return {}
        if not isinstance(r, dict):
            return {}
        actions = r.get("next_actions") if isinstance(r.get("next_actions"), list) else []
        plan = {
            "topic": str(r.get("topic") or "")[:200],
            "verdict": str(r.get("verdict") or ""),
            "confidence": str(r.get("confidence") or ""),
            "level": str(r.get("level") or ""),
            "decision": str(r.get("decision") or ""),
            "next_actions": actions,
            "fallback": r.get("fallback") if isinstance(r.get("fallback"), dict) else {},
            "reopen_condition": str(r.get("reopen_condition") or ""),
            "decision_source": str(r.get("decision_source") or ""),
            "decision_warnings": r.get("decision_warnings") if isinstance(r.get("decision_warnings"), list) else [],
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        es.debate_plan = plan
        todos = []
        for i, a in enumerate(actions[:6]):
            if not isinstance(a, dict):
                continue
            if str(a.get("owner") or "ai").lower() == "user":
                continue  # 需要用户提供的东西不生成待办（那是提问，不是待办）
            blocks = a.get("blocks")
            if isinstance(blocks, str):
                blocks = [blocks]
            if not isinstance(blocks, list):
                blocks = []
            todos.append({
                "id": f"debate_todo_{es.debate_count}_{i}",
                "title": str(a.get("action") or "")[:200],
                "status": "pending",
                "blocks": [str(b) for b in blocks if str(b).strip()],
                "expected": str(a.get("expected") or "")[:200],
                "from_debate": plan["ts"],
            })
        # 有 blocks 的排前面（硬约束优先）
        todos.sort(key=lambda t: 0 if t["blocks"] else 1)
        es.debate_todos = [t for t in todos if t["title"]]
        return plan
    except Exception as e:
        logger.warning(f"_ingest_debate_plan failed: {e}")
        return {}


def sync_debate_todos(es: EnforcementState, todos) -> int:
    """用 agent 的待办列表回写 es.debate_todos 的完成状态（返回变化条数）。"""
    try:
        live = {}
        for t in (todos or []):
            if not isinstance(t, dict):
                continue
            _id = str(t.get("id") or "")
            _tt = str(t.get("title") or t.get("content") or "").strip()
            _st = str(t.get("status") or "pending")
            if _id:
                live[_id] = _st
            if _tt:
                live[_tt] = _st
        n = 0
        for dt in getattr(es, "debate_todos", []) or []:
            st = live.get(str(dt.get("id"))) or live.get(str(dt.get("title")))
            if st and st != dt.get("status"):
                dt["status"] = st
                n += 1
        return n
    except Exception:
        return 0


def pending_debate_blocks(es: EnforcementState) -> list:
    """未完成的、带硬约束的裁决待办。"""
    out = []
    for t in getattr(es, "debate_todos", []) or []:
        if t.get("status") in ("completed", "cancelled"):
            continue
        if t.get("blocks"):
            out.append(t)
    return out


# ==================== P3(2026-09-22): 意图确认弹窗门禁 ====================
# 用户原话："在执行任务之前，先理解用户的意图，grill 用户把不清楚的问题问明白，
# 做出弹窗供用户勾选，理解意图之后再执行。"
# 机制：ask_user 弹出表单 → 未答复前执行类工具被拦 → 用户勾选提交（或直接回消息）
# 即解除。这保证"先问清楚再动手"不是靠模型自觉，而是有硬门禁兜底。

def form_pending(es: EnforcementState) -> bool:
    """是否正在等用户回答意图确认表单（超时视为失效）。"""
    if not getattr(es, "awaiting_form_id", ""):
        return False
    _ts = float(getattr(es, "awaiting_form_ts", 0.0) or 0.0)
    if _ts and (time.time() - _ts) > _FORM_PENDING_TTL:
        return False
    return True


def arm_intent_confirm(es: EnforcementState, reason: str = "") -> None:
    """P3: 高代价任务开工前预置"意图未确认"门禁（不依赖模型自觉）。

    与 form_pending 的区别：form_pending 表示"表单已经发出去了"；本函数表示"服务器
    判定本轮属于高代价任务（分析/集群投递/入库/报告）且意图没交代清楚"——在模型还没
    来得及弹表单时就把执行类工具锁上，防止"提示词写了但模型直接开跑"。
    """
    es.intent_confirm = True
    es.intent_confirm_reason = str(reason or "")[:300]
    es.intent_confirm_ts = time.time()


def intent_confirm_pending(es: EnforcementState) -> bool:
    """预置门禁是否生效（超时自动失效，避免用户走开锁死会话）。"""
    if not getattr(es, "intent_confirm", False):
        return False
    _ts = float(getattr(es, "intent_confirm_ts", 0.0) or 0.0)
    if _ts and (time.time() - _ts) > _FORM_PENDING_TTL:
        return False
    return True


def clear_intent_confirm(es: EnforcementState) -> bool:
    """解除预置门禁（用户答复/发新消息/表单送达即解除）。"""
    _was = bool(getattr(es, "intent_confirm", False))
    es.intent_confirm = False
    es.intent_confirm_reason = ""
    es.intent_confirm_ts = 0.0
    return _was


def set_awaiting_form(es: EnforcementState, form_id: str, question: str = "") -> None:
    es.awaiting_form_id = str(form_id or "")
    es.awaiting_form_question = str(question or "")[:300]
    es.awaiting_form_ts = time.time()
    # 表单真的发出去了 → 预置门禁由"未问"升级为"已问待答"（同一把锁，不叠加）
    clear_intent_confirm(es)


def clear_awaiting_form(es: EnforcementState, form_id: str = "", answer: dict = None) -> bool:
    """用户答复/发新消息 → 解除门禁。返回是否真的解除了。"""
    if not getattr(es, "awaiting_form_id", ""):
        return False
    if form_id and str(form_id) != str(es.awaiting_form_id):
        return False
    if isinstance(answer, dict):
        try:
            es.form_answers.append({**answer, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            del es.form_answers[:-20]
        except Exception:
            pass
    es.awaiting_form_id = ""
    es.awaiting_form_question = ""
    es.awaiting_form_ts = 0.0
    clear_intent_confirm(es)
    return True


def _form_gate(es: EnforcementState, tool_name: str, args=None):
    """意图未确认 → 拦下执行类工具（None=放行）。

    覆盖：执行代码类 + 高影响产物类 + 集群投递（remote_cluster 的 run/submit；
    check/status/push/pull 等只读运维动作放行，避免连状态都查不了）。
    """
    _asked = form_pending(es)
    _armed = intent_confirm_pending(es)
    if not (_asked or _armed):
        return None
    _hit = tool_name in _FORM_GATED_TOOLS
    if not _hit and tool_name == _REMOTE_CLUSTER_TOOL:
        _act = str(_args_as_dict(args).get("action") or "").strip().lower()
        _hit = _act in _REMOTE_CLUSTER_EXEC_ACTIONS
    if not _hit:
        return None
    es.form_block_hits = int(getattr(es, "form_block_hits", 0)) + 1
    if _asked:
        _msg = chr(10).join([
            "⛔ 意图还没确认，先别执行：你已经用 ask_user 问了用户「%s」，但用户还没回答（或还没提交勾选）。"
            % ((getattr(es, "awaiting_form_question", "") or "?")[:120],),
            "现在必须做的：结束本回合等用户答复。不要再尝试调用 %s 或任何执行/产物工具。" % (tool_name,),
            "解除方式：① 用户在确认弹窗里勾选并提交；② 用户直接在输入框回复（也算答复）；"
            "③ 30 分钟内无人答复则门禁自动失效。",
        ])
    else:
        _reason = str(getattr(es, "intent_confirm_reason", "") or "")[:120]
        _msg = chr(10).join([
            "⛔ 开工前意图没确认，先别执行：本轮属于高代价任务（分析/集群投递/结果入库/出报告），"
            "但目标/交付物/关键参数还没跟用户对齐" + (("（%s）" % _reason) if _reason else "") + "。",
            "现在必须做的：立刻调 ask_user 弹「确认表单」——question 写清要确认什么，"
            "options 给可勾选项（对象形式 label/desc/recommended），多件事用 multi_select=true，"
            "kind=\"intent\"；然后结束本回合等用户勾选。不要写代码、不要跑脚本、不要出报告。",
            "解除方式：① 用户提交勾选；② 用户直接回消息（也算确认）；③ 30 分钟无答复自动失效。",
        ])
    return {
        "blocked": True,
        "message": _msg,
        "awaiting_form_id": es.awaiting_form_id,
        "intent_confirm": bool(_armed),
    }


# ==================== P4(2026-09-22): 代码修改模式门禁 ====================
# 用户原话："如果我给一些脚本和代码，让 MemOmics 自己帮我改一下、完善一下，
#           它会不会自己跑去执行呢？什么时候执行脚本，什么时候只是改代码呢？
#           如果只是修改代码，能不能直接给修改后的代码呢？"
# 机制：服务器判定本轮是"改代码"（有代码/脚本 + 有改动动词，且用户没说要跑）→ 置位 code_edit：
#   · 拦：execute_r / execute_python / execute_code / run_script / 集群 run,submit /
#         terminal 的非只读命令（真在跑代码的）
#   · 放：读文件、写文件、给代码（cat/findstr 读用户脚本、write 落盘改好的代码都不受影响）
#   · 要跑必须用户点头：弹窗勾"用数据验证" / 用户直接回消息说要跑 / 30 分钟 TTL
# 语义与 P3 一致，但"答复"不默认解锁 —— 用户选"只要代码"时锁继续生效（这是他的本意）。

_CODE_EDIT_TTL = _FORM_PENDING_TTL  # 30 分钟无后续自动失效，不永久锁死
_CODE_EDIT_GATED_TOOLS = {"execute_r", "execute_python", "execute_code", "run_script"}


def arm_code_edit(es: EnforcementState, reason: str = "", data=None) -> bool:
    # 2026-10-21 用户要求：不再用"代码修改模式"锁 —— 按语义判断即可。
    return False
    """进入代码修改模式：只改不跑。data=记忆里可供验证的数据路径（可空）。"""
    es.code_edit = True
    es.code_edit_verify = False          # 新一轮请求 = 重新决策（不沿用上次的同意）
    es.code_edit_reason = str(reason or "")[:300]
    es.code_edit_ts = time.time()
    if data is not None:
        es.code_edit_data = [str(x)[:200] for x in list(data)[:5]]
    return True


def code_edit_pending(es: EnforcementState) -> bool:
    """代码修改模式是否仍在拦执行（超时 → False）。

    注意：用户同意"用数据验证"走 clear_code_edit()，锁本身会被清掉；
    code_edit_verify 只是"本轮是否获准"的标记（审计用），不参与判定 ——
    否则一次同意就等于本会话永久放行，违背"什么时候跑、什么时候只改"的可预测性。
    """
    if not getattr(es, "code_edit", False):
        return False
    _ts = float(getattr(es, "code_edit_ts", 0.0) or 0.0)
    if _ts and (time.time() - _ts) > _CODE_EDIT_TTL:
        return False
    return True


def clear_code_edit(es: EnforcementState, grant_exec: bool = False) -> bool:
    """退出代码修改模式。grant_exec=True 表示用户同意执行（本会话后续不再拦）。"""
    _was = bool(getattr(es, "code_edit", False))
    es.code_edit = False
    es.code_edit_reason = ""
    es.code_edit_ts = 0.0
    if grant_exec:
        es.code_edit_verify = True
    return _was


def code_edit_gate(es: EnforcementState, tool_name: str, args=None):
    # 2026-10-21 用户要求：去掉该锁，一律放行
    return None
    """代码修改模式：拦执行类工具（None=放行）。"""
    if not code_edit_pending(es):
        return None
    _d = _args_as_dict(args)
    _hit = False
    if tool_name == "terminal":
        # 只读命令放行：读用户脚本、看目录、grep 报错都必须能做
        _hit = not _is_readonly_terminal(str(_d.get("command") or ""))
    elif tool_name in _CODE_EDIT_GATED_TOOLS:
        _hit = True
    elif tool_name == _REMOTE_CLUSTER_TOOL:
        _hit = str(_d.get("action") or "").strip().lower() in _REMOTE_CLUSTER_EXEC_ACTIONS
    if not _hit:
        return None
    es.code_edit_block_hits = int(getattr(es, "code_edit_block_hits", 0)) + 1
    _data = getattr(es, "code_edit_data", []) or []
    _lines = [
        "⛔ 代码修改模式：用户要的是「改代码」，不是「跑分析」，现在别执行。",
        "本轮判定依据：用户给了代码/脚本并要求修改，但没说要跑（%s）。" % (
            str(getattr(es, "code_edit_reason", "") or "改代码")[:120],),
        "现在该做的：把修改后的【完整代码】直接写出来（回复里给代码块；需要落盘就写到 "
        "results/<sid>/scripts/），逐条说明改了什么、为什么；用户脚本是基准，不许重写他的风格。",
        "被拦的工具：%s。" % (tool_name,),
    ]
    if _data:
        _lines.append("记忆里有用户的数据可用于验证：%s" % ("；".join(str(x) for x in _data[:3]),))
    _lines.append("解除方式：① ask_user 问用户「要不要用你的数据跑一遍验证」，用户勾选同意；"
                  "② 用户直接回消息说要跑/验证/测试；③ 30 分钟无后续自动失效。")
    return {"blocked": True, "message": chr(10).join(_lines), "code_edit": True}


def _debate_block_gate(es: EnforcementState, tool_name: str):
    """P2: 裁决 blocks 硬约束 —— 拦住高影响产物，返回 block dict（None=放行）。

    语义：辩论裁决写了"不做 X 就不许出 Y" → Y 就是入库/报告/结论产物。
    解除方式三条（都不依赖模型"猜"）：完成待办并标记完成 / 再辩一次覆盖 /
    把待办标记 cancelled（用户明确要求跳过时）。
    """
    if not getattr(es, "debate_enforce_blocks", True):
        return None
    pend = pending_debate_blocks(es)
    if not pend:
        return None
    es._debate_block_hits = getattr(es, "_debate_block_hits", 0) + 1
    lines = []
    for t in pend[:3]:
        lines.append("  • [%s] %s  ← 不做则必须停：%s"
                     % (t.get("id", ""), t.get("title", ""),
                        "；".join(str(b) for b in (t.get("blocks") or [])[:3])))
    msg = ("⛔ 辩论裁决的硬约束还没满足，本次 %s 被拦下（裁决要求先完成下列动作才允许产出高影响结果）：\n"
           % tool_name + "\n".join(lines) +
           "\n解除方式（三选一）：① 先完成该动作，再用 todo 工具把它标记 status='completed'；"
           "② 再调一次 debate_analysis（新裁决覆盖旧约束）；"
           "③ 用户明确要求跳过时，把该待办标记 status='cancelled' 后重试。")
    return {"blocked": True, "message": msg, "debate_blocks": [t.get("id") for t in pend]}


def _save_debate_conclusion(es: EnforcementState, result, args):
    """保存辩论结论到 conclusions/ 目录"""
    cdir = es.get_conclusions_dir()
    if not cdir:
        return
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"debate_{ts}.json"
        fpath = os.path.join(cdir, fname)

        # 提取关键信息
        skill_name = ""
        try:
            if isinstance(args, str):
                a = json.loads(args)
                skill_name = a.get("module_id", a.get("skill", ""))
        except Exception:
            pass

        conclusion = {
            "session_id": es.session_id,
            "timestamp": datetime.now().isoformat(),
            "skill": skill_name,
            "terminal_count": es.terminal_count,
            "skills_loaded": list(es.skills_loaded),
            "result_summary": str(result)[:2000] if result else "",
        }

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(conclusion, f, ensure_ascii=False, indent=2)

        # 同时保存纯文本摘要
        txt_path = fpath.replace(".json", ".md")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"# 辩论结论 — {skill_name or '分析'}\n\n")
            f.write(f"- 会话: {es.session_id}\n")
            f.write(f"- 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"- 已加载 Skill: {', '.join(es.skills_loaded) or '无'}\n")
            f.write(f"- Terminal 执行次数: {es.terminal_count}\n")
            f.write(f"- 审查: pre={'✅' if es.rail_pre_done else '❌'} / post={'✅' if es.rail_post_done else '❌'}\n")
            f.write(f"\n## 辩论结果\n\n```\n{str(result)[:3000]}\n```\n")

    except Exception as e:
        print(f"[Enforcement] 保存辩论结论失败: {e}")


def get_enforcement_report(session_id: str) -> dict:
    """生成强制执行报告"""
    es = get_enforcement(session_id)
    return {
        "session_id": session_id,
        "analysis_level": es.analysis_level,
        "skills_loaded": list(es.skills_loaded),
        "knowledge_searched": es.knowledge_searched,
        "rail_pre_done": es.rail_pre_done,
        "rail_post_done": es.rail_post_done,
        "debate_done": es.debate_done,
        # 裁决待办的实时状态 + 还卡着几道硬门禁。不暴露这两个字段的话，用户报
        # 「待办做完了也不划掉」时只能靠猜（2026-09-30 那次就是）。形状与 to_dict 一致。
        "debate_todos": [{"id": t.get("id"), "title": t.get("title"),
                          "status": t.get("status"), "blocks": t.get("blocks")}
                         for t in (getattr(es, "debate_todos", []) or [])],
        "debate_blocks_pending": len(pending_debate_blocks(es)),
        "terminal_count": es.terminal_count,
        "warnings": es.warnings,
        "conclusions_dir": es.conclusions_dir,
        "checklist": {
            "skill_view": bool(es.skills_loaded),
            "search_knowledge": es.knowledge_searched,
            "rail_review(pre)": es.rail_pre_done,
            "rail_review(post)": es.rail_post_done,
            "debate_analysis": es.debate_done,
        },
    }
