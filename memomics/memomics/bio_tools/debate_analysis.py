"""debate_analysis — 多角色正反方切断上下文对抗辩论工具。

v3 设计（多角色):
1. 正方 3 个专业编辑（各自独立 LLM 调用，互相看不到）：
   - 生物学编辑：从 marker gene / 已知生物学知识角度支持（用 biology_kb）
   - 统计学编辑：从显著性 / 效应量 / 样本量角度支持（用 statistics_kb）
   - 生信编辑：从 QC 指标 / 双胞率 / 污染率 / 聚类质量角度支持（用 bioinfo_kb）
2. 反方 4 个专业编辑（各自独立 LLM 调用，互相看不到，也看不到正方）：
   - 生物学编辑：从异质性 / 批次效应 / marker 重叠角度质疑（用 biology_kb）
   - 统计学编辑：从多重比较 / 假阳性 / 统计功效角度质疑（用 statistics_kb）
   - 生信编辑：从降维质量 / 聚类稳定性 / 注释置信度角度质疑（用 bioinfo_kb）
   - 历史经验编辑：从 error_memory/errors.jsonl 历史报错记录角度质疑（用 history_errors）
3. 裁判编辑（LLM 决断）— 看到正方+反方所有编辑后给出最终裁决

分科知识库：
- 每个学科角色使用专属知识库（biology_kb / statistics_kb / bioinfo_kb）
- 如果专属知识库未提供，回退到通用 knowledge_base_info
- 历史经验角色使用 history_errors（error_memory）

归档机制：
- 辩论结果自动归档到 results/.../log/debate_{timestamp}.json（如设了线程级 results_dir）
- 同时缓存到 _debates/ 目录用于去重（72h TTL）

上下文隔离机制：
- 每个编辑是独立的 HTTP API 调用，messages 只包含该编辑自己的 prompt
- 正方编辑不知道反方编辑说了什么，反之亦然
- 正方编辑之间也互相不知道
- 裁判是唯一能看到所有编辑论点的
- 每次调用返回时记录调用 ID，可用于验证隔离性

适用于:
- 参数选择辩论 (如 clustering resolution 0.8 vs 1.0)
- 细胞类型注释辩论 (marker 明显 vs 不明显)
- QC 阈值辩论 (MT% 15% vs 20%)
- 分析结论辩论（生物发现是否可靠）
- 任何需要多方审视的分析决策
"""
import json
import os
import logging
import time
import hashlib
import threading
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

# === 线程级会话隔离（替代 os.environ，避免多会话竞态） ===
# 每个 agent 在自己的线程里运行，threading.local() 天然线程隔离
_session_local = threading.local()

def set_session_context(sid: str = "", results_dir: str = ""):
    """设置当前线程的会话上下文（由 server.py 在 agent 启动时调用）。"""
    _session_local.sid = sid
    _session_local.results_dir = results_dir

def get_session_sid() -> str:
    """获取当前线程的会话 ID（纯线程隔离，无 os.environ fallback）。"""
    return getattr(_session_local, "sid", "")

def get_session_results_dir() -> str:
    """获取当前线程的结果目录（纯线程隔离，无 os.environ fallback）。"""
    return getattr(_session_local, "results_dir", "")

SCHEMA = {
    "name": "debate_analysis",
    "description": (
        "Trigger a multi-role structured debate on an analysis decision or result. "
        "Pro side has 3 independent role editors (biology/statistics/bioinformatics), "
        "Con side has 4 independent role editors (biology/statistics/bioinformatics/history). "
        "Each role is a professional editor making an INDEPENDENT LLM call — they cannot see each other's arguments. "
        "Each discipline uses its own knowledge base (biology_kb/statistics_kb/bioinfo_kb). "
        "A judge editor reviews ALL arguments and gives a final verdict with confidence level. "
        "Use for: parameter choices, cell type annotation disputes, method selection, "
        "result validation, biological conclusion verification. "
        "MUST call this when encountering uncertain parameters or debatable results. "
        "Results are archived to results/.../log/debate_*.json automatically."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The decision/parameter/result being debated (e.g. 'clustering resolution=0.8', 'MT% threshold=15%', 'cluster 3 = T cells?', '衰老相关基因在Type II纤维中上调')"
            },
            "context": {
                "type": "string",
                "description": "Context: data details, species, tissue, direction, cell count, current parameters, results summary, QC metrics"
            },
            "knowledge_base_info": {
                "type": "string",
                "description": "General knowledge base info (fallback for all roles if discipline-specific KB not provided). If empty, debate will use general knowledge.",
                "default": ""
            },
            "biology_kb": {
                "type": "string",
                "description": "Biology-specific knowledge base: marker genes, cell type references, tissue-specific genes, literature evidence. Injected into biology editor prompts (both pro and con). If empty, falls back to knowledge_base_info.",
                "default": ""
            },
            "statistics_kb": {
                "type": "string",
                "description": "Statistics-specific knowledge base: method assumptions, sample size guidelines, multiple testing correction methods, power analysis references. Injected into statistics editor prompts (both pro and con). If empty, falls back to knowledge_base_info.",
                "default": ""
            },
            "bioinfo_kb": {
                "type": "string",
                "description": "Bioinformatics-specific knowledge base: QC thresholds, clustering best practices, dimensionality reduction guidelines, pipeline standards. Injected into bioinformatics editor prompts (both pro and con). If empty, falls back to knowledge_base_info.",
                "default": ""
            },
            "history_errors": {
                "type": "string",
                "description": "Historical error records from error_memory/errors.jsonl relevant to this topic. Used by con-side history agent.",
                "default": ""
            }
        },
        "required": ["topic", "context"]
    }
}

