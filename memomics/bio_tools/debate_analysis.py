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
import re
import threading
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

# === 会话级隔离（ContextVar，替代 threading.local） ===
# 2026-08-16 修复：threading.local 不跨线程传播——Hermes 的 tool_executor 会把
# 工具调用丢到 ThreadPoolExecutor worker 线程执行（tool_executor.py 的
# _execute_tool_calls_concurrent），worker 线程拿不到 _do_run 线程里
# set_session_context 设置的 threading.local 值，导致 execute_r/execute_python
# 在工具线程里 get_session_sid() 返回空 → 全部退化到 "default" kernel（会话串染）。
# ContextVar 会被 Hermes 的 propagate_context_to_thread（contextvars.copy_context）
# 自动传播到 worker 线程，会话隔离才对工具执行真正生效。
import contextvars as _contextvars

_sid_var = _contextvars.ContextVar("memomics_session_sid", default="")
_results_dir_var = _contextvars.ContextVar("memomics_session_results_dir", default="")

def set_session_context(sid: str = "", results_dir: str = ""):
    """设置当前上下文（线程 + 其派生的工具 worker 线程）的会话上下文。

    由 server.py 在 agent 启动 / executor 线程入口调用。
    """
    _sid_var.set(sid or "")
    _results_dir_var.set(results_dir or "")

def get_session_sid() -> str:
    """获取当前会话 ID（ContextVar，跨工具 worker 线程传播）。"""
    return _sid_var.get()

