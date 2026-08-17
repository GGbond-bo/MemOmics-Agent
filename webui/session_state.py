"""会话级状态捕获：用户诉求 + 任务状态 + 资产候选提取。

与 holographic 插件共享 ``hermes_home/memory_store.db``：
- ``session_state`` 表：task_json（任务状态块）+ requests_json（用户诉求，最近 20 条）
- ``assets`` 表：用户提供的脚本/路径（status=pending，待确认后由 agent 侧确认）

调用方：
- server.py 每轮 ws chat 调用 :func:`capture_user_request` / :func:`extract_assets`
- enforcement.py 里程碑调用 :func:`update_task_state`

护栏（对齐设计文档）：
- 诉求/资产只在**当前会话**记录，不注入跨会话目标
- 升级为 facts 只发生在用户明说"记住"或同诉求重复 >=2 次
- 资产候选必须 ``os.path.isfile`` 校验通过才入库（防假阳性）
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time

logger = logging.getLogger("session_state")

# ---------------------------------------------------------------------------
# 实体提取（诉求的"内容词"）
# ---------------------------------------------------------------------------

ENTITY_KEYWORDS = [
    "热图", "umap", "tsne", "聚类", "降维", "qc", "差异", "富集", "gsea", "生存",
    "火山图", "气泡图", "小提琴图", "通路", "marker", "注释", "分群", "细胞类型",
    "比例", "拟时", "轨迹", "拷贝数", "cnv", "免疫浸润", "相关性", "表达矩阵",
    "双细胞", "归一化", "批次", "整合", "harmony", "seurat", "scanpy", "monocle",
    "cellchat", "wgcna", "染色质", "atac", "motif", "peak", "热力图", "瀑布图",
    "森林图", "venn", "桑基图", "网络图", "gsva", "ssgsea", "aucell", "cytotrace",
    "文献", "下载", "调研", "数据库",
]

_RE_ENTITY = re.compile(
    r"(" + "|".join(re.escape(k) for k in ENTITY_KEYWORDS) + r")",
    re.IGNORECASE,
)

# 用户明说"记住"的升级触发词
_RE_REMEMBER = re.compile(r"(记住|记得|以后都|以后|每次|永远|后续都)")

# 动词/语气词（诉求降噪，与 holographic._extract_query_keywords 思路一致）
_RE_NOISE = re.compile(
    r"(继续|接着|然后|再|帮我|请|给我|麻烦|跑|做|画|看|计算|执行|整理|总结|生成|"
    r"更新|修改|优化|用|把|将|对|一下|看看|一遍|要|想|希望|现在|重新|开始|停止|"
    r"能不能|可以|怎么|如何|什么|哪些|那个|这个|还是|都|也|了|呢|吗|啊|吧|的|是|"
    r"之后|先|后|每|各|所有|全部|刚才|上次|之前|分析)"
)

# 资产路径/文件候选
_RE_PATH = re.compile(
    r"([A-Za-z]:[\\/][^\s，。；、\"']+|"
    r"(?:\.{1,2}[\\/][^\s，。；、\"']+|[\\/][^\s，。；、\"']*\.(?:R|py|sh|txt|csv|tsv|h5|h5ad|rds|RData|xlsx|bed|bw|narrowPeak|gtf|fa|fastq)\b))",
    re.IGNORECASE,
)
_ASSET_KIND_BY_EXT = {
    ".r": "script", ".py": "script", ".sh": "script",
    ".txt": "data", ".csv": "data", ".tsv": "data", ".h5": "data", ".h5ad": "data",
    ".rds": "data", ".rdata": "data", ".xlsx": "data",
    ".bed": "data", ".bw": "data", ".narrowpeak": "data", ".gtf": "data",
    ".fa": "data", ".fastq": "data",
}

_MAX_REQUESTS = 20
_MAX_ASSETS_PER_TURN = 8
_STORE_LOCK = threading.Lock()
_STORE = None  # lazy MemoryStore 单例


def _get_store():
    """Lazy MemoryStore singleton (webui 进程内复用连接)."""
    global _STORE
    if _STORE is None:
        from plugins.memory.holographic.store import MemoryStore
        _STORE = MemoryStore(db_path=_get_db_path())
    return _STORE


def _get_db_path() -> str:
    """hermes_home/memory_store.db（与 holographic 插件共享同一库）。"""
    from pathlib import Path
    cur = Path(__file__).resolve().parent.parent  # MEMOMICS_HOME/
    return str(cur / "hermes_home" / "memory_store.db")


def get_store():
    """公开的 MemoryStore 单例访问（供 server.py 等外部调用）。"""
    return _get_store()


def _now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def extract_entity(text: str) -> str:
    """从用户消息提取内容实体（图/分析方法词）。

    只在关键词表命中时返回（防闲聊误判，如"好的谢谢"）。
    """
    if not text:
        return ""
    m = _RE_ENTITY.search(text)
    if m:
        return m.group(1).lower()
    return ""


def capture_user_request(
    session_id: str,
    text: str,
    store=None,
    intent: str = "chat",
) -> dict:
    """捕获用户诉求到 session_state.requests_json（最近 20 条）。

    升级规则（escalate=True）：
    1. 文本含"记住/以后/每次"等明确记忆词；
    2. 同 entity 诉求在本会话出现 >=2 次。
    升级时写入 facts（category='user_request'，幂等去重）。
    """
    text = (text or "").strip()
    if not text:
        return {"entity": "", "escalated": False}
    store = store or _get_store()
    entity = extract_entity(text)

    st = store.get_session_state(session_id)
    try:
        reqs = json_loads(st.get("requests_json") or "[]")
    except Exception:
        reqs = []

    # 去重：60 秒内同 entity 且文本完全相同 → 静默去重（不追加、不重复升级）
    now = _now_ts()
    if any(
        x.get("entity") == entity
        and x.get("text") == text[:200]
        and abs(time.time() - (x.get("_ts_n", 0))) < 60
        for x in reqs[-5:]
    ):
        return {"entity": entity, "escalated": False}

    # 升级：明确记忆词，或同 entity 诉求此前已出现过（本次为第 2 次）
    same_entity = [r for r in reqs if r.get("entity") == entity]
    escalated = bool(_RE_REMEMBER.search(text)) or (bool(entity) and len(same_entity) >= 1)

    reqs.append({
        "text": text[:200],
        "entity": entity,
        "intent": intent,
        "ts": now,
        "_ts_n": time.time(),
    })
    reqs = reqs[-_MAX_REQUESTS:]

    if escalated:
        try:
            store.add_fact(
                content=f"[用户诉求] {text[:200]}",
                category="user_request",
                tags=entity or "general",
            )
        except Exception as e:  # 升级失败不影响主流程
            logger.warning("escalate request failed: %s", e)

    store.update_session_state(session_id, requests_json=json_dumps(reqs))
    return {"entity": entity, "escalated": escalated}


def extract_assets(
    session_id: str,
    text: str,
    store=None,
    project: str = "",
) -> list:
    """从用户消息提取资产候选（脚本/数据路径），status=pending 入库。

    规则：盘符路径或常见扩展名 + os.path.isfile 存在性校验。
    每轮最多 _MAX_ASSETS_PER_TURN 条，防批量误提取。
    """
    text = (text or "").strip()
    if not text:
        return []
    store = store or _get_store()
    found: list = []
    seen = set()
    for m in _RE_PATH.finditer(text):
        raw = m.group(1)
        key = raw.lower().rstrip(".,;:，。；、")
        if key in seen:
            continue
        seen.add(key)
        # 只收存在性校验通过的候选（防 LLM/文本里的假路径）
        if not os.path.isfile(key):
            continue
        ext = os.path.splitext(key)[1].lower()
        kind = _ASSET_KIND_BY_EXT.get(ext, "file")
        name = os.path.basename(key)
        if store.has_asset(name=name, path=key, session_id=session_id):
            continue
        store.add_asset(
            name=name,
            path=key,
            kind=kind,
            purpose="",
            session_id=session_id,
            project=project,
            status="pending",
            source="user",
        )
        found.append({"name": name, "path": key, "kind": kind})
        if len(found) >= _MAX_ASSETS_PER_TURN:
            break
    return found


def update_task_state(session_id: str, store=None, **fields) -> dict:
    """合并更新任务状态块（title/step/total_steps/current_script/last_conclusion）。

    返回合并后的 task dict。空值字段不覆盖已有值。
    """
    store = store or _get_store()
    st = store.get_session_state(session_id)
    try:
        task = json_loads(st.get("task_json") or "{}")
    except Exception:
        task = {}
    changed = False
    for k, v in fields.items():
        if v is None or v == "":
            continue
        if task.get(k) != v:
            task[k] = v
            changed = True
    if changed:
        task["updated_at"] = _now_ts()
        store.update_session_state(session_id, task_json=json_dumps(task))
    return task


def confirm_asset(asset_id: int, store=None, status: str = "confirmed") -> bool:
    """确认/拒绝资产（pending -> confirmed/rejected）。"""
    store = store or _get_store()
    return store.confirm_asset(asset_id, status)


# ---------------------------------------------------------------------------
# JSON 辅助（防御性）
# ---------------------------------------------------------------------------

def json_dumps(obj) -> str:
    import json
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "[]"


def json_loads(s: str):
    import json
    try:
        return json.loads(s)
    except Exception:
        return []