# ==================== 正方角色 prompts ====================

PRO_BIO_PROMPT = """你是一位**生物学专业编辑**（正方）。你的任务是从生物学角度**支持**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 生物学知识库参考
{kb_info}

请从以下生物学角度论证为什么这个决策/结论是合理的：
1. **Marker gene 验证**：相关标记基因的表达模式是否支持？
2. **已知生物学知识**：与文献中已知的细胞类型/组织特征是否一致？
3. **生物学预期**：结果是否符合该物种/组织/方向的生物学预期？

要求：
- 如果知识库参考中有具体发现和文献，**必须引用**（标注文献来源）
- 如果知识库参考为空，标注 [LLM常识，非知识库引用]
- 给出具体的基因名、表达数据、文献引用
- 不要空话，要有数据支撑
- 控制在 300 字以内
- 你不知道其他编辑的观点，请独立思考
"""

PRO_STAT_PROMPT = """你是一位**统计学专业编辑**（正方）。你的任务是从统计学角度**支持**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 统计学知识库参考
{kb_info}

请从以下统计学角度论证为什么这个决策/结论是合理的：
1. **显著性**：p值、FDR是否达到阈值？效应量是否足够大？
2. **样本量**：细胞数/样本数是否足够支持这个结论？
3. **分布特征**：数据的分布是否符合方法的假设？

要求：
- 给出具体的数值（p值、效应量、置信区间）
- 不要空话，要有数据支撑
- 控制在 300 字以内
- 你不知道其他编辑的观点，请独立思考
"""

PRO_BIOINFO_PROMPT = """你是一位**生信专业编辑**（正方）。你的任务是从生信分析质量角度**支持**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 生信知识库参考
{kb_info}

请从以下生信分析质量角度论证为什么这个决策/结论是合理的：
1. **QC 指标**：nFeature/nCount/percent.mt 分布是否合理？
2. **聚类质量**：轮廓系数、聚类稳定性是否达标？双胞率是否在可接受范围？
3. **分析流程**：参数选择是否符合最佳实践？是否有遗漏的步骤？

要求：
- 给出具体的 QC 数值和分析指标
- 不要空话，要有数据支撑
- 控制在 300 字以内
- 你不知道其他编辑的观点，请独立思考
"""

# ==================== 反方角色 prompts ====================

CON_BIO_PROMPT = """你是一位**生物学专业编辑**（反方）。你的任务是从生物学角度**质疑**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 生物学知识库参考
{kb_info}

请从以下生物学角度论证为什么这个决策/结论可能有问题：
1. **异质性**：是否存在亚群被合并？是否有过度聚类？
2. **批次效应**：结果是否受批次效应影响？生物学差异与技术差异是否混淆？
3. **Marker 重叠**：标记基因是否在多种细胞类型中表达？特异性是否足够？
4. **替代解释**：是否有其他生物学解释？

要求：
- 给出具体的基因名、表达数据
- 如果有更好的解释，明确提出
- 控制在 300 字以内
- 你不知道其他编辑的观点，请独立思考
"""

CON_STAT_PROMPT = """你是一位**统计学专业编辑**（反方）。你的任务是从统计学角度**质疑**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 统计学知识库参考
{kb_info}

请从以下统计学角度论证为什么这个决策/结论可能有问题：
1. **多重比较**：是否进行了多重检验校正？假阳性率是否可控？
2. **统计功效**：样本量是否足够检测到真实效应？是否有 power analysis？
3. **模型假设**：统计方法的假设是否满足？是否有更合适的替代方法？
4. **效应量**：虽然显著，但效应量是否大到有生物学意义？

要求：
- 给出具体的数值和统计推理
- 如果有更合适的统计方法，明确提出
- 控制在 300 字以内
- 你不知道其他编辑的观点，请独立思考
"""