def get_session_results_dir() -> str:
    """获取当前结果目录（ContextVar，跨工具 worker 线程传播）。"""
    return _results_dir_var.get()

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
            },
            "mode": {
                "type": "string",
                "description": "辩论架构（P0 参数化，2026-08-10）: homogeneous=单模型8角色(默认/现状) | adversarial=正方反方裁判三组异构模型 | multi_model=每个角色独立模型 | temperature=同模型多温度采样。留空用 config.yaml debate.mode。",
                "default": ""
            },
            "rounds": {
                "type": "integer",
                "description": "辩论轮数，默认 1。>1 时第 2 轮起向正反方注入上一轮裁判摘要（轮间隔离：角色依然看不到彼此原始论点）。",
                "default": 1
            },
            "role_model_map": {
                "type": "object",
                "description": "角色级模型覆盖 {角色名: {model, provider}}，角色名 ∈ pro_biology/pro_statistics/pro_bioinformatics/con_biology/con_statistics/con_bioinformatics/con_history/judge。优先级最高。",
                "default": {}
            },
            "level": {
                "type": "string",
                "enum": ["L1", "L2"],
                "description": "辩论级别（门控判定，2026-08-11）: L2=完整 8 角色辩论（默认，结论合成/入库前） | L1=轻量采样辩论（默认模型上下文切断正反采样 N 组 + 裁判总结，成本约 1/3，脚本设计/统计级结论用）。",
                "default": "L2"
            },
            "species": {
                "type": "string",
                "description": "本次分析物种（human/mouse/猴 等）— 自动知识库注入按物种优先排序",
                "default": ""
            },
            "tissue": {
                "type": "string",
                "description": "本次分析组织（muscle/brain/liver 等）— 自动注入的组织过滤",
                "default": ""
            },
            "direction": {
                "type": "string",
                "description": "本次研究方向（aging/发育/疾病 等）— 自动注入的方向过滤",
                "default": ""
            },
            "auto_kb": {
                "type": "boolean",
                "description": "自动检索知识库注入（默认 true）：biology_kb 按物种+组织+方向优先（其他物种降权参考），bioinfo_kb 按话题匹配（跨物种可参考），statistics_kb 不注入（LLM 自行判断）。显式传 kb 参数时自动注入跳过对应库。",
                "default": True
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


def _call_llm_sync(prompt: str, label: str, api_key: str, base_url: str, model: str,
                    temperature: float = 0.7, max_tokens: int = 4096) -> dict:
    """独立 LLM 调用 — 每个角色一个独立的 messages 数组，切断上下文。

    返回 dict: {content, call_id, isolation_verified}
    - call_id: 唯一调用 ID，可用于追踪
    - isolation_verified: True 表示这是独立调用（messages 只有 1 条）

    线程安全：每次调用创建独立的 httpx.Client，不共享状态，可安全并行。
    P0(2026-08-10): temperature 可配置（temperature 模式按角色分配采样温度）。
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
        "max_tokens": max_tokens,
        "temperature": temperature,
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
                    # 🔧 P2-2 修复(2026-08-01): reasoning_content 是思维链草稿，不是精炼论点
                    # 标记为草稿，让辩论使用方知道这是 fallback 内容
                    content = "[reasoning草稿(非精炼论点)] " + content[:2000]
                if content and len(content.strip()) > 10:
                    return {
                        "content": content,
                        "call_id": call_id,
                        "isolation_verified": True,
                        "messages_count": 1,  # 只有 1 条消息 = 上下文已隔离
                        "used_reasoning_fallback": bool(not msg.get("content") or len(msg.get("content", "").strip()) < 10),
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

def _call_role_parallel(tasks: list, cfg: dict = None) -> dict:
    """调用多个角色，返回 {label: result_dict}。

    受控并发（2026-08-14 修复）：全串行最坏 8角色x3重试x120s=48min 卡死；
    全并发 8 路又触发 provider 并发/配额限制导致 7 次 8/8 全失败。
    折中：max_workers=3（可用 MEMOMICS_DEBATE_MAX_WORKERS 覆盖），
    每角色仍独立 HTTP 调用（上下文隔离不变），_call_llm_sync 内部 3 次重试
    兜底瞬时 429。

    P0(2026-08-10): cfg 可传辩论配置，每个角色按 _resolve_role_llm 独立解析模型
    （异构/对抗/温度模式）。cfg=None 时行为=现状（环境变量单模型）。
    """
    def _run_one(label, prompt):
        try:
            return label, _call_llm_role(label, prompt, cfg)
        except Exception as e:
            logger.warning(f"debate {label} call failed: {e}")
            return label, {
                "content": f"[{label} 辩论生成失败]",
                "call_id": f"{label}_{int(time.time() * 1000) % 1000000}",
                "isolation_verified": True,
                "messages_count": 1,
                "error": True,
            }

    results = {}
    try:
        _mw = int(os.environ.get("MEMOMICS_DEBATE_MAX_WORKERS", "3"))
    except Exception:
        _mw = 3
    max_workers = max(1, min(_mw, len(tasks) or 1))
    if max_workers <= 1:
        for label, prompt in tasks:
            _l, _r = _run_one(label, prompt)
            results[_l] = _r
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as _ex:
            _futures = [_ex.submit(_run_one, label, prompt) for label, prompt in tasks]
            for _f in _futures:
                _l, _r = _f.result()
                results[_l] = _r
    return results


# ==================== 辩论配置（P0 参数化 2026-08-10） ====================

ALL_ROLES = ["pro_biology", "pro_statistics", "pro_bioinformatics",
             "con_biology", "con_statistics", "con_bioinformatics",
             "con_history", "judge"]

# temperature 模式下按角色哈希分配的采样温度池（L1 对照组用）
_TEMP_POOL = [0.3, 0.5, 0.7, 0.9, 1.1]


def _get_config_path() -> Path:
    """定位 hermes_home/config.yaml（与 _get_debates_dir 同源）。"""
    try:
        for p in list(sys.path):
            if p.endswith('hermes-agent') or p.endswith('hermes-agent\\') or p.endswith('hermes-agent/'):
                break
        from hermes_constants import get_hermes_home
        base = Path(get_hermes_home())
    except Exception:
        base = Path(os.environ.get("HERMES_HOME", str(Path(__file__).resolve().parents[2] / "hermes_home")))
    return base / "config.yaml"


def _load_debate_config() -> dict:
    """读取 config.yaml 的 debate: 段。缺省返回默认值（行为=现状 homogeneous）。

    config 结构（详见 docs/debate-core-design.md）:
      debate:
        mode: homogeneous | adversarial | multi_model | temperature
        rounds: 1
        judge: {model, provider}
        pro:   {model, provider}
        con:   {model, provider}
        role_model_map: {"pro_biology": {model, provider}, ...}
        cache_ttl_hours: 72
    """
    default = {
        "mode": "homogeneous",
        "rounds": 1,
        "judge": {}, "pro": {}, "con": {},
        "role_model_map": {},
        "cache_ttl_hours": 72,
        # C2/C3(2026-08-11): L1 轻量采样 + token 预算
        "l1": {"samples": 3, "strategy": "sampling"},
        "token_budget": 0,  # 0=不限；>0 为单会话辩论 token 预算
    }
    try:
        import yaml
        cfg_path = _get_config_path()
        if not cfg_path.exists():
            return default
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        debate_cfg = data.get("debate") or {}
        if not isinstance(debate_cfg, dict):
            return default
        merged = dict(default)
        merged.update({k: v for k, v in debate_cfg.items() if v is not None})
        return merged
    except Exception as e:
        logger.warning(f"Failed to load debate config, using defaults: {e}")
        return default


def _load_provider_keys() -> dict:
    """读取 hermes_home/provider_keys.json: {provider_id: {api_key, base_url}}。"""
    try:
        keys_path = _get_config_path().parent / "provider_keys.json"
        if not keys_path.exists():
            return {}
        with open(keys_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to load provider_keys.json: {e}")
        return {}


def _debate_fingerprint(mode: str, rounds: int, role_model_map: dict, cfg: dict = None,
                        level: str = "L2") -> str:
    """模式指纹 — 参与缓存 key，防止不同辩论架构/级别的结果互相污染（P0 级）。

    任何影响辩论产出的配置（mode/rounds/角色模型分配/分组模型/门控级别）变化 → 指纹变化 → 新缓存条目。
    P0-5(2026-08-10): 增加 cfg 参数，judge/pro/con 分组配置也计入指纹——
    真实数据测试发现：改了 judge 模型但 mode 不变时，旧缓存（坏结果）仍会命中。
    C3(2026-08-11): 增加 level 参数（默认 L2 = 现状指纹，向后兼容）——
    L1 轻量采样与 L2 完整辩论的结果必须隔离，否则脚本阶段的 L1 结果污染结论阶段的 L2。
    """
    parts = [f"mode={mode}", f"rounds={rounds}"]
    if level and level != "L2":
        parts.append(f"level={level}")
    if cfg:
        for grp in ("judge", "pro", "con"):
            gc = (cfg.get(grp) or {})
            if gc:
                parts.append(f"{grp}={gc.get('provider','?')}/{gc.get('model','?')}")
    if role_model_map:
        for k in sorted(role_model_map):
            v = role_model_map[k] or {}
            parts.append(f"{k}={v.get('provider','?')}/{v.get('model','?')}")
    return "|".join(parts)


def _resolve_role_llm(label: str, cfg: dict) -> dict:
    """解析某个角色的 (api_key, base_url, model, temperature)。

    优先级：
    1. role_model_map[label]（最细粒度，可覆盖一切）
    2. mode 分组：adversarial → pro/con/judge 三组；multi_model → 按角色从模型池稳定分配
    3. 默认：环境变量 DEEPSEEK_API_KEY/BASE_URL/MODEL（现状行为 = homogeneous）
    返回 dict {api_key, base_url, model, temperature, provider}
    """
    mode = (cfg or {}).get("mode", "homogeneous")
    provider_keys = _load_provider_keys()
    env_key = os.environ.get("DEEPSEEK_API_KEY", "")
    # 2026-08-15: 移除已死默认端点(dcsapi 401)；空 URL 时按 key 匹配 provider_keys 回退
    env_url = os.environ.get("DEEPSEEK_BASE_URL", "")
    env_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

    def _from_provider(pid: str, model: str):
        if pid and pid in provider_keys:
            info = provider_keys[pid]
            return {
                "api_key": info.get("api_key", ""),
                "base_url": (info.get("base_url") or "").rstrip("/"),
                "model": model or env_model,
                "temperature": 0.7,
                "provider": pid,
            }
        return None

    # ① role_model_map 细粒度覆盖
    rmm = (cfg or {}).get("role_model_map") or {}
    if label in rmm and rmm[label]:
        rv = _from_provider(rmm[label].get("provider", ""), rmm[label].get("model", ""))
        if rv and rv["api_key"]:
            return rv

    # ② 分组配置（judge/pro/con）在任何 mode 下都生效（P0-4 修复 2026-08-10：
    #    真实数据测试发现 homogeneous 模式下 judge 用 deepseek-v4-flash 长 prompt
    #    content 为空 → 配了 judge 模型却不生效。分组配置 = 按角色指定模型。）
    _group = "judge" if label == "judge" else ("pro" if label.startswith("pro_") else "con")
    _gc = (cfg or {}).get(_group) or {}
    if _gc:
        rv = _from_provider(_gc.get("provider", ""), _gc.get("model", ""))
        if rv and rv["api_key"]:
            return rv
        # 分组配置缺 key → 回退环境变量（但保留分组模型名）
        if _gc.get("model") and env_key:
            return {"api_key": env_key, "base_url": env_url, "model": _gc["model"],
                    "temperature": 0.7, "provider": "env"}

    # ③ mode 分组（adversarial 的分组已由 ② 覆盖；此处只剩 multi_model/temperature）
    if mode == "multi_model":
        # 按角色名哈希从可用 provider 稳定分配（同一角色永远同一模型）
        # P2-9(2026-08-10): 跳过已验证 401 的 dcs-cloud（与默认回退策略一致），
        # 否则按哈希分配到 dcs-cloud 的角色必然失败。
        candidates = []
        for pid, info in provider_keys.items():
            if pid == "dcs-cloud":
                continue
            if info.get("api_key") and info.get("base_url"):
                candidates.append(pid)
        if candidates:
            import hashlib as _hl
            idx = int(_hl.md5(label.encode("utf-8")).hexdigest(), 16) % len(candidates)
            pid = candidates[idx]
            # P2-10(2026-08-10): model 按 provider 用默认模型（deepseek 官方无 glm 系列，
            # 原来用 env_model="glm-5.2" 直接 400 Bad Request）
            _prov_default_model = {"deepseek": "deepseek-v4-flash"}
            return {"api_key": provider_keys[pid]["api_key"],
                    "base_url": provider_keys[pid]["base_url"].rstrip("/"),
                    "model": _prov_default_model.get(pid, env_model),
                    "temperature": 0.7, "provider": pid}

    elif mode == "temperature":
        # 同模型多温度采样（对照实验：多样性是否必须来自异构）
        # P2-8(2026-08-10): 修复——之前直接返回 env_key，无环境变量时
        # api_key 为空 → "Illegal header value b'Bearer '" 8/8 全失败。
        # 现在复用默认回退（env → provider_keys），只覆盖 temperature。
        import hashlib as _hl
        _base = _default_role_llm(env_key, env_url, env_model, provider_keys)
        idx = int(_hl.md5(label.encode("utf-8")).hexdigest(), 16) % len(_TEMP_POOL)
        _base["temperature"] = _TEMP_POOL[idx]
        return _base

    # ③ 默认（homogeneous / 无配置）
    return _default_role_llm(env_key, env_url, env_model, provider_keys)


def _default_role_llm(env_key: str, env_url: str, env_model: str, provider_keys: dict) -> dict:
    """默认模型解析：环境变量优先，缺失时回退 provider_keys.json。

    与 webui/server.py 策略对齐 — 跳过已验证 401 的 dcs-cloud，优先 deepseek 官方，其余兜底。
    P2-8(2026-08-10): 抽成独立函数供 temperature 模式复用（原 temperature 直接返回 env_key，
    无环境变量时 api_key 为空 → 8/8 全失败 "Illegal header value b'Bearer '"）。
    """
    if env_key:
        # 2026-08-15: base_url 为空时按 key 匹配 provider_keys；再不行回退 deepseek 官方
        _url = env_url or ""
        if not _url:
            for pid, info in provider_keys.items():
                if info.get("api_key") == env_key and info.get("base_url"):
                    _url = info["base_url"].rstrip("/")
                    break
        if not _url:
            _url = "https://api.deepseek.com/v1"
        return {"api_key": env_key, "base_url": _url, "model": env_model,
                "temperature": 0.7, "provider": "env"}
    # 环境变量缺失（如直接命令行调用、不经 server 的 _sync_debate_env）→
    # 回退 provider_keys.json
    _known_dead = {"dcs-cloud"}
    _fallback_order = sorted(provider_keys.keys(),
                             key=lambda pid: (pid in _known_dead, pid != "deepseek"))
    for pid in _fallback_order:
        info = provider_keys[pid]
        if info.get("api_key") and info.get("base_url"):
            # 各 provider 默认模型（与 webui/server.py 默认一致；deepseek 官方无 glm 系列）
            _prov_default_model = {"deepseek": "deepseek-v4-flash"}
            return {"api_key": info["api_key"],
                    "base_url": info["base_url"].rstrip("/"),
                    "model": _prov_default_model.get(pid, env_model),
                    "temperature": 0.7, "provider": pid}
    return {"api_key": env_key, "base_url": env_url, "model": env_model,
            "temperature": 0.7, "provider": "env"}


# C1(2026-08-11): token 分级 — 论点角色不需要 4096，judge 需要综合 7 方给结构化裁决
_ROLE_MAX_TOKENS = {"judge": 2048}  # 其余角色（pro/con）默认 1024
_ROLE_MAX_TOKENS_DEFAULT = 1024


def _role_max_tokens(label: str) -> int:
    return _ROLE_MAX_TOKENS.get(label, _ROLE_MAX_TOKENS_DEFAULT)


def _call_llm_role(label: str, prompt: str, cfg: dict) -> dict:
    """按角色解析模型后调用 _call_llm_sync（隔离性不变：messages 只有该角色自己的 prompt）。"""
    rc = _resolve_role_llm(label, cfg)
    return _call_llm_sync(prompt, label, rc["api_key"], rc["base_url"], rc["model"],
                          temperature=rc["temperature"], max_tokens=_role_max_tokens(label))


def _role_model_id(label: str, cfg: dict) -> str:
    """角色的实际模型标识（provider/model），写入结果供实验记录。"""
    rc = _resolve_role_llm(label, cfg)
    return f"{rc['provider']}/{rc['model']}"


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
        base = Path(os.environ.get("HERMES_HOME", str(Path(__file__).resolve().parents[2] / "hermes_home")))
    debates_dir = base / "skills" / "bioinformatics" / "_debates"
    debates_dir.mkdir(parents=True, exist_ok=True)
    return debates_dir


def _topic_hash(topic: str, context: str, fingerprint: str = "") -> str:
    """生成 topic+context 的 hash，用于历史辩论匹配。

    P0(2026-08-10): 增加 fingerprint 参数（mode/rounds/角色模型指纹）——
    不同架构的辩论结果必须使用不同缓存 key，防止互相污染。
    不传 fingerprint 时保持旧行为（旧存档仍可读）。
    """
    combined = (topic.strip().lower() + "||" + context.strip().lower() + "||" + fingerprint).encode("utf-8")
    return hashlib.md5(combined).hexdigest()[:16]


def _topic_hash_legacy(topic: str, context: str) -> str:
    """旧版 hash（2026-07 及以前存档）：lower() 但无 strip()。仅供 _load_debate 读取兼容。"""
    combined = (topic.lower() + "||" + context.lower()).encode("utf-8")
    return hashlib.md5(combined).hexdigest()[:16]


def _save_debate(topic: str, context: str, result_json: str, fingerprint: str = "") -> None:
    """将辩论结果保存到 _debates/ 目录，文件名 = topic_hash(fingerprint).json。"""
    try:
        h = _topic_hash(topic, context, fingerprint)
        path = _get_debates_dir() / f"{h}.json"
        record = {
            "topic": topic,
            "context": context,
            "hash": h,
            "fingerprint": fingerprint,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "result": json.loads(result_json),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        logger.info(f"debate saved to {path}")
    except Exception as e:
        logger.warning(f"Failed to save debate: {e}")


def _load_debate(topic: str, context: str, max_age_hours: int = 72, fingerprint: str = "") -> dict | None:
    """查询历史辩论结果。返回 dict 或 None。

    匹配条件：topic+context+fingerprint 的 hash 完全匹配（P0：指纹隔离架构）。
    过期条件：超过 max_age_hours 小时的记录不返回（默认 72 小时）。
    """
    try:
        h = _topic_hash(topic, context, fingerprint)
        path = _get_debates_dir() / f"{h}.json"
        if not path.exists() and not fingerprint:
            # 读取兼容（P0 2026-08-10）：2026-07 及以前存档用无 lower() 的旧 hash 算法
            h_legacy = _topic_hash_legacy(topic, context)
            path_legacy = _get_debates_dir() / f"{h_legacy}.json"
            if path_legacy.exists():
                path = path_legacy
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
        # 🔧 P0-1 修复: 缓存中的失败结果(含error标记或占位符)不返回
        _cached_result = record.get("result", {})
        if _cached_result.get("error") or "辩论生成失败" in str(_cached_result.get("judge_verdict", "")):
            logger.warning(f"debate {h} cached result is FAILED, ignoring")
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


def _extract_json_candidates(text: str) -> list:
    """括号平衡扫描提取所有顶层 JSON 对象候选（支持任意嵌套）。"""
    cands, i, n = [], 0, len(text)
    while i < n:
        if text[i] != '{':
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
                if depth == 0:
                    cands.append(text[i:j + 1])
                    break
            j += 1
        if j >= n:
            break
        i = j + 1
    return cands


def _parse_judge_json(text: str) -> dict:
    """解析 judge 输出为结构化裁决 dict（A3 抽取，2026-08-11）。

    P0-3(2026-08-10): 真实数据测试发现 deepseek-v4-flash 的 content 常为空，
    fallback 的 reasoning_content 是思维链草稿，其中 JSON 片段可能残缺/含 "verdict": null。
    A3(2026-08-11): 正则 [^{}]* 无法匹配嵌套 recommended_params → 改括号平衡扫描。
    策略: 扫描全部顶层 JSON 对象 → 取首个 verdict 非空的 → 否则 ValueError。

    Returns: dict 含 verdict（非空）
    Raises: ValueError 无有效裁决
    """
    clean = text.replace("```json", "").replace("```", "").strip()
    for cand in _extract_json_candidates(clean):
        try:
            o = json.loads(cand)
        except Exception:
            continue
        if isinstance(o, dict) and o.get("verdict") not in (None, ""):
            return o
    # B3(2026-08-14): 兜底解析 — 部分网关把思考链塞进 content，JSON 结构残缺，
    # 但 verdict/confidence 字段本身完整。直接正则抓取，避免 L1→L2 无谓升级。
    _m = re.search(r'"verdict"\s*:\s*"([a-zA-Z_]+)"', text)
    if _m and _m.group(1).lower() in ("support", "modify", "need_more_info", "ok"):
        _out = {"verdict": _m.group(1).lower()}
        _c = re.search(r'"confidence"\s*:\s*"(high|medium|low)"', text, re.IGNORECASE)
        if _c:
            _out["confidence"] = _c.group(1).lower()
        _r = re.search(r'"recommended_params"\s*:\s*(\{.*?\})\s*[,}\]]', text, re.DOTALL)
        if _r:
            try:
                _out["recommended_params"] = json.loads(_r.group(1))
            except Exception:
                _out["recommended_params"] = {}
        return _out
    raise ValueError("judge JSON 中无有效 verdict")


def _check_consistency(result: dict) -> list:
    """B1(2026-08-11): 裁决一致性校验 — 返回矛盾点列表（空=一致）。

    实证 bug：_debates/ 中 3 条 need_more_info+high（信息不足却高置信）。
    矛盾裁决不得回流 skill_evolution（B2）。
    """
    issues = []
    verdict = str(result.get("verdict", "")).lower()
    conf = str(result.get("confidence", "")).lower()
    if verdict == "need_more_info" and conf == "high":
        issues.append("verdict=need_more_info 但 confidence=high（信息不足不可能高置信）")
    if verdict == "modify" and not (result.get("recommended_params") or {}):
        issues.append("verdict=modify 但 recommended_params 为空（要求修改却无建议）")
    scores = result.get("scores") or {}
    if scores and all((v or 0) == 0 for v in scores.values()) and conf != "low":
        issues.append("scores 全为 0 但 confidence 非 low")
    return issues


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


def _auto_match_skill(topic: str) -> str:
    """P2-12(2026-08-10): 从 topic 自动匹配 skill 名 — 断点 A 修复。

    reflow_skill 未配置时，扫描 hermes_home/skills/bioinformatics/ 下各 skill
    的 SKILL.md frontmatter name + skill.json name，若 topic（小写）包含
    skill 名或其中文名，选最长匹配项。让裁决能自动沉淀到正确的 skill.json。
    匹配不到返回 ""（只归档不写 skill.json，保持安全默认）。
    """
    try:
        base = _get_config_path().parent / "skills" / "bioinformatics"
        if not base.exists():
            return ""
        text = (topic or "").lower()
        best, best_len = "", 0
        for sk_dir in base.iterdir():
            if not sk_dir.is_dir():
                continue
            names = []
            for fname in ("SKILL.md", "skill.json"):
                fp = sk_dir / fname
                if not fp.exists():
                    continue
                try:
                    content = fp.read_text(encoding="utf-8")[:2000]
                except Exception:
                    continue
                m = re.search(r'^name:\s*(.+)$', content, re.M)
                if m:
                    names.append(m.group(1).strip().strip('"\' '))
                if fname == "skill.json":
                    try:
                        sj = json.loads(content)
                        if sj.get("name"):
                            names.append(str(sj["name"]))
                    except Exception:
                        pass
            for n in names:
                nl = n.lower()
                if nl and nl in text and len(nl) > best_len:
                    best, best_len = n, len(nl)
        return best
    except Exception as e:
        logger.warning(f"auto_match_skill failed: {e}")
        return ""


def _reflow_verdict(result: dict) -> None:
    """P1(2026-08-10): 辩论裁决回流 — verdict → skill_evolution.record_verdict。

    规则（与设计文档 L4 一致）:
    - 仅成功辩论（无 error）且 judge 裁决已结构化时触发
    - confidence 为 low 时不沉淀（结果不可靠，留给 agent 判断）
    - skill_name 从 config.yaml debate.reflow_skill 读取；缺省为空 →
      只归档 run_record_*_verdict.json，不写 skill.json（避免误入无关 skill）
    - 失败静默：回流失败不阻断主流程
    """
    try:
        if result.get("error") or not result.get("verdict"):
            return
        conf = str(result.get("confidence", "low")).lower()
        if conf == "low":
            return
        # B2(2026-08-11): 矛盾裁决禁止回流（垃圾不得入库）
        if _check_consistency(result):
            logger.warning("Debate verdict inconsistent, skip reflow")
            return
        cfg = _load_debate_config()
        skill_name = cfg.get("reflow_skill") or ""
        if not skill_name:
            # P2-12(2026-08-10): 断点 A — 未配置 reflow_skill 时自动匹配
            skill_name = _auto_match_skill(str(result.get("topic", "")))
        # 2026-08-14 修复：旧代码取 pro_bio/con_bio/judge（不存在的 key），call_ids 恒为空。
        # 正确结构是 pro_arguments/con_arguments（biology/statistics/bioinformatics/history 子键）。
        _call_ids = []
        for _grp in (result.get("pro_arguments", {}), result.get("con_arguments", {})):
            if isinstance(_grp, dict):
                for _v in _grp.values():
                    if isinstance(_v, dict) and _v.get("call_id"):
                        _call_ids.append(_v["call_id"])
        evidence = json.dumps({
            "call_ids": _call_ids[:10],
            "scores": result.get("scores", {}),
            "kb_used": result.get("knowledge_base", {}),
        }, ensure_ascii=False)[:300]
        try:
            from bio_tools.skill_evolution import skill_evolution
        except ImportError:
            from memomics.bio_tools.skill_evolution import skill_evolution
        skill_evolution(
            action="record_verdict",
            skill_name=skill_name,
            topic=str(result.get("topic", ""))[:100],
            result_summary=str(result.get("judge_verdict", ""))[:500],
            params_used=json.dumps(result.get("recommended_params", {}), ensure_ascii=False)[:300],
            # 2026-08-14 修复：旧代码取 confidence_score（不存在的 key），score 恒为 0.7。
            # 改为按 confidence 字符串映射数值分。
            score=float({"high": 0.9, "medium": 0.6, "low": 0.3}.get(
                str(result.get("confidence", "")).lower(), 0.7)),
            reason=evidence,
        )
        logger.info("Debate verdict reflowed to skill_evolution.record_verdict")
    except Exception as e:
        logger.warning(f"Debate verdict reflow failed (non-blocking): {e}")


_L1_PRO_PROMPT = """你是生信分析评审中的**正方编辑**。请就以下决策给出简洁的支持论证（150字以内）。

主题：{topic}
背景：{context}
知识库参考：{kb_info}

输出格式（严格 JSON）：
{{"argument": "支持理由（含具体参数/阈值建议）", "recommended_params": {{}} }}"""

_L1_CON_PROMPT = """你是生信分析评审中的**反方编辑**。请就以下决策给出简洁的质疑论证（150字以内）。

主题：{topic}
背景：{context}
知识库参考：{kb_info}

输出格式（严格 JSON）：
{{"argument": "质疑理由（含风险点）", "risk_params": {{}} }}"""

_L1_JUDGE_PROMPT = """你是生信分析评审的**裁判**。{n}组正反方编辑（独立评审、互不可见）对以下决策给出了意见，请总结双方并裁决。

主题：{topic}
背景：{context}

{debates}

输出格式（严格 JSON）：
{{"verdict": "ok|modify|need_more_info", "confidence": "high|medium|low", "recommended_params": {{}}, "reasoning": "50字内总结"}}"""


def _debate_l1_lightweight(topic: str, context: str, kb: str, cfg: dict, fingerprint: str) -> str:
    """C2(2026-08-11): L1 轻量采样辩论。

    架构（按用户要求）：使用当前选择的默认模型，正方与反方**上下文切断**独立采样，
    最后裁判总结双方裁决——全部同一模型，但每次调用 messages 独立（切断上下文）。
    N 次采样用温度梯度制造多样性（成本约 L2 的 1/3：2N+1 次短调用 vs 8 次长调用）。
    """
    l1_cfg = cfg.get("l1") or {}
    n_samples = max(1, min(5, int(l1_cfg.get("samples", 3))))
    rc = _default_role_llm(os.environ.get("DEEPSEEK_API_KEY", ""),
                           os.environ.get("DEEPSEEK_BASE_URL", ""),
                           os.environ.get("DEEPSEEK_MODEL", ""),
                           _load_provider_keys())
    if not rc["api_key"]:
        return _fallback_debate(topic, context, kb, "")

    debates_text = []
    sample_records = []
    for i in range(n_samples):
        temp = _TEMP_POOL[i % len(_TEMP_POOL)]
        pro_prompt = _L1_PRO_PROMPT.format(topic=topic, context=context, kb_info=kb or "无")
        con_prompt = _L1_CON_PROMPT.format(topic=topic, context=context, kb_info=kb or "无")
        pro = _call_llm_sync(pro_prompt, f"l1_pro_{i}", rc["api_key"], rc["base_url"],
                             rc["model"], temperature=temp, max_tokens=512)
        con = _call_llm_sync(con_prompt, f"l1_con_{i}", rc["api_key"], rc["base_url"],
                             rc["model"], temperature=temp + 0.1, max_tokens=512)
        if pro.get("error") or con.get("error"):
            continue
        debates_text.append(f"### 第{i+1}组（采样温度 {temp:.1f}）\n"
                            f"正方：{pro['content'][:400]}\n反方：{con['content'][:400]}")
        sample_records.append({"pro": pro["content"][:500], "con": con["content"][:500],
                               "pro_call_id": pro["call_id"], "con_call_id": con["call_id"]})

    if not debates_text:
        return _fallback_debate(topic, context, kb, "")

    judge_prompt = _L1_JUDGE_PROMPT.format(n=len(debates_text), topic=topic,
                                           context=context, debates="\n\n".join(debates_text))
    judge = _call_llm_sync(judge_prompt, "l1_judge", rc["api_key"], rc["base_url"],
                           rc["model"], temperature=0.3, max_tokens=1024)

    result = {
        "topic": topic,
        "debate_format": f"L1 轻量采样辩论（{len(debates_text)} 组正反采样 + 裁判）",
        "level": "L1",
        "model": f"{rc['provider']}/{rc['model']}",
        "samples": sample_records,
        "judge_verdict": judge.get("content", "")[:3000],
        "verdict": "need_more_info", "confidence": "low",
        "recommended_params": {},
        "isolation_verification": {
            "pro_con_isolated": True, "messages_count": 1,
            "note": "每组正反方独立调用（上下文切断），裁判最后总结双方裁决，全部同一模型。",
        },
    }
    if not judge.get("error"):
        try:
            obj = _parse_judge_json(judge["content"])
            result["verdict"] = obj.get("verdict") or "need_more_info"
            result["confidence"] = obj.get("confidence") or "low"
            result["recommended_params"] = obj.get("recommended_params", {}) or {}
        except Exception as e:
            result["verdict_parse_error"] = str(e)[:100]

    # B2 一致性门禁（与 L2 同规则）
    issues = _check_consistency(result)
    if issues:
        result["confidence"] = "low"
        result["consistency_issues"] = issues

    result_json = json.dumps(result, ensure_ascii=False, indent=2)
    # 2026-08-14 修复：矛盾裁决（consistency_issues 非空）不入全局缓存，
    # 否则下次同 topic+context 命中会直接返回 low 结果，污染 72h 复用。
    if not result.get("consistency_issues"):
        _save_debate(topic, context, result_json, fingerprint=fingerprint)
    _archive_debate_to_results(topic, context, result_json)
    _reflow_verdict(result)
    return result_json


def _auto_kb_injection(topic: str, context: str = "", species: str = "",
                       tissue: str = "", direction: str = "",
                       max_per_kb: int = 4, max_chars: int = 800) -> dict:
    """自动检索知识库并按学科路由注入（2026-08-13 用户三例设计）。

    - biology_kb：物种+组织+方向强匹配排第一（kb_search 的 path_boost 排序
      已保证：物种 +25 / 组织 +15 / 方向 +10，同物种同组织同方向自然最前）；
      匹配条目 <2 时补搜其他物种，标注 [其他物种·参考]（如人衰老可参考
      小鼠衰老研究，但优先级靠后）
    - bioinfo_kb：话题匹配为主（DEG/CellChat/bulk 等方法类知识跨物种可参考）；
      同物种自然靠前，结果不足时放宽物种补搜，拓展思路
    - statistics_kb：不注入——统计判断由 LLM 自行推理（不需要外部知识库）
    """
    out = {"biology_kb": "", "bioinfo_kb": "", "statistics_kb": "", "sources": []}
    try:
        from memomics.bio_tools.kb_search import _search_kb
    except Exception:
        try:
            from kb_search import _search_kb
        except Exception:
            return out

    def _fmt(items, tag):
        parts, srcs = [], []
        for it in items:
            parts.append(f"[{tag}·{it.get('file', '')}]\n{it.get('snippet', '')[:max_chars]}")
            srcs.append(it.get("file", ""))
        return "\n\n".join(parts), srcs

    # ① biology：同物种/组织/方向优先（物种按目录名精确匹配，不受
    # tissue/direction 的 path_boost 干扰）
    try:
        r = _search_kb(topic, species=species, tissue=tissue, direction=direction)
        results = r.get("results", [])
        if species:
            try:
                from memomics.bio_tools.kb_search import _normalize_species as _ns
            except Exception:
                from kb_search import _normalize_species as _ns
            _svs = _ns(species)
            same = [x for x in results
                    if any(sv.lower() in x.get("file", "").lower() for sv in _svs)][:max_per_kb]
        else:
            same = results[:max_per_kb]
        others = []
        if len(same) < 2:
            try:
                r2 = _search_kb(topic, species="", tissue=tissue, direction=direction)
                seen = {s["file"] for s in same}
                others = [x for x in r2.get("results", []) if x["file"] not in seen][:max_per_kb - len(same)]
            except Exception:
                pass
        txt1, src1 = _fmt(same, "同物种·匹配")
        txt2, src2 = _fmt(others, "其他物种·参考")
        out["biology_kb"] = (txt1 + ("\n\n" + txt2 if txt2 else "")).strip()
        out["sources"] += src1 + src2
    except Exception as e:
        logger.warning(f"auto biology_kb injection failed: {e}")

    # ② bioinfo：话题匹配为主（方法类跨物种可参考）
    try:
        r = _search_kb(topic, species=species, tissue=tissue, direction=direction)
        top = r.get("results", [])[:max_per_kb]
        if len(top) < 2:
            try:
                r2 = _search_kb(topic, species="", tissue="", direction="")
                seen = {t["file"] for t in top}
                top += [x for x in r2.get("results", []) if x["file"] not in seen][:max_per_kb - len(top)]
            except Exception:
                pass
        txt, src = _fmt(top, "方法知识")
        out["bioinfo_kb"] = txt.strip()
        out["sources"] += src
    except Exception as e:
        logger.warning(f"auto bioinfo_kb injection failed: {e}")

    # ③ statistics：不注入（LLM 自行判断统计）
    return out


def debate_analysis(topic: str, context: str, knowledge_base_info: str = "",
                    history_errors: str = "", biology_kb: str = "",
                    statistics_kb: str = "", bioinfo_kb: str = "",
                    mode: str = None, rounds: int = None,
                    role_model_map: dict = None, level: str = "L2",
                    species: str = "", tissue: str = "", direction: str = "",
                    auto_kb: bool = True) -> str:
    """多角色辩论 — 正方3专业编辑 + 反方4专业编辑 + 裁判编辑，全部独立 LLM 调用。

    上下文隔离实现：
    - 每个编辑调用 _call_llm_sync()，传入只包含该编辑 prompt 的 messages
    - 正方编辑之间不知道彼此（各自独立调用）
    - 反方编辑之间不知道彼此（各自独立调用）
    - 正方不知道反方（各自独立调用）
    - 裁判是唯一看到所有角色的（裁判的 prompt 包含所有角色的输出）

    P0 参数化(2026-08-10):
    - mode: homogeneous(现状单模型) | adversarial(正反判三组异构) | multi_model(全角色异构) | temperature(同模型多温度采样)
    - rounds: 辩论轮数（>1 时第 2 轮起向 pro/con 注入上一轮裁判摘要）
    - role_model_map: {角色: {model, provider}} 最细粒度覆盖
    - 不传时全部从 config.yaml 的 debate: 段读取；无配置 = 现状行为

    C2(2026-08-11): level 门控级别
    - "L2"(默认): 完整 8 角色辩论（现状）
    - "L1": 轻量采样辩论 — 默认模型 N 次独立采样（温度梯度，上下文切断），
      裁判总结双方裁决。成本约为 L2 的一半，用于脚本设计/统计级结论。
    """
    # ========== 配置解析（参数优先，config 次之，默认=现状） ==========
    cfg = _load_debate_config()
    if mode is not None:
        cfg["mode"] = mode
    if rounds is not None:
        cfg["rounds"] = int(rounds) if str(rounds).isdigit() else 1
    if role_model_map is not None:
        cfg["role_model_map"] = role_model_map
    mode = str(cfg.get("mode", "homogeneous")).lower()
    rounds = max(1, int(cfg.get("rounds", 1) or 1))
    rmm = cfg.get("role_model_map") or {}
    level = str(level or "L2").upper()
    if level not in ("L1", "L2"):
        level = "L2"
    # 自动知识库注入（2026-08-13 用户三例设计）：biology 按物种/组织/方向
    # 强匹配优先（其他物种降权参考），bioinfo 按话题匹配（跨物种可参考），
    # statistics 不注入（LLM 自行判断）。显式传入的 kb 参数优先不覆盖。
    if auto_kb and not (biology_kb or bioinfo_kb):
        _inj = _auto_kb_injection(topic, context, species, tissue, direction)
        if not biology_kb and _inj.get("biology_kb"):
            biology_kb = _inj["biology_kb"]
        if not bioinfo_kb and _inj.get("bioinfo_kb"):
            bioinfo_kb = _inj["bioinfo_kb"]
    fingerprint = _debate_fingerprint(mode, rounds, rmm, cfg, level=level)

    # 检查至少有一个可用 key（judge 能跑即可；role_model_map/分组配置的 key 也算）
    judge_rc = _resolve_role_llm("judge", cfg)
    if not judge_rc["api_key"]:
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

    # ========== 查询历史辩论（优化2：持久化复用；P0：指纹隔离架构） ==========
    cached = _load_debate(topic, context, fingerprint=fingerprint)
    if cached:
        cached_result = cached.get("result", {})
        cached_result["reused_from_cache"] = True
        cached_result["cache_timestamp"] = cached.get("timestamp", "")
        cached_result["note"] = (
            "多角色辩论（v3）+ 并行调用 + 历史复用：本次辩论与历史记录的 topic+context+架构指纹完全匹配，"
            f"直接复用 {cached.get('timestamp', '')} 的辩论结果（72小时内有效）。"
            f"架构: mode={mode}, rounds={rounds}"
        )
        return json.dumps(cached_result, ensure_ascii=False, indent=2)

    # ========== 分科知识库（回退到通用 kb） ==========
    bio_kb = biology_kb or kb
    stat_kb = statistics_kb or kb
    bioinfo_kb_val = bioinfo_kb or kb

    # ========== C2(2026-08-11): L1 轻量采样辩论（默认模型上下文切断正反采样 + 裁判总结） ==========
    if level == "L1":
        return _debate_l1_lightweight(topic, context, kb, cfg, fingerprint)

    try:
        # ========== 辩论轮次循环（P0：rounds>1 时轮间注入上一轮裁判摘要） ==========
        prev_round_summary = ""
        final_judge = None
        for round_no in range(1, rounds + 1):
            round_note = ""
            if round_no > 1 and prev_round_summary:
                round_note = (
                    f"\n\n## 上一轮辩论摘要（第 {round_no - 1} 轮裁判结论，供本轮参考）\n"
                    f"{prev_round_summary}"
                )

            # ========== 正方 3 专业编辑（互相不知道，各用专属知识库） ==========
            pro_tasks = [
                ("pro_biology", PRO_BIO_PROMPT.format(topic=topic, context=context, kb_info=bio_kb) + round_note),
                ("pro_statistics", PRO_STAT_PROMPT.format(topic=topic, context=context, kb_info=stat_kb) + round_note),
                ("pro_bioinformatics", PRO_BIOINFO_PROMPT.format(topic=topic, context=context, kb_info=bioinfo_kb_val) + round_note),
            ]
            pro_results = _call_role_parallel(pro_tasks, cfg)
            pro_bio = pro_results["pro_biology"]
            pro_stat = pro_results["pro_statistics"]
            pro_bioinfo = pro_results["pro_bioinformatics"]

            # ========== 反方 4 专业编辑（互相不知道，也看不到正方，各用专属知识库） ==========
            con_tasks = [
                ("con_biology", CON_BIO_PROMPT.format(topic=topic, context=context, kb_info=bio_kb) + round_note),
                ("con_statistics", CON_STAT_PROMPT.format(topic=topic, context=context, kb_info=stat_kb) + round_note),
                ("con_bioinformatics", CON_BIOINFO_PROMPT.format(topic=topic, context=context, kb_info=bioinfo_kb_val) + round_note),
                ("con_history", CON_HISTORY_PROMPT.format(topic=topic, context=context, history_errors=hist) + round_note),
            ]
            con_results = _call_role_parallel(con_tasks, cfg)
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
            judge = _call_llm_role("judge", judge_prompt, cfg)
            final_judge = judge

            # 🔧 P0-1 修复(2026-08-01): 失败检测 — 8个角色任一失败则不缓存不归档
            # 之前: 401/超时失败占位符仍被 _save_debate 缓存72h → 相同topic+context再命中返回占位符
            _all_roles = [pro_bio, pro_stat, pro_bioinfo, con_bio, con_stat, con_bioinfo, con_history, judge]
            _failed_roles = [r.get("call_id", "?") for r in _all_roles if r.get("error") or "辩论生成失败" in str(r.get("content", ""))]
            if _failed_roles:
                logger.warning(f"debate FAILED {len(_failed_roles)}/8 roles: {_failed_roles[:3]}... 不缓存不归档")
                return json.dumps({
                    "topic": topic,
                    "debate_format": "多角色对抗（v3）",
                    "error": True,
                    "failed_roles": len(_failed_roles),
                    "failed_role_ids": _failed_roles,
                    "judge_verdict": judge.get("content", "") if not judge.get("error") else "裁判也失败",
                    "note": "辩论失败（8角色中有角色返回占位符）。未缓存未归档，Agent 应重试或检查 API key/base_url。",
                }, ensure_ascii=False, indent=2)

            # 轮间摘要（供下一轮 pro/con 参考；rounds=1 时不生效）
            prev_round_summary = (judge.get("content") or "")[:1500]

        judge = final_judge

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
                f"架构参数: mode={mode}, rounds={rounds}。\n"
                "辩论结果已归档到 results/.../log/debate_*.json（通过线程级 results_dir 自动定位）。"
            ),
            "debate_config": {
                "mode": mode,
                "rounds": rounds,
                "fingerprint": fingerprint,
                "role_models": {
                    label: _role_model_id(label, cfg) for label in ALL_ROLES
                },
                "note": "mode: homogeneous=单模型8角色 | adversarial=正反判三组异构 | multi_model=全角色异构 | temperature=同模型多温度。role_models 记录每个角色实际使用的 provider/model，供实验分析。",
            },
            "timing": {
                "parallel": True,
                "rounds": rounds,
                "round_description": "每轮: 正方3专业编辑并行 → 反方4专业编辑并行 → 裁判单独调用"
                                   + ("；轮间注入上一轮裁判摘要" if rounds > 1 else ""),
            },
            "knowledge_base": {
                "biology_kb_provided": bool(biology_kb),
                "statistics_kb_provided": bool(statistics_kb),
                "bioinfo_kb_provided": bool(bioinfo_kb),
                "general_kb_used_as_fallback": not (biology_kb or statistics_kb or bioinfo_kb),
            },
        }
        result_json = json.dumps(result, ensure_ascii=False, indent=2)
        # 🔧 P1-2 修复(2026-08-01): 解析 judge JSON → 结构化 verdict 供 Agent 直接使用
        # 之前: judge_verdict 是原始文本(含```json围栏)，verdict=modify 的 recommended_params 无法结构化回传
        # P0-3 增强(2026-08-10): 真实数据测试发现 deepseek-v4-flash 的 content 常为空，
        # fallback 的 reasoning_content 是思维链草稿，其中 JSON 片段可能残缺/含 "verdict": null。
        # 修复: 优先用正则找含非空 verdict 的 JSON 对象；全部失败才降级默认值。
        try:
            _judge_text = judge["content"]
            _judge_obj = _parse_judge_json(_judge_text)
            result["verdict"] = _judge_obj.get("verdict", "need_more_info") or "need_more_info"
            result["confidence"] = _judge_obj.get("confidence", "low") or "low"
            result["recommended_params"] = _judge_obj.get("recommended_params", {}) or {}
            result["scores"] = _judge_obj.get("scores", {}) or {}
        except Exception as _je:
            result["verdict"] = "need_more_info"
            result["confidence"] = "low"
            result["recommended_params"] = {}
            result["verdict_parse_error"] = str(_je)[:100]

        # ========== B2(2026-08-11): 裁决一致性门禁 ==========
        # 实证 bug：_debates/ 中 3 条 need_more_info+high 矛盾裁决已进入缓存。
        # 矛盾裁决 → judge 独立重裁一次（上下文切断）→ 仍矛盾则强制降级 low，
        # 且禁止回流 skill_evolution（垃圾不得入库）。
        _issues = _check_consistency(result)
        if _issues:
            logger.warning(f"debate verdict inconsistent {_issues}; judge 重裁一次")
            try:
                _judge2 = _call_llm_role("judge", judge_prompt, cfg)
                if not _judge2.get("error") and "辩论生成失败" not in str(_judge2.get("content", "")):
                    _obj2 = _parse_judge_json(_judge2["content"])
                    result["verdict"] = _obj2.get("verdict") or result["verdict"]
                    result["confidence"] = _obj2.get("confidence") or result["confidence"]
                    result["recommended_params"] = _obj2.get("recommended_params", {}) or {}
                    result["scores"] = _obj2.get("scores", {}) or {}
                    result["judge_rejudged"] = True
                    result["judge_verdict"] = _judge2["content"][:3000]
                    judge = _judge2
            except Exception as _re:
                logger.warning(f"judge re-judge failed: {_re}")
            _issues = _check_consistency(result)
        if _issues:
            result["confidence"] = "low"  # 仍矛盾 → 强制降级，禁止回流
            result["consistency_issues"] = _issues
            logger.warning(f"debate verdict still inconsistent after re-judge: {_issues} → confidence=low, 禁止回流")

        result_json = json.dumps(result, ensure_ascii=False, indent=2)
        # 持久化辩论结果（优化2：全局缓存用于去重；P0：指纹隔离）
        # 2026-08-14 修复：矛盾裁决不入缓存，否则下次命中直接返回 low 结果。
        if not result.get("consistency_issues"):
            _save_debate(topic, context, result_json, fingerprint=fingerprint)
        # 归档到结果目录（需求1b：强制保留到 results/.../log/）
        _archive_debate_to_results(topic, context, result_json)
        # P1(2026-08-10): 裁决回流 — verdict → skill_evolution.record_verdict（skill.json debate_verdicts + run_record 归档）
        _reflow_verdict(result)
        return result_json

    except Exception as e:
        logger.warning(f"Multi-role debate failed, using fallback: {e}")
        return _fallback_debate(topic, context, knowledge_base_info, history_errors)


def _auto_load_kb(context: str, topic: str) -> str:
    """当 KB 未传入时，从 context/topic 提取物种/组织/方向，自动加载知识库。"""
    import yaml
    text = (topic + " " + context).lower()
    
    species_map = {
        "Homo_sapiens": ["人", "human", "患者", "homo sapiens", "病人", "clinical"],
        "Macaca_mulatta": ["猕猴", "恒河猴", "猴", "macaque", "rhesus", "macaca", "monkey"],
        "Mus_musculus": ["小鼠", "mouse", "mus musculus", "c57", "balb"],
        "rattus_norvegicus": ["大鼠", "rat", "rattus"],
        "danio_rerio": ["斑马鱼", "zebrafish", "danio"],
    }
    tissue_map = {
        "liver": ["肝脏", "liver", "肝", "hepatocyte"],
        "skeletal_muscle": ["骨骼肌", "skeletal muscle", "肌肉", "myofiber"],
        "brain": ["脑", "brain", "neuron", "cortex", "hippocampus", "海马"],
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
        "disease": ["疾病", "disease", "癌症", "cancer", "肿瘤", "tumor", "ad", "alzheimer", "阿尔茨海默", "帕金森", "parkinson"],
    }
    
    sp = next((k for k, vs in species_map.items() if any(v in text for v in vs)), None)
    ts = next((k for k, vs in tissue_map.items() if any(v in text for v in vs)), None)
    dr = next((k for k, vs in direction_map.items() if any(v in text for v in vs)), "general")
    
    # 🔧 放宽双锁：物种/组织缺一时按已匹配维度搜索（2026-08-01）
    # 之前: if not sp or not ts: return ""  ← 双锁导致只提物种/只提组织都失败
    if not sp and not ts:
        return ""
    
    # 🔧 优先使用 search_knowledge v3/v4 引擎（2026-08-01）
    # FTS5 全文搜索 + 同义词扩展 + 词边界，比文件系统扫描更准
    try:
        from memomics.bio_tools.kb_search import _search_kb
        _kb_result = _search_kb(topic, sp or "", ts or "", dr if dr != "general" else "")
        if _kb_result.get("total", 0) > 0:
            _kb_hits = _kb_result.get("results", [])
            _parts = []
            for hit in _kb_hits[:6]:
                _fn = hit.get("file", "kb")
                _content = hit.get("snippet") or hit.get("content") or ""
                if _content:
                    _parts.append("## " + _fn + "\n" + str(_content)[:3000])
            if _parts:
                header = "[auto-loaded KB via search_knowledge] " + (sp or "?") + "/" + (ts or "?") + "/" + dr + "\n\n"
                return header + "\n\n".join(_parts)
    except Exception:
        pass  # 回退到文件扫描
    
    kb_root = os.path.join(
        os.path.dirname(__file__), "..", "..", "memomics", "knowledge_base"
    )
    # 🔧 放宽搜索路径：支持物种/组织部分匹配（2026-08-01）
    # 之前: kb_dir = os.path.join(kb_root, sp, ts, dr)  ← 必须全部匹配
    # 现在: 按已匹配维度逐级放宽，找到存在的目录
    candidate_dirs = []
    if sp and ts:
        candidate_dirs += [
            os.path.join(kb_root, sp, ts, dr),
            os.path.join(kb_root, sp, ts, "general"),
            os.path.join(kb_root, sp, ts),
        ]
    if sp:
        candidate_dirs.append(os.path.join(kb_root, sp))
    if ts:
        candidate_dirs.append(os.path.join(kb_root, ts))
    # 去重并保留存在的
    seen = set()
    kb_dir = ""
    for cd in candidate_dirs:
        if cd not in seen:
            seen.add(cd)
            if os.path.isdir(cd):
                kb_dir = cd
                break
    if not kb_dir:
        return ""
    
    parts = []
    # Collect with relevance score (keyword hits) + mtime tiebreak
    keywords = [kw for kws in (species_map.values(), tissue_map.values(), direction_map.values()) for kw in kws if kw in text]
    candidates = []
    for dirpath, dirnames, filenames in os.walk(kb_dir):
        for fn in filenames:
            if fn.endswith((".yaml", ".yml")) and fn != "index.yaml":
                fp = os.path.join(dirpath, fn)
                try:
                    with open(fp, "r", encoding="utf-8") as fh:
                        content = fh.read()
                    if len(content) > 100:
                        # 相关性 = 文件名命中 + 内容关键词命中数
                        score = sum(1 for kw in keywords if kw in fn.lower())
                        score += min(5, sum(1 for kw in keywords if kw in content.lower()))
                        mtime = os.path.getmtime(fp)
                        candidates.append((score, mtime, fn, content))
                except Exception:
                    pass
    # Sort by relevance score descending, then mtime descending
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    for score, mtime, fn, content in candidates[:8]:
        label = "## " + fn + "\n"
        parts.append(label + content[:3000])
    
    if not parts:
        return ""
    
    header = "[auto-loaded KB] " + (sp or "?") + "/" + (ts or "?") + "/" + dr + "\n\n"
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
                mode=args.get("mode"),
                rounds=args.get("rounds"),
                role_model_map=args.get("role_model_map"),
                level=args.get("level") or "L2",
                species=args.get("species", ""),
                tissue=args.get("tissue", ""),
                direction=args.get("direction", ""),
                auto_kb=args.get("auto_kb", True),
            ),
            emoji="🎭",
            max_result_size_chars=40_000,
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
            max_result_size_chars=40_000,
        )
    except ImportError:
        pass  # 不在 Hermes 环境中时不注册

_register()
