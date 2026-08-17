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

# 高影响工具：命中即强制 L2（入库/报告/结论产物，不可降级）
_DEBATE_HIGH_IMPACT_TOOLS = {
    "generate_report", "add_figure", "save_knowledge", "submit_skill",
    "knowledge_write", "conclusion_save", "write_report", "deliver",
}
# 失败信号工具（terminal/脚本执行，重试≥2 或报错 → 升级 L2）
_DEBATE_EXEC_TOOLS = {"terminal", "execute_r", "execute_python", "execute_code", "run_script"}

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


def debate_gate(es: "EnforcementState", stage: str = "conclusion",
                signals: dict = None) -> tuple:
    """三级门控判定 — 什么时候该辩论。

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

    if es.analysis_level in ("chat", "lightweight"):
        return DEBATE_L0, ["chat/lightweight 级：无分析对象，跳过辩论"], force

    impact = bool(signals.get("high_impact"))
    if impact:
        reasons.append("高影响（入库/报告/结论产物）：强制 L2")
        level = DEBATE_L2
        force = True

    if not force:
        if es.analysis_level == "statistical":
            level = DEBATE_L1
            reasons.append("statistical 级：默认 L1 轻量辩论")
        else:  # analysis
            failures = int(signals.get("failed_retries", 0)) + (1 if signals.get("last_error") else 0)
            conflict = bool(signals.get("conflict"))
            uncertainty = bool(signals.get("uncertainty"))
            if failures >= 2:
                level = DEBATE_L2
                reasons.append(f"失败重试≥2（retries={failures}）：升级 L2")
            elif conflict:
                level = DEBATE_L2
                reasons.append("rail_review(post) 未通过/结果冲突：升级 L2")
            elif stage == "conclusion":
                level = DEBATE_L2
                reasons.append("analysis 级结论合成前：默认 L2")
            elif uncertainty:
                level = DEBATE_L2
                reasons.append("高不确定性：升级 L2")
            else:
                level = DEBATE_L1
                reasons.append("analysis 级脚本设计/执行后：L1 轻量辩论")

    # 预算护栏：单会话辩论次数上限（config debate.budget，默认 3）
    # 强制（高影响）不降级；超预算的非强制降为 L1 并提示
    if not force and level == DEBATE_L2 and es.debate_count >= es.debate_budget:
        level = DEBATE_L1
        reasons.append(f"预算护栏：本会话已辩论 {es.debate_count} 次 ≥ budget={es.debate_budget}，降级 L1")

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
        self.debate_done: bool = False  # 🔧 P2(2026-08-10): 保留兼容字段，新逻辑用 debated_topics
        self.debated_topics: set = set()  # P2: topic 级去重 — 同一主题只辩一次
        self.debate_count: int = 0  # P2: 单会话辩论次数（预算护栏）
        self.debate_budget: int = 3  # P2: 预算上限（config debate.budget 可覆盖）
        self.token_used: int = 0  # C3(2026-08-11): 本会话辩论累计 token（usage 统计）
        self.token_budget: int = 0  # C3: token 预算上限（config debate.token_budget，0=不限）
        self._pending_high_impact: bool = False  # P2: 高影响工具已调用，待门控消费
        self.analysis_level: str = "chat"
        self._pending_record: bool = False  # 上一步 terminal 完成后还没 record
        self._error_recorded: int = 0  # P1-11: 本会话自动 record_error 次数（限 2 防刷屏）
        self._block_kind: str = ""  # P0-1(2026-08-13): 阻断原因类别 rail_pre/rail_post/""
        self._block_reason: str = ""  # P0-1: 阻断原因描述（注入被拦工具的错误消息）
        self._last_terminal_result: str = ""  # 最近 terminal 输出（提取参数用）
        self._exec_retries: dict = {}  # P2: 命令/脚本重试计数 {cmd: n}
        self._last_exec_error: bool = False  # P2: 最近一次执行是否报错
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
            "debate_done": self.debate_done,
            "debated_topics": list(self.debated_topics),  # P2
            "debate_count": self.debate_count,  # P2
            "debate_budget": self.debate_budget,  # P2
            "token_used": self.token_used,  # C3
            "token_budget": self.token_budget,  # C3
            "analysis_level": self.analysis_level,
            "terminal_count": self.terminal_count,
            "warnings": self.warnings[-5:],
        }


# === 全局会话级状态存储 ===
_session_enforcement: dict = {}


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
    return was


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
        _cfg_p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hermes_home", "config.yaml")
        if os.path.exists(_cfg_p):
            _d = _y.safe_load(open(_cfg_p, encoding="utf-8")) or {}
            _b = ((_d.get("debate") or {}).get("budget")) or None
            if isinstance(_b, int) and _b > 0:
                es.debate_budget = _b
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
            # require 事件通过 Hermes 原生 _pending_steer 通道注入，
            # 下一批工具调用后 LLM 就能看到（零底座改动，运行中即时生效）
            if etype == "enforcement" and kwargs.get("action") == "require" and agent_ref:
                _inject_agent_hint(agent_ref[0], "【系统强制提示】" + str(kwargs.get("message", "")))
        except Exception:
            pass

    def _inject_agent_hint(agent, text: str) -> bool:
        """把提示注入 agent 上下文（Hermes 原生 _pending_steer 通道）。"""
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

        # P0-1: es.blocked 置位（rail_review pre/post 未通过）→ 拦截执行类工具
        # 修复类工具不在 _DEBATE_EXEC_TOOLS，天然放行。
        if es.blocked and tool_name in _DEBATE_EXEC_TOOLS:
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

        elif tool_name in _DEBATE_EXEC_TOOLS and tool_name != "terminal":
            # P2(2026-08-10): 失败重试信号 — execute_r/python/code 同命令重试计数
            # 参数键兼容 command/code/script（execute_r/python 用 code，terminal 用 command）
            _cmd = ""
            if isinstance(args, dict):
                _cmd = str(args.get("command") or args.get("code") or args.get("script") or "")
            else:
                _cmd = str(args)
            _key = _cmd.strip()[:100]
            es._exec_retries[_key] = es._exec_retries.get(_key, 0) + 1
            es._last_exec_error = False  # 由 complete 分支更新
            # P2-7(2026-08-10): 钩子① — 执行前脚本设计辩论。
            # analysis 级 + 该命令首次执行 + 门控判定 L1/L2 → 提示先辩脚本设计
            if (es.analysis_level == "analysis" and es._exec_retries[_key] == 1
                    and not es.debated_topics):
                _b_level, _b_reasons, _b_force = debate_gate(es, stage="before_script", signals={})
                if _b_level >= DEBATE_L1:
                    _checks = _param_checklist(_cmd)
                    _check_txt = ""
                    if _checks:
                        _check_txt = ("\n🔍 参数核查清单（辩脚本设计时必逐项核查，用工具实查，不许猜）：\n"
                                      + "\n".join(f"  • {c}" for c in _checks))
                    _emit("enforcement", action="require",
                          level=DEBATE_LEVEL_NAMES[_b_level],
                          reasons=_b_reasons,
                          message=(f"💬 执行前辩论门控 → {DEBATE_LEVEL_NAMES[_b_level]}：{'；'.join(_b_reasons[:2])}。"
                                   f"先 debate_analysis 辩脚本设计与参数选择，再执行。{_check_txt}"),
                          require=["debate_analysis"])

        elif tool_name in _DEBATE_HIGH_IMPACT_TOOLS:
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

        if tool_name == "terminal" or (tool_name in _DEBATE_EXEC_TOOLS and tool_name != "terminal"):
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
                        should_proceed = r.get("should_proceed", True)
                        if not should_proceed:
                            issues = r.get("issues", [])
                            es.blocked = True  # P0-1: 硬阻断接线 — 后续执行类工具被拦
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
                # 触发 debate（P2(2026-08-10): 三级门控替代固定布尔触发）
                _g_signals = {
                    "high_impact": getattr(es, "_pending_high_impact", False),
                    "failed_retries": max(es._exec_retries.values()) if es._exec_retries else 0,
                    "last_error": es._last_exec_error,
                    "conflict": not should_proceed if es.rail_post_done else False,
                    "uncertainty": False,
                }
                _g_level, _g_reasons, _g_force = debate_gate(es, stage="after_script", signals=_g_signals)
                es._pending_high_impact = False
                # 钩子③ 结论辩论（对齐 docs/debate-core-design.md §钩子③）：
                # rail_review(post) 后 + analysis 级 → 结论合成前默认 L2（最终结论
                # 比过程更重要）。与钩子②取最高级：无异常信号的 analysis 任务
                # after=L1（轻量）、conclusion=L2（完整）→ 升级 L2；statistical
                # 两者都 L1；chat 都 L0。共享 es.debated_topics 去重，不重复辩。
                _c_level, _c_reasons, _c_force = debate_gate(es, stage="conclusion", signals=_g_signals)
                if _c_level > _g_level:
                    _g_level, _g_reasons, _g_force = _c_level, _c_reasons, _c_force
                if _g_level >= DEBATE_L1:
                    _mode_hint = {
                        # C2(2026-08-11): L1 轻量采样 / L2 完整 8 角色，都默认单模型上下文切断
                        DEBATE_L1: "level='L1'（轻量采样辩论，成本约 1/3）",
                        DEBATE_L2: "level='L2'（完整 8 角色辩论）",
                    }[_g_level]
                    _emit("enforcement", action="require",
                          level=DEBATE_LEVEL_NAMES[_g_level],
                          reasons=_g_reasons,
                          message=f"💬 辩论门控 → {DEBATE_LEVEL_NAMES[_g_level]}：{'；'.join(_g_reasons[:2])}。请调用 debate_analysis（{_mode_hint}）。",
                          require=["debate_analysis"])

        elif tool_name == "debate_analysis":
            es.debate_done = True
            # 保存辩论结论
            _save_debate_conclusion(es, result, args)
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