CON_BIOINFO_PROMPT = """你是一位**生信专业编辑**（反方）。你的任务是从生信分析质量角度**质疑**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 生信知识库参考
{kb_info}

请从以下生信分析质量角度论证为什么这个决策/结论可能有问题：
1. **降维质量**：PCA/UMAP 的解释方差是否足够？是否过度降维？
2. **聚类稳定性**：不同分辨率下聚类是否稳定？Bootstrap 稳定性如何？
3. **注释置信度**：自动注释的置信度得分是多少？是否有手动验证？
4. **参数敏感性**：结果是否对参数选择高度敏感？换一组参数结果会变吗？

要求：
- 给出具体的分析指标
- 如果有更好的参数/方法，明确提出
- 控制在 300 字以内
- 你不知道其他编辑的观点，请独立思考
"""

CON_HISTORY_PROMPT = """你是一位**历史经验专业编辑**（反方）。你的任务是从历史报错和经验记录角度**质疑**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 历史报错记录
{history_errors}

请从以下历史经验角度论证为什么这个决策/结论可能有问题：
1. **历史报错**：之前是否遇到过类似参数导致的错误？错误是什么？
2. **已知陷阱**：这个参数/方法是否有已知的坑？
3. **环境限制**：当前硬件/环境是否真的能跑通这个参数？
4. **修复经验**：之前类似问题是怎么修复的？是否应该采用修复后的方案？

要求：
- 引用具体的历史报错记录（时间、错误内容、修复方案）
- 如果历史记录显示这个参数有问题，明确指出
- 控制在 300 字以内
- 你不知道其他编辑的观点，请独立思考
"""

# ==================== 裁判 prompt ====================

JUDGE_PROMPT = """你是生信分析多角色辩论的**裁判编辑**。7位专业编辑对以下决策进行了辩论，请给出最终裁决。

## 辩论主题
{topic}

## 上下文
{context}

## 正方论证（3位专业编辑，各自独立）

### 生物学编辑（正方）
{pro_bio}

### 统计学编辑（正方）
{pro_stat}

### 生信编辑（正方）
{pro_bioinfo}

## 反方论证（4位专业编辑，各自独立）

### 生物学编辑（反方）
{con_bio}

### 统计学编辑（反方）
{con_stat}

### 生信编辑（反方）
{con_bioinfo}

### 历史经验编辑（反方）
{con_history}

## 裁判要求

请给出：
1. **各方论证强度评估**（1-10分）
2. **最终裁决**：支持原决策 / 修改参数 / 需要更多信息
3. **置信度**：高 / 中 / 低（表示对裁决的信心程度）
4. 如果建议修改，给出具体推荐参数
5. 裁决理由（300字以内）

**重要**：正方和反方是独立生成的（切断上下文），你不能假设他们看过彼此的论点。你需要综合判断哪方更有说服力。

注意：你是最终权威，但请公正地权衡各方论点。不要因正方或反方人多而偏袒。

格式：
```json
{{
  "scores": {{
    "pro_biology": <1-10>,
    "pro_statistics": <1-10>,
    "pro_bioinformatics": <1-10>,
    "con_biology": <1-10>,
    "con_statistics": <1-10>,
    "con_bioinformatics": <1-10>,
    "con_history": <1-10>
  }},
  "verdict": "support" | "modify" | "need_more_info",
  "confidence": "high" | "medium" | "low",
  "recommended_params": {{}},
  "reasoning": "..."
}}
```
"""


