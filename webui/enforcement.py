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
        "画图", "可视化", "figure", "plot", "chart", "graph", "volcano", "heatmap", "generate", "create", "draw",
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
    
    # 有分析关键词 + 执行意图 → analysis
    has_action = any(kw in msg_lower for kw in ["run", "do", "go", "start", "generate", "create", "draw", "plot", "subset", "exec"])
    if score >= 3 or (score >= 2 and has_action):
        return "analysis"
    elif score >= 1:
        return "statistical"
    return "chat"


class EnforcementState:
    """会话级强制执行状态追踪"""

    def __init__(self, session_id: str, results_dir: str = ""):
        self.session_id = session_id
        self.results_dir = results_dir
        self.skills_loaded: set = set()
        self.knowledge_searched: bool = False
        self.rail_pre_done: bool = False
        self.rail_post_done: bool = False
        self.debate_done: bool = False
        self.analysis_level: str = "chat"
        self._pending_record: bool = False  # 上一步 terminal 完成后还没 record
        self._last_terminal_result: str = ""  # 最近 terminal 输出（提取参数用）
        self.terminal_count: int = 0
        self.tool_history: list = []
        self.warnings: list = []
        self.blocked: bool = False
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
        except Exception:
            pass

    def tool_start_cb(tool_call_id: str, tool_name: str, args):
        """工具执行前拦截"""
        es.tool_history.append({"tool": tool_name, "args": str(args)[:200], "time": time.time(), "phase": "start"})

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

        elif tool_name == "terminal":
            # 🔧 bug③ 修复(2026-08-01): 合并自杀检测到主分支
            # 之前: 此处有独立的 elif terminal 分支(153行)在前面，导致这里整个不可达
            _cmd = str(args.get("command", "")) if isinstance(args, dict) else str(args)
            _cmd_lower = _cmd.lower()
            _danger = [
                ("taskkill", "/im python", "禁止 /IM python.exe，会把 MemOmics 自己杀掉！请用 /F /PID <具体PID>"),
                ("killall", "python", "禁止 killall python！请用 kill <具体PID>"),
                ("pkill", "python", "禁止 pkill python！请用 kill <具体PID>"),
            ]
            for _tool, _pattern, _msg in _danger:
                if _tool in _cmd_lower and _pattern in _cmd_lower:
                    es.warnings.append(f"terminal: 自杀命令被拦截 - {_cmd[:80]}")
                    _emit("enforcement", action="blocked", message=f"⛔ 拦截：{_msg}")

            es.terminal_count += 1
            # 🔧 自进化门禁：上一个 terminal 完成后还没 record_run → 阻断
            if es._pending_record and es.analysis_level != "chat":
                es.warnings.append(f"terminal#{es.terminal_count}: 上一步未完成 record_run")
                _emit("enforcement", action="blocked",
                      message="⛔ 上一步 terminal 完成后未记录经验！请先调用 skill_evolution(action='record_run') 沉淀经验，再执行下一步。",
                      require=["skill_evolution"])
            # 分析级操作且未加载 skill → 警告
            if es.analysis_level in ("analysis", "statistical") and not es.skills_loaded:
                es.warnings.append(f"terminal#{es.terminal_count}: 未加载任何 skill")
                _emit("enforcement", action="warning",
                      message=f"⚠️ 未加载 skill 就执行 terminal。SOUL.md 铁律 #1 要求先 skill_view。",
                      missing=["skill_view"])

            # 分析级操作且未做 pre 审查 → 警告
            if es.analysis_level in ("analysis", "statistical") and not es.rail_pre_done and es.terminal_count == 1:
                es.warnings.append(f"terminal#{es.terminal_count}: 未执行 rail_review(pre)")
                _emit("enforcement", action="warning",
                      message=f"⚠️ 未执行 rail_review(pre) 审查。铁律 #3 要求分析前先审查。",
                      missing=["rail_review(pre)"])

            # 无知识库搜索 → 温和提醒
            if es.analysis_level in ("analysis",) and not es.knowledge_searched and es.terminal_count == 1:
                _emit("enforcement", action="info",
                      message="💡 建议先 search_knowledge() 获取参数推荐。铁律 #2。")

    def tool_complete_cb(tool_call_id: str, tool_name: str, args, result):
        """工具执行后拦截 — 自动触发后续动作"""
        es.tool_history.append({"tool": tool_name, "args": str(args)[:200], "time": time.time(), "phase": "complete"})

        if tool_name == "terminal":
            es.rail_post_done = False
            # 保存结果用于后续参数提取
            es._last_terminal_result = str(result)[:1000] if result else ""
            # 设置 pending 标记：所有非闲聊级别都需要 record
            if es.analysis_level != "chat":
                es._pending_record = True

            # 自动提示：需要 rail_review(post)
            if es.analysis_level in ("analysis", "statistical", "lightweight"):
                _emit("enforcement", action="require",
                      message="🔍 terminal 执行完毕。请调用 rail_review(post) 进行执行后审查。",
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
                            _emit("enforcement", action="blocked",
                                  message=f"🛡️ rail_review(pre) 发现问题: {'; '.join(issues[:3])}")
                    elif phase == "post" or r.get("phase") == "post":
                        es.rail_post_done = True
                        # 🔧 bug② 修复(2026-08-01): rail_review 返回键是 "passed" 不是 "should_proceed"
                        # 之前: r.get("should_proceed", True) 永远默认True → 审查失败也被当通过
                        should_proceed = r.get("passed", r.get("should_proceed", True))
                        if not should_proceed:
                            issues = r.get("issues", [])
                            _emit("enforcement", action="blocked",
                                  message=f"🛡️ rail_review(post) 发现问题: {'; '.join(issues[:3])}")
            except Exception:
                pass

            # rail_review(post) 完成后 → 自动 record_run + 触发 debate
            if es.rail_post_done:
                # 自动记录成功运行到 skill（自进化）— 扩展到所有非闲聊级别
                if es.analysis_level != "chat" and es.skills_loaded:
                    try:
                        import importlib.util as _iu2
                        import os as _os2, re as _re
                        _sep2 = _iu2.spec_from_file_location(
                            "skill_evolution",
                            _os2.join(_os2.dirname(_os2.abspath(__file__)),
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
                        for _sk in es.skills_loaded:
                            _se.skill_evolution(
                                action="record_run",
                                skill_name=_sk,
                                script_name=f"session_{sid}_terminal{es.terminal_count}",
                                species=_species, tissue=_tissue, direction=_direction,
                                params_used=_params,
                                result_summary=f"rail_review(post) passed. session={sid}",
                                score=7
                            )
                        _emit("enforcement", action="recorded",
                              message=f"🧬 自动 record_run: {', '.join(es.skills_loaded)} species={_species} tissue={_tissue}")
                        es._pending_record = False  # 已记录，清除标记
                    except Exception as _e:
                        _emit("enforcement", action="warning",
                              message=f"⚠️ record_run 失败: {_e}")
                # 触发 debate
                if not es.debate_done and es.analysis_level == "analysis":
                    _emit("enforcement", action="require",
                          message="💬 rail_review(post) 通过。请调用 debate_analysis 进行多专家辩证审查。",
                          require=["debate_analysis"])

        elif tool_name == "debate_analysis":
            es.debate_done = True
            # 保存辩论结论
            _save_debate_conclusion(es, result, args)

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