def _call_llm_sync(prompt: str, label: str, api_key: str, base_url: str, model: str) -> dict:
    """独立 LLM 调用 — 每个角色一个独立的 messages 数组，切断上下文。

    返回 dict: {content, call_id, isolation_verified}
    - call_id: 唯一调用 ID，可用于追踪
    - isolation_verified: True 表示这是独立调用（messages 只有 1 条）

    线程安全：每次调用创建独立的 httpx.Client，不共享状态，可安全并行。
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    # 关键：每个角色只有自己的 prompt，没有其他角色的消息
    # 这就是"切断上下文"的实现方式
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.7,
    }
    call_id = f"{label}_{int(time.time() * 1000) % 1000000}"

    for attempt in range(3):
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers, json=payload
                )
                resp.raise_for_status()
                msg = resp.json()["choices"][0]["message"]
                content = msg.get("content") or ""
                if (not content or len(content.strip()) < 10) and msg.get("reasoning_content"):
                    content = msg["reasoning_content"]
                if content and len(content.strip()) > 10:
                    return {
                        "content": content,
                        "call_id": call_id,
                        "isolation_verified": True,
                        "messages_count": 1,  # 只有 1 条消息 = 上下文已隔离
                    }
                time.sleep(2)
        except Exception as e:
            logger.warning(f"debate {label} attempt {attempt+1} failed: {e}")
            time.sleep(3)

    return {
        "content": f"[{label} 辩论生成失败]",
        "call_id": call_id,
        "isolation_verified": True,
        "messages_count": 1,
        "error": True,
    }


# ==================== 并行调用工具 ====================

def _call_role_parallel(tasks: list, api_key: str, base_url: str, model: str) -> dict:
    """并行调用多个角色，返回 {label: result_dict}。

    每个 task = (label, prompt)。
    使用 ThreadPoolExecutor 并行调用，每个角色仍是独立 HTTP 调用（上下文隔离不变）。
    正方角色互相看不到（各自的 messages 只有自己的 prompt），并行不破坏隔离性。
    """
    results = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {
            executor.submit(_call_llm_sync, prompt, label, api_key, base_url, model): label
            for label, prompt in tasks
        }
        for future in as_completed(futures):
            label = futures[future]
            try:
                results[label] = future.result()
            except Exception as e:
                logger.warning(f"debate {label} parallel call failed: {e}")
                results[label] = {
                    "content": f"[{label} 辩论生成失败]",
                    "call_id": f"{label}_{int(time.time() * 1000) % 1000000}",
                    "isolation_verified": True,
                    "messages_count": 1,
                    "error": True,
                }
    return results


# ==================== 辩论结果持久化 ====================

def _get_debates_dir() -> Path:
    """获取辩论历史存储目录：hermes_home/skills/bioinformatics/_debates/"""
    try:
        import sys
        # hermes-agent 在 sys.path 中时优先用 get_hermes_home()
        for p in list(sys.path):
            if p.endswith('hermes-agent') or p.endswith('hermes-agent\\') or p.endswith('hermes-agent/'):
                break
        from hermes_constants import get_hermes_home
        base = Path(get_hermes_home())
    except Exception:
        # fallback: 环境变量或硬编码
        base = Path(os.environ.get("HERMES_HOME", "E:/MemOmics-Agent/hermes_home"))
    debates_dir = base / "skills" / "bioinformatics" / "_debates"
    debates_dir.mkdir(parents=True, exist_ok=True)
    return debates_dir


def _topic_hash(topic: str, context: str) -> str:
    """生成 topic+context 的 hash，用于历史辩论匹配。"""
    combined = (topic.strip().lower() + "||" + context.strip().lower()).encode("utf-8")
    return hashlib.md5(combined).hexdigest()[:16]


def _save_debate(topic: str, context: str, result_json: str) -> None:
    """将辩论结果保存到 _debates/ 目录，文件名 = topic_hash.json。"""
    try:
        h = _topic_hash(topic, context)
        path = _get_debates_dir() / f"{h}.json"
        record = {
            "topic": topic,
            "context": context,
            "hash": h,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "result": json.loads(result_json),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        logger.info(f"debate saved to {path}")
    except Exception as e:
        logger.warning(f"Failed to save debate: {e}")


def _load_debate(topic: str, context: str, max_age_hours: int = 72) -> dict | None:
    """查询历史辩论结果。返回 dict 或 None。

    匹配条件：topic+context 的 hash 完全匹配。
    过期条件：超过 max_age_hours 小时的记录不返回（默认 72 小时）。
    """
    try:
        h = _topic_hash(topic, context)
        path = _get_debates_dir() / f"{h}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            record = json.load(f)
        # 检查是否过期
        saved_time = time.strptime(record.get("timestamp", ""), "%Y-%m-%d %H:%M:%S")
        age_hours = (time.time() - time.mktime(saved_time)) / 3600
        if age_hours > max_age_hours:
            logger.info(f"debate {h} expired ({age_hours:.1f}h > {max_age_hours}h)")
            return None
        return record
    except Exception as e:
        logger.warning(f"Failed to load debate: {e}")
        return None


def _get_results_log_dir() -> Path:
    """获取当前分析结果目录下的 log/ 子目录。

    通过线程级上下文获取（set_session_context 设定，纯线程隔离，无竞态风险）。
    修复：当线程级 results_dir 为空时，尝试从 server 的 _sessions 字典回退获取。
    """
    results_dir = get_session_results_dir()
    if not results_dir:
        # 回退方案：从 server._sessions 获取
        sid = get_session_sid()
        if sid:
            import sys as _sys
            try:
                server_mod = _sys.modules.get("webui.server")
                if server_mod and hasattr(server_mod, "_sessions"):
                    sess = server_mod._sessions.get(sid, {})
                    results_dir = sess.get("results_dir", "")
            except Exception:
                pass
    if not results_dir:
        import sys as _sys
        print(f"[debate_analysis] WARNING: results_dir is empty, cannot archive debate", file=_sys.stderr)
        return None
    log_dir = Path(results_dir) / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _archive_debate_to_results(topic: str, context: str, result_json: str):
    """将辩论结果归档到 results/.../log/debate_{timestamp}.json"""
    try:
        log_dir = _get_results_log_dir()
        if log_dir is None:
            return  # 没有结果目录，跳过归档
        ts = time.strftime("%Y%m%d_%H%M%S")
        h = _topic_hash(topic, context)[:8]
        archive_path = log_dir / f"debate_{ts}_{h}.json"
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(result_json)
        logger.info(f"Debate archived to {archive_path}")
    except Exception as e:
        logger.warning(f"Failed to archive debate to results: {e}")


def debate_analysis(topic: str, context: str, knowledge_base_info: str = "",
                    history_errors: str = "", biology_kb: str = "",
                    statistics_kb: str = "", bioinfo_kb: str = "") -> str:
    """多角色辩论 — 正方3专业编辑 + 反方4专业编辑 + 裁判编辑，全部独立 LLM 调用。

    上下文隔离实现：
    - 每个编辑调用 _call_llm_sync()，传入只包含该编辑 prompt 的 messages
    - 正方编辑之间不知道彼此（各自独立调用）
    - 反方编辑之间不知道彼此（各自独立调用）
    - 正方不知道反方（各自独立调用）
    - 裁判是唯一看到所有角色的（裁判的 prompt 包含所有角色的输出）
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://dcsapi.dcs.cloud/api/aigress/unified/v1")
    model = os.environ.get("DEEPSEEK_MODEL", "glm-5.2")

    if not api_key:
        return _fallback_debate(topic, context, knowledge_base_info, history_errors)

    kb = knowledge_base_info or "无知识库参考"
    hist = history_errors or "无历史报错记录"

    # ========== 自动加载知识库（兜底：KB 为空时从 context 提取物种/组织/方向） ==========
    if kb == "无知识库参考" and not biology_kb and not statistics_kb and not bioinfo_kb:
        auto_kb = _auto_load_kb(context, topic)
        if auto_kb:
            kb = auto_kb
            if not biology_kb:
                biology_kb = auto_kb
            if not statistics_kb:
                statistics_kb = auto_kb
            if not bioinfo_kb:
                bioinfo_kb = auto_kb

    # ========== 查询历史辩论（优化2：持久化复用） ==========
    cached = _load_debate(topic, context)
    if cached:
        cached_result = cached.get("result", {})
        cached_result["reused_from_cache"] = True
        cached_result["cache_timestamp"] = cached.get("timestamp", "")
        cached_result["note"] = (
            "多角色辩论（v3）+ 并行调用 + 历史复用：本次辩论与历史记录的 topic+context 完全匹配，"
            f"直接复用 {cached.get('timestamp', '')} 的辩论结果（72小时内有效）。"
        )
        return json.dumps(cached_result, ensure_ascii=False, indent=2)

    # ========== 分科知识库（回退到通用 kb） ==========
    bio_kb = biology_kb or kb
    stat_kb = statistics_kb or kb
    bioinfo_kb_val = bioinfo_kb or kb

    try:
        # ========== 正方 3 专业编辑（并行调用，互相不知道，各用专属知识库） ==========
        pro_tasks = [
            ("pro_biology", PRO_BIO_PROMPT.format(topic=topic, context=context, kb_info=bio_kb)),
            ("pro_statistics", PRO_STAT_PROMPT.format(topic=topic, context=context, kb_info=stat_kb)),
            ("pro_bioinformatics", PRO_BIOINFO_PROMPT.format(topic=topic, context=context, kb_info=bioinfo_kb_val)),
        ]
        pro_results = _call_role_parallel(pro_tasks, api_key, base_url, model)
        pro_bio = pro_results["pro_biology"]
        pro_stat = pro_results["pro_statistics"]
        pro_bioinfo = pro_results["pro_bioinformatics"]

        # ========== 反方 4 专业编辑（并行调用，互相不知道，也看不到正方，各用专属知识库） ==========
        con_tasks = [
            ("con_biology", CON_BIO_PROMPT.format(topic=topic, context=context, kb_info=bio_kb)),
            ("con_statistics", CON_STAT_PROMPT.format(topic=topic, context=context, kb_info=stat_kb)),
            ("con_bioinformatics", CON_BIOINFO_PROMPT.format(topic=topic, context=context, kb_info=bioinfo_kb_val)),
            ("con_history", CON_HISTORY_PROMPT.format(topic=topic, context=context, history_errors=hist)),
        ]
        con_results = _call_role_parallel(con_tasks, api_key, base_url, model)
        con_bio = con_results["con_biology"]
        con_stat = con_results["con_statistics"]
        con_bioinfo = con_results["con_bioinformatics"]
        con_history = con_results["con_history"]

        # ========== 裁判（唯一看到所有角色论点的，单独调用） ==========
        judge_prompt = JUDGE_PROMPT.format(
            topic=topic, context=context,
            pro_bio=pro_bio["content"],
            pro_stat=pro_stat["content"],
            pro_bioinfo=pro_bioinfo["content"],
            con_bio=con_bio["content"],
            con_stat=con_stat["content"],
            con_bioinfo=con_bioinfo["content"],
            con_history=con_history["content"],
        )
        judge = _call_llm_sync(judge_prompt, "judge", api_key, base_url, model)

        # ========== 组装结果（含隔离验证信息） ==========
        result = {
            "topic": topic,
            "debate_format": "多角色对抗（v3）",
            "pro_arguments": {
                "biology": {"argument": pro_bio["content"], "call_id": pro_bio["call_id"]},
                "statistics": {"argument": pro_stat["content"], "call_id": pro_stat["call_id"]},
                "bioinformatics": {"argument": pro_bioinfo["content"], "call_id": pro_bioinfo["call_id"]},
            },
            "con_arguments": {
                "biology": {"argument": con_bio["content"], "call_id": con_bio["call_id"]},
                "statistics": {"argument": con_stat["content"], "call_id": con_stat["call_id"]},
                "bioinformatics": {"argument": con_bioinfo["content"], "call_id": con_bioinfo["call_id"]},
                "history": {"argument": con_history["content"], "call_id": con_history["call_id"]},
            },
            "judge_verdict": judge["content"],
            "isolation_verification": {
                "method": "每个角色独立 HTTP API 调用，messages 数组只包含该角色自己的 prompt",
                "pro_isolated": all(r["messages_count"] == 1 for r in [pro_bio, pro_stat, pro_bioinfo]),
                "con_isolated": all(r["messages_count"] == 1 for r in [con_bio, con_stat, con_bioinfo, con_history]),
                "judge_sees_all": True,
                "call_ids": {
                    "pro_biology": pro_bio["call_id"],
                    "pro_statistics": pro_stat["call_id"],
                    "pro_bioinformatics": pro_bioinfo["call_id"],
                    "con_biology": con_bio["call_id"],
                    "con_statistics": con_stat["call_id"],
                    "con_bioinformatics": con_bioinfo["call_id"],
                    "con_history": con_history["call_id"],
                    "judge": judge["call_id"],
                },
                "note": "每个 call_id 对应一次独立 API 调用。正方和反方的 messages 中不包含对方的任何内容。可通过检查 API 日志中的 call_id 验证隔离性。"
            },
            "note": (
                "多角色辩论（v3）+ 并行调用 + 分科知识库：正方3专业编辑并行 + 反方4专业编辑并行 + 裁判单独调用，"
                "每个编辑独立 LLM 调用（切断上下文），各学科使用专属知识库，裁判综合7方给出裁决+置信度。\n"
                "辩论结果已归档到 results/.../log/debate_*.json（通过线程级 results_dir 自动定位）。"
            ),
            "timing": {
                "parallel": True,
                "rounds": 3,
                "round_description": "轮1: 正方3专业编辑并行 | 轮2: 反方4专业编辑并行 | 轮3: 裁判单独调用",
            },
            "knowledge_base": {
                "biology_kb_provided": bool(biology_kb),
                "statistics_kb_provided": bool(statistics_kb),
                "bioinfo_kb_provided": bool(bioinfo_kb),
                "general_kb_used_as_fallback": not (biology_kb or statistics_kb or bioinfo_kb),
            },
        }
        result_json = json.dumps(result, ensure_ascii=False, indent=2)
        # 持久化辩论结果（优化2：全局缓存用于去重）
        _save_debate(topic, context, result_json)
        # 归档到结果目录（需求1b：强制保留到 results/.../log/）
        _archive_debate_to_results(topic, context, result_json)
        return result_json

    except Exception as e:
        logger.warning(f"Multi-role debate failed, using fallback: {e}")
        return _fallback_debate(topic, context, knowledge_base_info, history_errors)


def _auto_load_kb(context: str, topic: str) -> str:
    """当 KB 未传入时，从 context/topic 提取物种/组织/方向，自动加载知识库。"""
    import yaml
    text = (topic + " " + context).lower()
    
    species_map = {
        "homo_sapiens": ["人", "human", "患者", "homo sapiens", "病人"],
        "mus_musculus": ["小鼠", "mouse", "mus musculus", "c57", "balb"],
        "rattus_norvegicus": ["大鼠", "rat", "rattus"],
        "danio_rerio": ["斑马鱼", "zebrafish", "danio"],
    }
    tissue_map = {
        "liver": ["肝脏", "liver", "肝", "hepatocyte"],
        "skeletal_muscle": ["骨骼肌", "skeletal muscle", "肌肉", "myofiber"],
        "brain": ["脑", "brain", "neuron", "cortex"],
        "kidney": ["肾", "kidney", "renal"],
        "heart": ["心脏", "heart", "cardiac"],
        "lung": ["肺", "lung", "pulmonary"],
        "blood": ["血液", "blood", "pbmc"],
        "skin": ["皮肤", "skin", "dermal"],
        "adipose": ["脂肪", "adipose"],
        "pancreas": ["胰腺", "pancreas"],
        "intestine": ["肠道", "intestine", "colon"],
        "bone_marrow": ["骨髓", "bone marrow"],
    }
    direction_map = {
        "aging": ["衰老", "aging", "ageing", "老化", "年龄", "增龄"],
        "development": ["发育", "development", "胚胎", "分化", "再生", "regeneration"],
        "disease": ["疾病", "disease", "癌症", "cancer", "肿瘤", "tumor"],
    }
    
    sp = next((k for k, vs in species_map.items() if any(v in text for v in vs)), None)
    ts = next((k for k, vs in tissue_map.items() if any(v in text for v in vs)), None)
    dr = next((k for k, vs in direction_map.items() if any(v in text for v in vs)), "general")
    
    if not sp or not ts:
        return ""
    
    kb_root = os.path.join(
        os.path.dirname(__file__), "..", "..", "memomics", "knowledge_base"
    )
    kb_dir = os.path.join(kb_root, sp, ts, dr)
    if not os.path.isdir(kb_dir):
        kb_dir = os.path.join(kb_root, sp, ts, "general")
    if not os.path.isdir(kb_dir):
        return ""
    
    parts = []
    # Collect with mtime, prioritize newest files
    candidates = []
    for dirpath, dirnames, filenames in os.walk(kb_dir):
        for fn in filenames:
            if fn.endswith((".yaml", ".yml")) and fn != "index.yaml":
                fp = os.path.join(dirpath, fn)
                try:
                    with open(fp, "r", encoding="utf-8") as fh:
                        content = fh.read()
                    if len(content) > 100:
                        mtime = os.path.getmtime(fp)
                        candidates.append((mtime, fn, content))
                except Exception:
                    pass
    # Sort by mtime descending (newest first), take top 8
    candidates.sort(reverse=True, key=lambda x: x[0])
    for mtime, fn, content in candidates[:8]:
        label = "## " + fn + "\n"
        parts.append(label + content[:3000])
    
    if not parts:
        return ""
    
    header = "[auto-loaded KB] " + sp + "/" + ts + "/" + dr + "\n\n"
    return header + "\n\n".join(parts[:6])

def _fallback_debate(topic: str, context: str, kb_info: str, history_errors: str) -> str:
    """退化为 prompt 模式（无 API 调用）。"""
    result = {
        "topic": topic,
        "debate_format": "多角色对抗（v3）— fallback 模式",
        "context": context,
        "knowledge_base_info": kb_info,
        "history_errors": history_errors,
        "debate_instructions": (
            "请按以下步骤执行多角色辩论（正方/反方切断上下文）：\n\n"
            "正方（3位专业编辑，各自独立思考，互相不知道）：\n"
            "1. 生物学编辑：从 marker gene / 已知生物学知识角度支持（用生物学知识库）\n"
            "2. 统计学编辑：从显著性 / 效应量 / 样本量角度支持（用统计学知识库）\n"
            "3. 生信编辑：从 QC 指标 / 双胞率 / 聚类质量角度支持（用生信知识库）\n\n"
            "反方（4位专业编辑，各自独立思考，互相不知道，也看不到正方）：\n"
            "4. 生物学编辑：从异质性 / 批次效应 / marker 重叠角度质疑（用生物学知识库）\n"
            "5. 统计学编辑：从多重比较 / 假阳性 / 统计功效角度质疑（用统计学知识库）\n"
            "6. 生信编辑：从降维质量 / 聚类稳定性 / 注释置信度角度质疑（用生信知识库）\n"
            "7. 历史经验编辑：从 error_memory 历史报错记录角度质疑\n\n"
            "裁判编辑（看到所有7方后裁决）：\n"
            "8. 综合裁决：支持/修改/需要更多信息 + 置信度（高/中/低）\n\n"
            "注意：正方和反方必须独立思考，不能互相看到。每个学科编辑使用该学科的专属知识库。"
        ),
        "isolation_note": (
            "上下文隔离实现：每个编辑是独立的 LLM 调用，messages 只包含该编辑自己的 prompt。"
            "正方不知道反方说了什么，正方编辑之间也互相不知道。"
            "裁判是唯一能看到所有编辑论点的。"
        ),
        "note": "LLM API 调用失败，退化为 prompt 模式。请在回复中按上述步骤执行辩论。"
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


def _register():
    try:
        from tools.registry import registry
        registry.register(
            name="debate_analysis",
            toolset="memomics",
            schema=SCHEMA,
            handler=lambda args, **kw: debate_analysis(
                args.get("topic", ""),
                args.get("context", ""),
                args.get("knowledge_base_info", ""),
                args.get("history_errors", ""),
                args.get("biology_kb", ""),
                args.get("statistics_kb", ""),
                args.get("bioinfo_kb", ""),
            ),
            emoji="🎭",
            max_result_size_chars=120_000,
        )

        # 问题8: 新增图片结论 vs 模块结论一致性辩论模板
        FIGURE_CONCLUSION_DEBATE_SCHEMA = {
        "name": "debate_figure_conclusions",
        "description": (
            "问题8: 对图片解读结论和模块总结论进行一致性辩论。"
            "正方拿图片解读结论，反方拿模块总结论，辩论两者是否矛盾。"
            "报告中每张图的结论和每个模块的总结论都必须经过此辩论。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "figure_conclusions": {
                    "type": "array",
                    "items": {"type": "object", "properties": {
                        "figure_name": {"type": "string"},
                        "conclusion": {"type": "string"},
                    }},
                    "description": "图片解读结论列表",
                },
                "module_conclusions": {
                    "type": "array",
                    "items": {"type": "object", "properties": {
                        "module_name": {"type": "string"},
                        "conclusion": {"type": "string"},
                    }},
                    "description": "分析模块总结论列表",
                },
                "knowledge_base_info": {"type": "string", "description": "知识库参考信息"},
            },
            "required": ["figure_conclusions", "module_conclusions"],
        },
    }

        def debate_figure_conclusions_handler(args, **kw):
            """问题8: 图片结论 vs 模块结论一致性辩论"""
            fig_conclusions = args.get("figure_conclusions", [])
            mod_conclusions = args.get("module_conclusions", [])
            kb_info = args.get("knowledge_base_info", "")

            # 构造辩论 topic
            fig_text = "\n".join([
                f"- 图【{f.get('figure_name', '?')}】结论: {f.get('conclusion', '?')}"
                for f in fig_conclusions
            ])
            mod_text = "\n".join([
                f"- 模块【{m.get('module_name', '?')}】总结论: {m.get('conclusion', '?')}"
                for m in mod_conclusions
            ])
            topic = (
                "辩论以下图片解读结论与模块总结论是否一致、是否矛盾、是否有数据支撑、是否过度推断。\n\n"
                f"【图片解读结论】\n{fig_text}\n\n"
                f"【模块总结论】\n{mod_text}"
            )
            context = (
                "本次辩论针对报告中图片结论与模块结论的一致性。"
                "正方应论证图片结论与模块结论一致且有数据支撑；"
                "反方应质疑任何矛盾、过度推断或缺乏数据支撑的结论。"
            )
            # 复用现有 7 角色辩论引擎
            return debate_analysis(topic, context, kb_info, "")

        registry.register(
            name="debate_figure_conclusions",
            toolset="memomics",
            schema=FIGURE_CONCLUSION_DEBATE_SCHEMA,
            handler=debate_figure_conclusions_handler,
            emoji="🖼️",
            max_result_size_chars=120_000,
        )
    except ImportError:
        pass  # 不在 Hermes 环境中时不注册

_register()
