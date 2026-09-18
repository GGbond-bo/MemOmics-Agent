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
# 2026-09-13（用户要求）：辩论必须跟随「当前使用模型的提供商」。会话级模型配置由
# server.py 在 agent 回合入口注入（多会话各用各的模型），见 _current_model_route()。
_model_cfg_var = _contextvars.ContextVar("memomics_session_model_cfg", default=None)

def set_session_context(sid: str = "", results_dir: str = "", model_config: dict = None):
    """设置当前上下文（线程 + 其派生的工具 worker 线程）的会话上下文。

    由 server.py 在 agent 启动 / executor 线程入口调用。
    model_config: 该会话当前使用的模型配置 {provider, base_url, api_key, model}。
    辩论/文献库等独立 LLM 调用据此走「当前模型提供商」（2026-09-13 新增）。
    """
    _sid_var.set(sid or "")
    _results_dir_var.set(results_dir or "")
    _model_cfg_var.set(dict(model_config) if isinstance(model_config, dict) and model_config else None)

def get_session_sid() -> str:
    """获取当前会话 ID（ContextVar，跨工具 worker 线程传播）。"""
    return _sid_var.get()

def get_session_results_dir() -> str:
    """获取当前结果目录（ContextVar，跨工具 worker 线程传播）。"""
    return _results_dir_var.get()

def get_session_model_config() -> dict:
    """获取当前会话「正在使用的模型配置」（ContextVar，跨工具 worker 线程传播）。"""
    cfg = _model_cfg_var.get()
    return cfg if isinstance(cfg, dict) else {}

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
            },
            "evidence_cards": {
                "type": "string",
                "description": "证据卡（v2）：JSON 数组或 Markdown 文本，注入到所有角色与裁判 prompt。每卡含 id/type/title/pmid/doi/conclusion/effect/n/source_file。空=无外部证据卡。",
                "default": ""
            },
            "role_preset": {
                "type": "string",
                "enum": ["core7", "core9"],
                "description": "v2 角色预设：core7=现状 8 角色；core9=增加实验设计/可重复性中立评审（10 角色/轮，成本更高）。留空用 config。",
                "default": ""
            },
            "judge_count": {
                "type": "integer",
                "description": "v2 多裁判数量：1=单裁判（现状）；2-3=温度采样多裁判 + 简单多数投票（judge_consensus）。留空用 config。",
                "default": 0
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

# ==================== v2 证据审查器提示词（2026-08-27） ====================

_EVIDENCE_CONTRACT = """## 证据契约（必须遵守）
1. 每个观点必须有证据锚点：[PMID:xxx] / [DOI:xxx] / [KB源:文件] / [数据:具体数值]。
2. 无直接证据的推理必须标注 [仅是推理]，且不得作为论点计分。
3. 证据等级：P=文献/实验证据，C=证据卡/KB，I=纯推理。
4. 你的专业领域内若存在失败条件/已知反例，必须写入 self_audit_failures。
5. 若证据不足，明确写“本领域证据不足，不可下结论”，并列出 needed_evidence。"""

_V2_OUTPUT_SPEC = """## 输出格式（严格 JSON，不要输出任何其他文字）
{{"claims": [{{"claim": "…", "evidence": "[PMID:…] / [KB源:…] / [数据:…]", "level": "P|C|I", "confidence": "high|medium|low", "risk_boundary": "失效条件…"}}], "self_audit_failures": ["…"], "alternative_hypothesis": "若…则结论可能为…（可检验）", "needed_evidence": ["…"]}}"""

_V2_ROLE_QUESTIONS = {
    "pro_biology": {
        "title": "生物学专业编辑（正方）",
        "task": "从生物学角度支持以下决策/结论",
        "questions": """1. Marker gene 验证：相关标记基因的表达模式是否支持？
2. 已知生物学知识：与文献中已知的细胞类型/组织特征是否一致？
3. 生物学预期：结果是否符合该物种/组织/方向的生物学预期？
4. 证据等级标注：marker 特异性需给出双细胞类型对比数据或 PMID/DOI；无则 [I]。""",
    },
    "pro_statistics": {
        "title": "统计学专业编辑（正方）",
        "task": "从统计学角度支持以下决策/结论",
        "questions": """1. 显著性：p 值/FDR 是否达到阈值？效应量是否足够大？
2. 样本量：细胞数/样本数是否足够支持这个结论？（必须报告是否做过功效分析，没有则写在 self_audit_failures）
3. 分布特征：数据分布是否符合方法假设（附模型诊断证据）。
4. 多重比较校正方法明确说明。""",
    },
    "pro_bioinformatics": {
        "title": "生信专业编辑（正方）",
        "task": "从生信分析质量角度支持以下决策/结论",
        "questions": """1. QC 指标：nFeature/nCount/percent.mt 分布（给分位数，不只是均值）。
2. 聚类质量：轮廓系数、聚类稳定性、双胞率是否达标。
3. 分析流程：参数选择是否符合最佳实践？是否遗漏步骤？
4. 参数敏感性：说明结果对参数的变化区间（敏感/不敏感）。""",
    },
    "con_biology": {
        "title": "生物学专业编辑（反方）",
        "task": "从生物学角度质疑以下决策/结论",
        "questions": """1. 异质性：是否存在亚群被合并？是否有过度聚类？
2. 批次效应：生物学差异与技术差异是否混淆？
3. Marker 重叠：标记基因是否在多种细胞类型中表达？特异性是否足够？
4. 替代解释：必须给出【可检验的替代假设】（如“可能同源亚群，用 X 标记可区分”）。""",
    },
    "con_statistics": {
        "title": "统计学专业编辑（反方）",
        "task": "从统计学角度质疑以下决策/结论",
        "questions": """1. 多重比较：是否校正？假阳性率是否可控？
2. 统计功效：样本量是否足够？按当前样本量该效应量的功效是多少？（无法估计则写 self_audit_failures）
3. 模型假设：是否满足？是否有更合适方法？
4. 效应量：显著是否达到有生物学意义的大小？""",
    },
    "con_bioinformatics": {
        "title": "生信专业编辑（反方）",
        "task": "从生信分析质量角度质疑以下决策/结论",
        "questions": """1. 降维质量：PCA/UMAP 解释方差是否足够？是否过度降维？
2. 聚类稳定性：不同分辨率下是否稳定？bootstrap 稳定性如何？
3. 注释置信度：自动注释置信度得分？是否有手动验证？
4. 参数敏感性：换一组参数结果会变吗（给出敏感性陈述与证据或 [I]）。""",
    },
    "con_history": {
        "title": "历史经验编辑（反方）",
        "task": "从历史报错与经验记录角度质疑，并做证据匹配",
        "questions": """1. 检索相似历史报错（error_memory/errors.jsonl），给出〔相似度/适用性/置信度〕。
2. 已知陷阱：该参数/方法是否有已知的坑？
3. 环境限制：当前硬件/环境能否跑通？
4. 修复经验：之前是如何修复的？是否应采用修复后方案？""",
    },
    "design_review": {
        "title": "实验设计评审（中立）",
        "task": "检查实验设计/对照/批次/混杂，给出 confounding 风险清单",
        "questions": """1. design 公式与因子水平是否正确？（对照组/处理命名/交互项——设计错了结论全错）
2. 是否存在 donor/sample 混杂？是否建议 leave-one-out 或随机效应？
3. 样本与对照是否可比较（年龄/性别/批次/采集方案）？
4. 给出 confounding_risk 清单与最低限度的改进设计。""",
    },
    "reproducibility_review": {
        "title": "可重复性评审（中立）",
        "task": "检查随机种子/版本/环境/运行时长，输出可复现性评分与风险",
        "questions": """1. 随机种子/采样顺序是否固定？能否复现？
2. 工具链版本（R/Python/包）是否记录？是否需要 lock 文件？
3. 运行环境依赖（GPU/内存/路径）是否固化？
4. 给出 reproducibility_score(1-10) 与重跑建议。""",
    },
}

_V2_ROLE_TEMPLATE = """你是**{title}**。你的任务是从你的专业视角{task}。

## 辩论主题
{topic}
{scenario_line}
## 上下文
{context}

## {kb_title}
{kb_info}

{evidence_section}{contract}

{questions}

## 要求
- 严格按“输出格式”输出 JSON；每个 claim 必须带证据锚点与等级。
- 不编造证据；无证据写 [仅是推理] 并计入 needed_evidence。
- 控制在 500 字以内（结构化字段总长度）。
- 你不知道其他编辑的观点，请独立思考。
{output_spec}"""

_V2_JUDGE_PROMPT = """你是{persona}。{n_pro}位专业编辑（{roles}）进行了辩论，请按 rubrics 综合裁决。

## 辩论主题
{topic}

## 上下文
{context}

## 正方论证
{pro_arguments}

## 反方论证
{con_arguments}

{digest_section}{neutral_args}{evidence_section}{contract}

{focus_section}## 评分 rubrics（替代主观“说服力”）
{rubrics_hint}

## 裁决决策树（必须遵守）
1. 若正反双方证据均不足（大量 [I]/[仅是推理]）→ verdict=need_more_info, confidence=low, 必须列 missing。
2. 若 verdict=modify 但拿不出 recommended_params → 禁止输出该组合。
3. 若 confidence=high 但 missing 非空 → confidence 必须降为 medium。
4. 若双方论证接近 → 只能 need_more_info + missing，不得强行二选一。

## 输出格式（严格 JSON）
{{"rubrics": {{{rubric_keys}}}, "verdict": "support|modify|need_more_info", "confidence": "high|medium|low", "recommended_params": {{}}, "missing": ["必要证据/数据清单"], "reasoning": "≤500字，说明哪些论点挂在哪条证据上"}}"""

_RUBRICS_HINT = """- evidence_quality：论点是否锚定 PMID/DOI/数据
- effect_size：效应量大小与生物学意义
- confounding_control：批次/混杂/对照是否被考虑
- prior_literature：是否参考相关文献
- reproducibility：是否可复现
- pro/con_claim_coverage：正/反方是否覆盖完整（未覆盖给低分）"""


# ==================== 赛前场景预判（2026-09-18，用户提出） ====================
# 背景（用户原话）：「如果辩论的东西不是生物学相关的东西，而是排版，一些技术上的，
# 是不是需要采取其他的裁判呢？所以辩论之前，也要分析一下场景呢？」
# 问题：角色身份与裁判 rubric 长期硬编码生物学（marker gene / 批次效应 / 效应量 …）。
# 当辩题其实是「图版式怎么改」「脚本怎么修」「目录怎么组织」时，生物学 rubric 会问错问题，
# 裁判也会拿生信的标准打分 —— 结论看着专业，其实答非所问。
# 做法：正式辩论前先花 1 次短调用做**场景预判**，产出：
#   ① 主场景与判定依据 ② 裁判身份、必须逐条检查的要点 ③ 本场景的评分 rubric 键
#   ④ 各角色槽位的专业身份与提问清单（槽位数量不变 → 调用数/路由/归档结构不动）
# 预判失败或解析失败一律回退到原有生物学模板，绝不阻断辩论。

_SCENARIO_LABELS = {
    "bio_data": "生物学数据与结论",
    "stats_design": "统计与实验设计",
    "figure_layout": "图表版式与视觉呈现",
    "code_engineering": "代码与工程实现",
    "writing": "文档写作与表达",
    "ops_environment": "运维环境与资源",
    "general": "通用综合判断",
}

_SCENARIO_PROMPT = """你在为一场多角色辩论做**赛前场景预判**。辩论题目如下，请先判断它到底属于哪一类问题，再据此设计本次辩论的角色与裁判标准。

## 辩论主题
{topic}

## 上下文
{context}

## 判断要求
1. 先看主题真正在争论什么：是**生物学/实验结论**、**统计与实验设计**、**图表版式与视觉呈现**、
   **代码与工程实现**、**文档写作**，还是**运维环境/资源**问题。可以复合，但必须给出一个主场景。
2. 角色槽位固定：正方 3 席、反方 4 席（反方第 4 席专门负责「历史经验/踩过的坑」）。
   你要为每个槽位起一个**符合本场景**的专业身份，并写出该身份必须追问的问题清单。
   生物学辩题就用生物学/统计/生信身份；版式辩题应该是信息设计/期刊规范/可读性与色觉可达性
   这类身份；代码辩题应该是软件工程/性能/测试与可维护性这类身份。**不许所有场景都套生物学**。
3. 裁判 rubric：给出 5-7 个**本场景真正该看**的评分维度（英文 key + 中文名 + 打分说明）。
   生物学场景可用 evidence_quality/effect_size/confounding_control；
   版式场景应换成期刊规范符合度/信息层级/色觉与灰度可达性/最小改动成本 这类维度。
4. 证据：说明本场景里「什么算证据」。生物学场景的证据是 PMID/DOI/实验数据；版式场景的证据是
   期刊投稿规范原文、目标期刊已发表图样例、灰度和色盲模拟结果、实际渲染尺寸；代码场景的证据是
   实测耗时/报错日志/版本 diff/测试结果。**不要照抄生物学证据标准**。
5. 不确定就选 general，并在 why 里说明为何无法归类。

## 输出格式（严格 JSON，不要输出任何其他文字）
{{"scenario": "bio_data|stats_design|figure_layout|code_engineering|writing|ops_environment|general",
  "scenario_label": "中文场景名（≤12字）",
  "why": "一句话判定依据（≤60字）",
  "judge_persona": "本场裁判身份一句话（例：期刊图版式与技术审稿编辑）",
  "judge_focus": ["裁判必须逐条检查的要点（4-6 条）", "…"],
  "rubric_keys": ["英文键名（5-7 个）", "…"],
  "rubrics": [{{"key": "英文键名", "label": "中文名", "hint": "怎么打分"}}],
  "evidence_types": ["本场景里什么算证据", "…"],
  "pro_roles": [{{"title": "正方第1席身份（例：信息设计编辑（正方））", "task": "从…角度支持", "questions": ["该席必须回答的问题", "…"]}}, {{"title": "…", "task": "…", "questions": ["…"]}}, {{"title": "…", "task": "…", "questions": ["…"]}}],
  "con_roles": [{{"title": "反方第1席身份", "task": "从…角度质疑", "questions": ["…"]}}, {{"title": "…", "task": "…", "questions": ["…"]}}, {{"title": "…", "task": "…", "questions": ["…"]}}, {{"title": "反方第4席的具体身份（负责历史经验/踩过的坑，不要照抄这句话）", "task": "从历史记录角度质疑", "questions": ["…"]}}]}}"""

# 角色槽位 → 场景预判里的位置。槽位 label 保持原样（调用路由/归档键/UI 全都不变），
# 只替换「展示身份 + 任务 + 提问清单」。
_SCENARIO_ROLE_SLOTS = {
    "pro_biology": ("pro_roles", 0),
    "pro_statistics": ("pro_roles", 1),
    "pro_bioinformatics": ("pro_roles", 2),
    "con_biology": ("con_roles", 0),
    "con_statistics": ("con_roles", 1),
    "con_bioinformatics": ("con_roles", 2),
    "con_history": ("con_roles", 3),
}

_SCENARIO_DEFAULT_RUBRIC_KEYS = ['"evidence_quality": 1-10', '"effect_size": 1-10',
                                 '"confounding_control": 1-10', '"prior_literature": 1-10',
                                 '"reproducibility": 1-10', '"pro_claim_coverage": 1-10',
                                 '"con_claim_coverage": 1-10']


# ==================== 裁判整理阶段（2026-09-18） ====================
# 背景（用户实测反馈）：大量角色模型不遵守 JSON 契约，只留下 "[reasoning草稿…]" 式的
# 思维链草稿 → 裁判直接读草稿，裁决理由又长又乱、论点挂不上锚点、"找不到证据"也看不出来。
# 做法：正式裁决之前先让裁判模型做一次**整理**（不重新辩论、不发明论据）：
#   ① 把每个角色的草稿/JSON 压缩成 1-3 条清晰陈述；
#   ② 论据只允许引用原文出现过的锚点，没证据就老实写「找不到论据」；
#   ③ 草稿角色显式标注、正反冲突摆明、证据缺口单独列。
# 整理稿同时用于两处：喂给最终裁决（裁判读整理稿）+ 存进归档供 WebUI 展示。

_DIGEST_ROLE_CHARS = 3500   # 每个角色进入整理 prompt 的原文上限（控输入规模，防上下文超限）

_JUDGE_DIGEST_PROMPT = """你是这场多角色辩论的**首席整理编辑**。你现在的任务不是重新辩论、也不是下结论，而是把各角色的发言**整理成干净、可核查的清单**，交给最终裁判直接使用。

## 辩论主题
{topic}

## 上下文
{context}

{evidence_section}## 各角色原始发言（已按角色切分；标注「草稿」的是没按 JSON 契约输出、只留下推理过程的角色）
{raw}

{note}## 整理要求（逐条遵守，违反即作废）
1. **只整理，不发明**：只能使用上面原文出现过的内容。你自己知道、但原文里没有写的文献、数据、基因名，一律不得写进来。
2. **说人话**：把每个角色的草稿/JSON/长篇推理压缩成 1-3 条清晰陈述；删掉过程性自言自语（如「我们是从正方角度」「需从三个角度论证」「先想一下」）。
3. **论据必须落在锚点上**：每条陈述的 evidence 只填原文出现过的 [PMID:…] / [DOI:…] / [KB源:…] / [数据:…] / [仅是推理]。
4. **找不到就老实承认**：原文没有任何外部证据支撑的陈述，evidence 写 "[找不到论据]"，evidence_status 写 "无外部证据"。不要为了让清单好看而补证据——裁判要靠这个判断该不该下结论。
5. **草稿必须标出来**：草稿角色的观点照实整理，但 draft_flag 写 true，note 里写明「该角色未按契约输出，本节取自推理草稿」。
6. **正反冲突要摆明**：双方对同一问题给出相反判断 → 写成一条 conflicts；谁的证据更硬写谁，都没证据就写 "双方都没有证据"。
7. **按角色成组**：每条陈述都要写清 source_role（用上面发言块标题里的角色名/角色键）。同一个角色的同类陈述合并成一条，不同角色的论点不要混进同一条——展示时会按「正方·生物学编辑 1/2/3…、正方·统计学编辑 1/2/3…、反方·生物学编辑 1/2/3…」分组，漏掉某个角色等于判它没说话。

## 输出格式（严格 JSON，不要输出任何其他文字，不要用代码块包裹）
{{"pro_points": [{{"claim": "一句清晰的陈述", "evidence": "[PMID:…] / [数据:…]", "evidence_status": "有外部证据|仅推理|无外部证据", "source_role": "pro_biology", "draft_flag": false, "note": ""}}], "con_points": [{{"claim": "…", "evidence": "…", "evidence_status": "…", "source_role": "con_biology", "draft_flag": false, "note": ""}}], "agreements": ["双方都认同的点"], "conflicts": [{{"issue": "争议点", "pro": "正方主张", "con": "反方主张", "who_has_evidence": "正方|反方|双方都有|双方都没有证据", "judgement": "一句话说明为什么"}}], "evidence_gaps": [{{"claim": "需要证据支撑的结论", "missing": "缺什么证据/数据", "source_role": "谁提的"}}], "draft_roles": ["未按契约输出、只给了草稿的角色"], "summary": "≤200字：这场辩论真正吵清楚的是什么，卡在什么地方"}}"""


# 2026-09-18 实跑教训：实测 opencode-go/deepseek-v4-pro 在整理步骤里也**只回了推理过程**
# （content 为空 → _call_llm_sync 用 reasoning_content 兜底，前缀 "[reasoning草稿…]"），
# 白白浪费一次调用、整理稿为空。修法：把模型自己刚才那段输出原样塞回去，只要求它做「格式化」
# 这一件事——分析已经做完，第二次通常就能把 JSON 吐出来（不再需要重新推理）。
_JUDGE_DIGEST_REPAIR_PROMPT = """你上一步已经把辩论整理分析做完了，但没有按要求输出结果——你的回复只有推理过程，没有 JSON。

现在只做一件事：**把你自己上面的分析结论，原样格式化成 JSON**。不要重新分析、不要写解释、不要写思考过程、不要用代码块。

## 你上一步的输出（可能被截断）
{prev}

## 输出要求（第一个字符必须是 {{ ，最后一个字符必须是 }} ）
1. 只允许使用原始发言里出现过的内容与锚点；没有证据的陈述 evidence 写 "[找不到论据]"，evidence_status 写 "无外部证据"。
2. 结构必须是这个 JSON：
{{"pro_points": [{{"claim": "一句清晰的陈述", "evidence": "[PMID:…] / [数据:…] / [找不到论据]", "evidence_status": "有外部证据|仅推理|无外部证据", "source_role": "pro_biology", "draft_flag": false, "note": ""}}], "con_points": [{{"claim": "…", "evidence": "…", "evidence_status": "…", "source_role": "con_biology", "draft_flag": false, "note": ""}}], "agreements": ["双方都认同的点"], "conflicts": [{{"issue": "争议点", "pro": "正方主张", "con": "反方主张", "who_has_evidence": "正方|反方|双方都有|双方都没有证据", "judgement": "一句话说明为什么"}}], "evidence_gaps": [{{"claim": "需要证据支撑的结论", "missing": "缺什么证据/数据", "source_role": "谁提的"}}], "draft_roles": ["未按契约输出、只给了草稿的角色"], "summary": "≤200字：这场辩论真正吵清楚的是什么，卡在什么地方"}}
3. 每条陈述都要带 source_role（角色名/角色键），同一角色的同类陈述合并成一条，不同角色不要混在一条里。
4. 如果你上一步的输出里确实没有任何可整理的内容，就输出 {{"pro_points": [], "con_points": [], "agreements": [], "conflicts": [], "evidence_gaps": [], "draft_roles": [], "summary": "整理失败：原文没有可用内容"}}。
5. 直接输出 JSON 本身，前后不要有任何字符。"""


def _digest_parse(txt: str):
    """从模型输出里挖出整理 JSON；挖不到返回 None（不抛异常）。"""
    if not txt or not str(txt).strip():
        return None
    clean = str(txt).replace("\u0060\u0060\u0060json", "").replace("\u0060\u0060\u0060", "").strip()
    for cand in _extract_json_candidates(clean):
        try:
            _o = json.loads(cand)
        except Exception:
            continue
        if isinstance(_o, dict) and ("pro_points" in _o or "con_points" in _o or "conflicts" in _o
                                     or "evidence_gaps" in _o or "summary" in _o):
            # 空壳（模型认输）也算解析成功，但上层会当成「没有可用内容」
            return _o
    return None



def _digest_block(label: str, content: str, draft=None) -> str:
    """整理 prompt 里的单个角色区块。draft=None 时按 [reasoning草稿 前缀自动判定。"""
    txt = str(content or "").strip()
    if draft is None:
        draft = txt.startswith("[reasoning草稿")
    head = f"### {label}"
    if draft:
        head += "　⚠️ 未按契约输出（草稿：只有推理过程，不是已核实的论点）"
    if len(txt) > _DIGEST_ROLE_CHARS:
        txt = txt[:_DIGEST_ROLE_CHARS] + "…（原文过长已截断）"
    return head + "\n" + txt


def _digest_section_text(dg) -> str:
    """把整理结果拼成喂给裁判的区块；整理失败/未启用返回空串（裁决照旧走原文）。"""
    if not isinstance(dg, dict):
        return ""
    obj = dg.get("digest")
    if isinstance(obj, dict) and obj:
        return ("## 整理稿（首席整理编辑已把各方草稿整理成清单；evidence 为 [找不到论据] = 原文没有外部证据，不得当作已证实的论点）\n"
                + json.dumps(obj, ensure_ascii=False, indent=1)[:9000] + "\n\n")
    if dg.get("error"):
        return ("## 整理稿\n（首席整理编辑这一步失败了：" + str(dg.get("error"))[:140]
                + "。请直接按原始发言判断，并注意：很多角色只给了草稿，草稿里的具体文献/数值未必可靠。）\n\n")
    return ""


def _judge_digest(topic: str, context: str, role_blocks, evidence_cards: str = "", cfg: dict = None,
                  extra_note: str = "") -> dict:
    """裁判整理阶段：把草稿/非契约输出整理成「清晰言论 + 论据清单」。

    返回 {"digest": {...}|None, "raw": ..., "model": ..., "call_id": ..., "error": ...}。
    这是增强步骤：任何失败都不抛异常、不阻断辩论，裁决退回原始 prompt 路径。
    """
    out = {"digest": None, "raw": "", "model": "", "call_id": "",
           "error": "", "skipped": "", "repaired": False, "note": "", "attempts": 0}
    try:
        if str(os.environ.get("MEMOMICS_DEBATE_NO_DIGEST", "")).strip() == "1":
            out["skipped"] = "env:MEMOMICS_DEBATE_NO_DIGEST=1"
            return out
        _flag = (cfg or {}).get("judge_digest", True)
        if str(_flag).strip().lower() in ("0", "false", "no", "off") or _flag is False:
            out["skipped"] = "config:judge_digest=false"
            return out
        blocks = [b for b in (role_blocks or []) if str(b or "").strip()]
        if not blocks:
            out["skipped"] = "no_arguments"
            return out
        prompt = _JUDGE_DIGEST_PROMPT.format(
            topic=topic, context=context,
            evidence_section=_evidence_block(evidence_cards),
            raw="\n\n".join(blocks), note=extra_note or "")
        r = _call_llm_role_resilient("judge", prompt, cfg or {}, temperature=0.2)
        _want = _role_model_id("judge", cfg or {})
        # 2026-09-18: 主路由失败时如实记录「真正产出整理稿的路由」，否则归档会把回退模型的
        # 产物记成主路由模型（实验记录必须能看出真实使用的模型）。
        _route_note = ""
        if r.get("fallback_used"):
            out["model"] = str(r.get("fallback_route") or _want)
            _route_note = f"裁判主路由 {_want} 调用失败，整理稿由回退路由 {out['model']} 产出"
        else:
            out["model"] = _want
        out["call_id"] = str(r.get("call_id") or "")
        if r.get("error"):
            out["error"] = str(r.get("error_detail") or r.get("error"))[:300]
            return out
        txt = str(r.get("content") or "")
        if not txt.strip():
            out["error"] = "整理输出为空（模型没给 content）"
            return out
        out["raw"] = txt[:6000]
        out["attempts"] = 1
        _draft = txt.lstrip().startswith("[reasoning草稿")
        obj = _digest_parse(txt)
        if obj is None:
            # 修复轮（2026-09-18 实跑教训）：很多推理模型在整理步骤里也把内容全塞进 reasoning，
            # content 只剩草稿 → 再叫它一次，只把上一步的分析格式化成 JSON（成本 1 次调用，
            # 有 _JUDGE_ROUTE_BAD 备忘，不会对着已挂的主路由重复付超时）。
            _fix = _JUDGE_DIGEST_REPAIR_PROMPT.format(prev=txt[:7000])
            r2 = _call_llm_role_resilient("judge", _fix, cfg or {}, temperature=0.1)
            out["attempts"] = 2
            txt2 = str(r2.get("content") or "")
            if txt2.strip():
                out["raw_first"] = txt[:6000]
                out["raw"] = txt2[:6000]
                out["call_id"] = str(r2.get("call_id") or out.get("call_id") or "")
                obj = _digest_parse(txt2)
                if obj is not None:
                    out["repaired"] = True
                    out["note"] = ("整理模型第一次只给了推理草稿，第二次（仅格式化）才输出 JSON"
                                   if _draft else "整理模型第一次输出无法解析，重试一次后成功")
            if obj is None:
                out["error"] = ("整理模型两次都没有给出 JSON"
                                + ("（两次都只有推理草稿）" if _draft else "（输出无法解析）")
                                + "，已按原文裁决" + (f"；{_route_note}" if _route_note else ""))
                return out
        if not any(obj.get(_k) for _k in ("pro_points", "con_points", "conflicts", "evidence_gaps", "summary")):
            out["error"] = ("整理模型给了 JSON 但内容为空（没有可整理的论点）"
                            + (f"；{_route_note}" if _route_note else ""))
            return out
        out["digest"] = obj
        if _route_note:
            out["note"] = _route_note + ("；" + out["note"] if out.get("note") else "")
        return out
    except Exception as e:
        out["error"] = str(e)[:200]
        return out


def _digest_fields(dg) -> dict:
    """整理结果 → 归档字段（只写有值的键，避免空字段噪声；整理失败也留痕便于排查）。"""
    out = {}
    if not isinstance(dg, dict):
        return out
    for _k, _v in (("judge_digest", dg.get("digest")), ("judge_digest_raw", dg.get("raw")),
                   ("judge_digest_model", dg.get("model")), ("judge_digest_call_id", dg.get("call_id")),
                   ("judge_digest_error", dg.get("error")), ("judge_digest_skipped", dg.get("skipped")),
                   ("judge_digest_repaired", dg.get("repaired")), ("judge_digest_note", dg.get("note"))):
        if _v:
            out[_k] = _v
    return out


def _attach_digest(result: dict, dg) -> None:
    """把整理结果写进结果 dict（L1 路径用；v3 路径用 **_digest_fields）。"""
    if isinstance(result, dict):
        result.update(_digest_fields(dg))


def _scenario_parse(txt: str):
    """从模型输出里解析场景预判 JSON；失败返回 None（不抛异常）。"""
    if not txt:
        return None
    clean = str(txt).replace("```json", "").replace("```", "").strip()
    for cand in [clean] + _extract_json_candidates(clean):
        try:
            o = json.loads(cand)
        except Exception:
            continue
        if isinstance(o, dict) and (o.get("scenario") or o.get("judge_persona") or o.get("rubrics")):
            return o
    return None


def _scenario_norm(obj):
    """规范化场景预判：补默认值、裁长度、限 rubric 数量；缺关键字段返回 None。"""
    if not isinstance(obj, dict):
        return None
    _sc = str(obj.get("scenario") or "general").strip().lower()
    if _sc not in _SCENARIO_LABELS:
        _sc = "general"
    out = {
        "scenario": _sc,
        "scenario_label": str(obj.get("scenario_label") or _SCENARIO_LABELS[_sc]).strip()[:24],
        "why": str(obj.get("why") or "").strip()[:200],
        "judge_persona": str(obj.get("judge_persona") or "").strip()[:140],
        "judge_focus": [str(x).strip()[:220] for x in (obj.get("judge_focus") or []) if str(x).strip()][:6],
        "evidence_types": [str(x).strip()[:180] for x in (obj.get("evidence_types") or []) if str(x).strip()][:6],
        "rubrics": [], "rubric_keys": [], "pro_roles": [], "con_roles": [],
    }
    _rs = []
    for r in (obj.get("rubrics") or []):
        if isinstance(r, dict) and r.get("key"):
            _k = re.sub(r"[^0-9a-zA-Z_]", "", str(r["key"]))[:40]
            if _k:
                _rs.append({"key": _k, "label": str(r.get("label") or _k)[:40],
                            "hint": str(r.get("hint") or "")[:180]})
    _rs = _rs[:7]
    if _rs:
        out["rubrics"] = _rs
        out["rubric_keys"] = [r["key"] for r in _rs]
    else:
        _ks = [re.sub(r"[^0-9a-zA-Z_]", "", str(k))[:40] for k in (obj.get("rubric_keys") or [])]
        out["rubric_keys"] = [k for k in _ks if k][:7]
        out["rubrics"] = [{"key": k, "label": k, "hint": ""} for k in out["rubric_keys"]]

    def _roles(key, want):
        got = []
        for r in (obj.get(key) or []):
            if isinstance(r, dict) and (r.get("title") or r.get("task")):
                got.append({"title": str(r.get("title") or "").strip()[:70],
                            "task": str(r.get("task") or "").strip()[:200],
                            "questions": [str(q).strip()[:240] for q in (r.get("questions") or [])
                                          if str(q).strip()][:6]})
        return got[:want]

    out["pro_roles"] = _roles("pro_roles", 3)
    out["con_roles"] = _roles("con_roles", 4)
    if not out["judge_persona"] and not out["rubrics"] and not out["pro_roles"] and not out["con_roles"]:
        return None
    return out


def _analyze_scenario(topic: str, context: str, cfg: dict = None) -> dict:
    """赛前场景预判（1 次调用，走 judge 路由 + 回退链）。

    返回 {"scenario": {...}|None, "model": ..., "call_id": ..., "error": ...}。
    任何失败都不抛异常：调用方拿到 scenario=None 就用原有生物学模板继续。
    """
    cfg = cfg or {}
    out = {"scenario": None, "model": "", "call_id": "", "error": "", "raw": ""}
    try:
        if str(os.environ.get("MEMOMICS_DEBATE_NO_SCENARIO", "")).strip() == "1":
            out["error"] = "skipped:env"
            return out
        _flag = cfg.get("scenario_analysis", True)
        if _flag is False or str(_flag).strip().lower() in ("0", "false", "no", "off"):
            out["error"] = "skipped:config"
            return out
        prompt = _SCENARIO_PROMPT.format(topic=topic, context=context)
        r = _call_llm_role_resilient("judge", prompt, cfg, temperature=0.2)
        out["model"] = (str(r.get("fallback_route") or _role_model_id("judge", cfg))
                        if r.get("fallback_used") else _role_model_id("judge", cfg))
        out["call_id"] = str(r.get("call_id") or "")
        if r.get("error"):
            out["error"] = "场景预判调用失败：" + str(r.get("error_detail") or r.get("error"))[:200]
            return out
        txt = str(r.get("content") or "")
        if not txt.strip():
            out["error"] = "场景预判输出为空（模型没给 content）"
            return out
        out["raw"] = txt[:1200]
        obj = _scenario_parse(txt)
        if obj is None:
            out["error"] = "场景预判输出无法解析为 JSON（已按生物学默认标准继续）"
            return out
        norm = _scenario_norm(obj)
        if norm is None:
            out["error"] = "场景预判 JSON 缺关键字段（已按生物学默认标准继续）"
            return out
        norm["model"] = out["model"]
        norm["call_id"] = out["call_id"]
        out["scenario"] = norm
        return out
    except Exception as e:
        out["error"] = "场景预判异常：" + str(e)[:200]
        return out


def _scenario_fields(res) -> dict:
    """场景预判结果 → 归档字段（成功写 scenario；失败写 scenario_error 留痕，便于排查）。"""
    if not isinstance(res, dict):
        return {}
    sc = res.get("scenario")
    if isinstance(sc, dict):
        return {"scenario": sc, "scenario_model": res.get("model", ""),
                "scenario_call_id": res.get("call_id", "")}
    d = {}
    if res.get("error"):
        d["scenario_error"] = str(res.get("error"))[:300]
    if res.get("model"):
        d["scenario_model"] = res["model"]
    if res.get("raw"):
        d["scenario_raw"] = str(res["raw"])[:1200]
    return d


def _scenario_role_spec(scenario, label: str):
    """取场景预判为某个角色槽位设计的身份；没有则 None（回退生物学默认）。"""
    if not isinstance(scenario, dict):
        return None
    slot = _SCENARIO_ROLE_SLOTS.get(label)
    if not slot:
        return None
    key, i = slot
    arr = scenario.get(key) or []
    if isinstance(arr, list) and len(arr) > i and isinstance(arr[i], dict):
        r = arr[i]
        if r.get("title") or r.get("task") or r.get("questions"):
            return r
    return None


def _scenario_line(scenario) -> str:
    """角色 prompt 里的场景段（没有预判就返回空串）。"""
    if not isinstance(scenario, dict):
        return ""
    _lab = scenario.get("scenario_label") or _SCENARIO_LABELS.get(scenario.get("scenario", ""), "")
    if not _lab:
        return ""
    _t = f"\n## 本场场景（赛前预判）\n场景：{_lab}"
    if scenario.get("why"):
        _t += f"（判定依据：{scenario['why']}）"
    _t += ("\n你的身份与提问清单已按该场景设定；某条问题在本场景确实不适用时可以跳过，"
           "但要在 self_audit_failures 里写明原因。")
    if scenario.get("evidence_types"):
        _t += "\n本场景的证据标准：" + "；".join(scenario["evidence_types"][:4]) + "。"
    return _t + "\n"


def _role_title(label: str, scenario=None) -> str:
    """角色展示名（中文）：场景预判给了本场身份就用它，否则用原 biology 默认名。"""
    _sc = _scenario_role_spec(scenario, label)
    if _sc and _sc.get("title"):
        return _sc["title"]
    return (_V2_ROLE_QUESTIONS.get(label) or {}).get("title") or label


def _evidence_block(evidence_cards: str = "") -> str:
    """把证据卡文本拼进 prompt；为空返回 '（未提供证据卡）'。"""
    ev = _format_evidence_cards(evidence_cards)
    if not ev:
        return "## 证据卡\n（未提供证据卡；所有无锚点推理都只能标记 [仅是推理]）\n\n"
    return f"## 证据卡（可引用，引用时用 id/PMID/DOI）\n{ev}\n\n"


def _v2_role_prompt(label: str, topic: str, context: str, kb_info: str,
                    history_errors: str = "", evidence_cards: str = "", scenario=None) -> str:
    """角色 prompt。scenario=赛前场景预判结果时，用本场该槽位的身份/任务/提问替换生物学默认。"""
    spec = _V2_ROLE_QUESTIONS.get(label, _V2_ROLE_QUESTIONS["pro_biology"])
    title, task, questions = spec["title"], spec["task"], spec["questions"]
    _sc_role = _scenario_role_spec(scenario, label)
    if _sc_role:
        title = _sc_role.get("title") or title
        task = _sc_role.get("task") or task
        _qs = _sc_role.get("questions") or []
        if _qs:
            questions = "\n".join(f"{i+1}. {q}" for i, q in enumerate(_qs))
    kb_title = "历史报错记录" if label == "con_history" else "知识库参考"
    kb = history_errors if label == "con_history" else (kb_info or "无知识库参考")
    return _V2_ROLE_TEMPLATE.format(
        title=title, task=task, topic=topic, context=context,
        scenario_line=_scenario_line(scenario),
        kb_title=kb_title, kb_info=kb,
        evidence_section=_evidence_block(evidence_cards),
        contract=_EVIDENCE_CONTRACT + "\n\n", questions=questions,
        output_spec=_V2_OUTPUT_SPEC)


def _v2_judge_prompt(topic: str, context: str, pro_arguments: str, con_arguments: str,
                     evidence_cards: str = "", neutral_args: str = "",
                     roles: str = "3 正方 + 4 反方", digest: str = "", scenario=None) -> str:
    """裁判 prompt。scenario=赛前场景预判结果时，裁判身份/检查要点/评分维度全部按本场场景走
    （排版题就不再拿生信的 effect_size/confounding 去打分）。"""
    _sc = scenario if isinstance(scenario, dict) else None
    persona = "生信分析多角色辩论的**裁判编辑**（v2）"
    focus_section = ""
    rubrics_hint = _RUBRICS_HINT
    rubric_keys = ", ".join(_SCENARIO_DEFAULT_RUBRIC_KEYS)
    if _sc:
        if _sc.get("judge_persona"):
            persona = f"{_sc['judge_persona']}，本场多角色辩论的**裁判编辑**（v2）"
        _bits = []
        if _sc.get("scenario_label"):
            _bits.append(f"- 本场场景：{_sc['scenario_label']}"
                         + (f"（判定依据：{_sc['why']}）" if _sc.get("why") else ""))
        for _f in (_sc.get("judge_focus") or [])[:6]:
            _bits.append(f"- {_f}")
        if _sc.get("evidence_types"):
            _bits.append("- 本场景的证据标准：" + "；".join(_sc["evidence_types"][:5])
                         + "（不符合这些标准的论据一律按“无证据”处理）")
        if _bits:
            focus_section = "## 本场裁判必须逐条检查（赛前场景预判）\n" + "\n".join(_bits) + "\n\n"
        if _sc.get("rubrics"):
            rubrics_hint = "\n".join(
                f"- {r['key']}：{r.get('label') or ''}"
                + (f"——{r['hint']}" if r.get("hint") else "") for r in _sc["rubrics"])
            rubric_keys = ", ".join(f'"{r["key"]}": 1-10' for r in _sc["rubrics"])
    return _V2_JUDGE_PROMPT.format(
        persona=persona,
        n_pro="7位" if not neutral_args else "9位",
        roles=roles,
        topic=topic, context=context,
        pro_arguments=pro_arguments, con_arguments=con_arguments,
        digest_section=digest or "",
        neutral_args=neutral_args or "",
        evidence_section=_evidence_block(evidence_cards),
        contract=_EVIDENCE_CONTRACT + "\n\n",
        focus_section=focus_section,
        rubrics_hint=rubrics_hint,
        rubric_keys=rubric_keys)


def _use_v2_prompts(cfg: dict) -> bool:
    """v2 提示词开关：prompt_version>=2 且未强制 legacy。"""
    if str(os.environ.get("MEMOMICS_DEBATE_LEGACY_PROMPTS", "")).strip() == "1":
        return False
    try:
        return int((cfg or {}).get("prompt_version", 2) or 2) >= 2
    except Exception:
        return False


def _format_evidence_cards(evidence_cards: str) -> str:
    """把 evidence_cards（JSON 数组或文本）格式化为可注入的证据卡文本。"""
    ev = (evidence_cards or "").strip()
    if not ev:
        return ""
    try:
        obj = json.loads(ev)
        items = obj if isinstance(obj, list) else ([obj] if isinstance(obj, dict) else [])
        lines = []
        for i, c in enumerate(items, 1):
            if not isinstance(c, dict):
                continue
            cid = c.get("id") or f"ev{i}"
            pmid = c.get("pmid") or c.get("doi") or ""
            title = c.get("title") or c.get("conclusion") or "证据"
            eff = c.get("effect", "?")
            n = c.get("n", "?")
            src = c.get("source_file", "?")
            conflict = c.get("conflict_with") or ""
            lines.append(f"- [{cid}] {title} | PMID/DOI: {pmid} | 效应: {eff} | n={n} | 来源: {src}"
                         + (f" | 冲突: {conflict}" if conflict else ""))
        return "\n".join(lines) if lines else ev
    except Exception:
        return ev


def _evidence_fingerprint(evidence_cards: str) -> str:
    """证据卡指纹：内容变化 → 新缓存条目（防止不同证据复用同一辩论）。"""
    if not (evidence_cards or "").strip():
        return ""
    try:
        obj = json.loads(evidence_cards)
        text = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except Exception:
        text = str(evidence_cards)
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:10]


def _collect_judge_consensus(judge_prompt: str, cfg: dict) -> tuple:
    """v2: 多裁判采样 — 返回 (primary_judge_result, consensus_dict)。

    count=1 时即现状单裁判。count>1 用温度梯度独立采样，简单多数投票。
    共识对象只含 votes/agreement，不替代主结果字段（主解析仍走 primary）。
    """
    try:
        count = max(1, min(3, int((cfg or {}).get("judge_count") or 1)))
    except Exception:
        count = 1
    raw = []
    objs = []
    for i in range(count):
        jr = _call_llm_role_resilient("judge", judge_prompt, cfg, temperature=0.3 + 0.2 * i)
        raw.append(jr)
        try:
            objs.append(_parse_judge_json(jr.get("content", "")))
        except Exception:
            pass
    consensus = {
        "judge_count": count,
        "valid_judges": len(objs),
        "agreement": round(len(objs) / count, 2) if count else 0.0,
        "votes": {},
        "confidence_votes": {},
    }
    if objs:
        votes = {}
        conf = {}
        for o in objs:
            votes[o.get("verdict")] = votes.get(o.get("verdict"), 0) + 1
            conf[o.get("confidence")] = conf.get(o.get("confidence"), 0) + 1
        majority_verdict = max(votes, key=votes.get)
        majority_conf = max(conf, key=conf.get)
        consensus["votes"] = votes
        consensus["confidence_votes"] = conf
        consensus["majority_verdict"] = majority_verdict
        consensus["majority_confidence"] = majority_conf
    return (raw[0] if raw else None), consensus


def _provider_extra_headers(base_url: str) -> dict:
    """按 base_url 匹配 config.yaml custom_providers[].extra_headers（2026-09-13）。

    本模块用裸 httpx 直发请求，绕过 Hermes 底座的 openai SDK 客户端，因此拿不到
    get_custom_provider_extra_headers 注入的附加头。opencode.ai 的 zen 网关要求每个
    请求带 x-opencode-session，缺则一律 400 MissingSessionID —— 050e0d14 只修了
    Hermes 底座路径，辩论链路仍 400。这里按 base_url/api_base 匹配 provider 条目并
    返回其 extra_headers，使任何 provider 的附加头都能生效。匹配不到返回 {}。
    """
    if not base_url:
        return {}
    try:
        import yaml
        cfg_path = _get_config_path()
        if not cfg_path.exists():
            return {}
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        target = base_url.rstrip("/").lower()
        for entry in data.get("custom_providers") or []:
            if not isinstance(entry, dict):
                continue
            for field in ("base_url", "api_base"):
                candidate = (entry.get(field) or "").rstrip("/").lower()
                if candidate and candidate == target:
                    extra = entry.get("extra_headers")
                    if isinstance(extra, dict) and extra:
                        return {str(k): str(v) for k, v in extra.items()}
                    return {}
    except Exception as e:
        logger.warning(f"Failed to load provider extra_headers for {base_url}: {e}")
    return {}


# 2026-09-13: 瞬时 vs 配置类失败判定 —— 只有瞬时失败才值得重跑（见 _retry_transient_roles）。
_TRANSIENT_HINTS = ("429", "500", "502", "503", "504", "timeout", "timed out",
                    "connect", "connection", "reset", "eof", "remotedisconnected",
                    "readtimeout", "temporarily", "overload", "rate limit", "tpm")
_CONFIG_HINTS = ("401", "403", "400 bad request", "unauthorized", "invalid api key",
                 "missing", "not found", "missing_session", "model_not")


def _is_transient_error(detail: str) -> bool:
    """失败是否属于瞬时类（429/5xx/超时/连接中断）。配置类（400/401/403/模型不存在）返回 False。"""
    d = str(detail or "").lower()
    if not d:
        return False
    if any(t in d for t in _CONFIG_HINTS):
        return False
    return any(t in d for t in _TRANSIENT_HINTS)


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
    # 2026-09-13: 合并 config.yaml custom_providers[].extra_headers
    # （opencode.ai zen 网关必需 x-opencode-session，缺失一律 400 MissingSessionID）
    headers.update(_provider_extra_headers(base_url))
    # 关键：每个角色只有自己的 prompt，没有其他角色的消息
    # 这就是"切断上下文"的实现方式
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    call_id = f"{label}_{int(time.time() * 1000) % 1000000}"

    last_error = ""
    for attempt in range(3):
        _detail = ""
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers, json=payload
                )
                if resp.status_code >= 400:
                    # 2026-09-13: 服务端错误正文是区分 400 MissingSessionID / 401 key 失效 /
                    # 上下文超限的唯一证据。此前只留 "400 Bad Request" 一行，judge 连续失败
                    # 4 次都无法定位（真因是缺 x-opencode-session 请求头）。
                    _detail = f"HTTP {resp.status_code} {resp.text[:300]}"
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
                _detail = (f"empty content (finish_reason={msg.get('finish_reason')}, "
                           f"reasoning={'yes' if msg.get('reasoning_content') else 'no'}, model={model})")
                last_error = _detail[:400]
                time.sleep(2)
        except Exception as e:
            if not _detail:
                _detail = f"{type(e).__name__}: {e}"
            last_error = _detail[:400]
            logger.warning(f"debate {label} attempt {attempt+1} failed: {e} | detail={last_error}")
            time.sleep(3)

    return {
        "content": f"[{label} 辩论生成失败]",
        "call_id": call_id,
        "isolation_verified": True,
        "messages_count": 1,
        "error": True,
        # 2026-09-13: 失败原因随结果回传（配置类 vs 瞬时类），上层据此决定重跑还是报错
        "error_detail": last_error or "unknown",
        "error_model": f"{model} @ {base_url}",
        "transient": _is_transient_error(last_error),
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


def _retry_transient_roles(results: dict, tasks: list, cfg: dict) -> dict:
    """2026-09-13 加固：只重跑「瞬时失败」的角色一次。

    现行策略是 8 角色任一失败即整场辩论作废（不缓存不归档），于是一个角色被 429/
    超时抖一下，整场 8 角色辩论全废。这里对 HTTP 429/5xx/超时/连接中断这类失败再跑
    一次（配置类失败如 400/401 重跑无意义，直接报错并带回 error_detail）。
    """
    try:
        _retry_tasks = [(l, p) for l, p in tasks
                        if results.get(l, {}).get("error") and results.get(l, {}).get("transient")]
        if not _retry_tasks:
            return results
        logger.warning(f"debate 重跑瞬时失败角色: {[l for l, _ in _retry_tasks]}")
        results.update(_call_role_parallel(_retry_tasks, cfg))
    except Exception as e:
        logger.warning(f"debate transient retry pass failed: {e}")
    return results


# ==================== 辩论配置（P0 参数化 2026-08-10） ====================

ALL_ROLES = ["pro_biology", "pro_statistics", "pro_bioinformatics",
             "con_biology", "con_statistics", "con_bioinformatics",
             "con_history", "judge",
             # core9 中立评审（role_preset=core9 时参与）
             "design_review", "reproducibility_review"]

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
        base = Path(os.environ.get("HERMES_HOME", "E:/MemOmics-Agent/hermes_home"))
    return base / "config.yaml"


def _load_debate_config() -> dict:
    """读取 config.yaml 的 debate: 段。缺省返回默认值（行为=现状 homogeneous）。

    config 结构（详见 docs/debate-core-design.md）:
      debate:
        mode: homogeneous | adversarial | multi_model | temperature
        rounds: 1
        scenario_analysis: true   # 赛前场景预判（非生物学辩题换裁判标准）；false 关闭
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
        # v2(2026-08-27): 证据审查器改造 — 全部向后兼容
        "role_preset": "core7",       # core7 | core9（新增设计/可重复性编辑）
        "judge_count": 1,             # 1 | 3（多裁判一致性；>1 成本 ×2-3）
        "rounds_max": 5,              # 上限护栏（防止 rounds=1000 打爆）
        "evidence_mode": False,       # True 时注入证据卡/做引用校验
        "prompt_version": 2,          # 2=v2 证据契约 | 1=legacy（可用 MEMOMICS_DEBATE_LEGACY_PROMPTS=1 回退）
        "judge_digest": True,         # 2026-09-18: 裁决前先让裁判整理（草稿→清晰言论+论据；找不到证据如实写明）
        # 2026-09-18: 赛前场景预判（+1 次调用，走 judge 路由）。用户提出「排版/技术类问题是不是该换裁判」
        # → 辩论前先判本场属于哪类问题，再据此生成各席位身份与裁判评分维度；
        # False 或 env MEMOMICS_DEBATE_NO_SCENARIO=1 则退回原有生物学模板。
        "scenario_analysis": True,
        "max_tokens": {"judge": 8192, "role": 8192, "l1_role": 2048, "l1_judge": 8192},
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


# ==================== 当前使用模型的提供商 / 可用提供商（2026-09-13 用户要求）====================
# 现象：judge 走 config.yaml 里写死的单条通道（opencode-go），该通道一坏 → L2 全灭；
# 而界面里用户"当前使用"的模型（model_config.json）从未参与辩论路由。
# 规则：辩论角色 = 当前使用模型的提供商优先 → 再在可用提供商之间兜底。
_PLACEHOLDER_KEY_TOKENS = ("your_api_key", "your-api-key", "yourkey", "your_key", "insert_key",
                           "changeme", "change_me", "replace_me", "placeholder", "sk-xxx",
                           "api_key_here", "在这里", "请填写")

_model_cfg_cache = {"path": "", "mtime": -1.0, "data": {}}


def _looks_like_placeholder_key(value) -> bool:
    """占位符 key 判定（与 webui/server.py::_is_valid_api_key 同源口径）。"""
    s = str(value or "").strip().lower()
    if not s:
        return True
    if s in ("none", "null", "undefined", "todo", "xxx", "dummy", "test"):
        return True
    if s.startswith(("<", "${")):
        return True
    return any(tok in s for tok in _PLACEHOLDER_KEY_TOKENS)


def _load_global_model_config() -> dict:
    """读取 hermes_home/model_config.json —— 界面「当前模型」的落盘位置。

    按 mtime 缓存重读：用户在界面换了模型/提供商，辩论下一次调用立刻生效。
    （旧实现只在 server 启动时把 DEEPSEEK_* 注入 env 一次，换模型后辩论仍用旧通道。）
    """
    try:
        p = _get_config_path().parent / "model_config.json"
        if not p.exists():
            return {}
        mt = p.stat().st_mtime
        if _model_cfg_cache["path"] == str(p) and _model_cfg_cache["mtime"] == mt:
            return dict(_model_cfg_cache["data"])
        data = json.loads(p.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return {}
        _model_cfg_cache.update({"path": str(p), "mtime": mt, "data": data})
        return dict(data)
    except Exception as e:
        logger.warning(f"Failed to load model_config.json: {e}")
        return {}


def _route_from_config(raw: dict, provider_keys: dict, source: str) -> dict:
    """把 {provider, base_url, api_key, model} 规格化成路由 dict；不可用返回 {}。"""
    raw = raw or {}
    key = str(raw.get("api_key") or "").strip()
    url = str(raw.get("base_url") or raw.get("api_base") or "").rstrip("/")
    model = str(raw.get("model") or "").strip()
    if not key or not url or _looks_like_placeholder_key(key):
        return {}
    pid = ""
    for _pid, _info in (provider_keys or {}).items():
        if str((_info or {}).get("base_url") or "").rstrip("/").lower() == url.lower():
            pid = _pid
            break
    return {"api_key": key, "base_url": url,
            "model": model or "deepseek-v4-flash", "temperature": 0.7,
            "provider": pid or str(raw.get("provider") or source), "source": source}


def _current_model_route(provider_keys: dict = None) -> dict:
    """「当前使用模型的提供商」路由。优先级：会话级 → 全局 model_config.json → env。

    会话级 = server.py 每回合 set_session_context(model_config=...) 注入（多会话各用各的模型）；
    全局 = 界面下拉框当前模型（model_config.json，按 mtime 实时读）；
    env = server 启动时 _sync_debate_env 注入的旧兼容通道（命令行/脚本调用时兜底）。
    """
    pk = provider_keys if provider_keys is not None else _load_provider_keys()
    for raw, source in ((get_session_model_config(), "session"),
                        (_load_global_model_config(), "model_config.json"),
                        ({"api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
                          "base_url": os.environ.get("DEEPSEEK_BASE_URL", ""),
                          "model": os.environ.get("DEEPSEEK_MODEL", "")}, "env")):
        route = _route_from_config(raw, pk, source)
        if route:
            return route
    return {}


_prov_models_cache = {"mtime": -1.0, "data": {}}


def _provider_default_models() -> dict:
    """config.yaml custom_providers[].models 的模型清单 → {pid: [model_id, ...]}（按 mtime 缓存）。

    用途：回退到「别的可用提供商」时要给一个该 provider 真正存在的模型 id，
    否则拿当前模型的 id 去打（如用 dcs 的 deepseek-flash 打 opencode-go）必 400。
    """
    try:
        p = _get_config_path()
        if not p.exists():
            return {}
        mt = p.stat().st_mtime
        if _prov_models_cache["mtime"] == mt:
            return dict(_prov_models_cache["data"])
        import yaml
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        out = {}
        for entry in (data.get("custom_providers") or []):
            if not isinstance(entry, dict):
                continue
            pid = str(entry.get("id") or "").strip()
            ids = [str(m.get("id")) for m in (entry.get("models") or [])
                   if isinstance(m, dict) and m.get("id")]
            if pid and ids:
                out[pid] = ids
        _prov_models_cache.update({"mtime": mt, "data": out})
        return dict(out)
    except Exception as e:
        logger.warning(f"Failed to load provider model list: {e}")
        return {}


def _available_routes(provider_keys: dict = None, exclude: list = None) -> list:
    """「可用提供商」路由表：有 key + base_url、非占位符 key。

    排序与 webui/server.py 一致：deepseek 官方优先，已知死通道（dcs-cloud）靠后。
    """
    pk = provider_keys if provider_keys is not None else _load_provider_keys()
    _known_dead = {"dcs-cloud"}
    _prov_default_model = {"deepseek": "deepseek-v4-flash"}
    _env_model = os.environ.get("DEEPSEEK_MODEL") or "deepseek-v4-flash"
    _listed = _provider_default_models()   # {pid: [该 provider 真实存在的 model id, ...]}
    out, seen = [], set()
    for pid in sorted(pk.keys(), key=lambda p: (p in _known_dead, p != "deepseek")):
        info = pk.get(pid) or {}
        key = str(info.get("api_key") or "").strip()
        url = str(info.get("base_url") or "").rstrip("/")
        if not key or not url or _looks_like_placeholder_key(key):
            continue
        # 模型 id 优先级：deepseek 官方惯例 → config.yaml 里该 provider 的模型清单 → env 模型
        _cands = [_prov_default_model.get(pid)] + list(_listed.get(pid) or []) + [_env_model]
        model = next((m for m in _cands if m), _env_model)
        sig = (url.lower(), model)
        if sig in seen or sig in (exclude or []):
            continue
        seen.add(sig)
        out.append({"api_key": key, "base_url": url, "model": model, "temperature": 0.7,
                    "provider": pid, "source": "provider_keys"})
    return out


def _debate_fingerprint(mode: str, rounds: int, role_model_map: dict, cfg: dict = None,
                        level: str = "L2", evidence_fp: str = "") -> str:
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
    # 2026-09-13: 默认路由改为「当前使用模型的提供商」后，同一 topic 在不同模型下
    # 会产出不同结论 → 当前模型必须进指纹，否则换模型后仍命中旧模型的结果。
    _cur_route = _current_model_route()
    if _cur_route:
        parts.append(f"cur={_cur_route.get('provider')}/{_cur_route.get('model')}")
    if cfg:
        # v2(2026-08-27): 影响产出的新参数一并入指纹，防缓存串用
        for key in ("role_preset", "judge_count", "rounds_max", "prompt_version", "evidence_mode",
                    "judge_digest"):
            v = cfg.get(key)
            if v not in (None, ""):
                parts.append(f"{key}={v}")
        for grp in ("judge", "pro", "con"):
            gc = (cfg.get(grp) or {})
            if gc:
                parts.append(f"{grp}={gc.get('provider','?')}/{gc.get('model','?')}")
    if role_model_map:
        for k in sorted(role_model_map):
            v = role_model_map[k] or {}
            parts.append(f"{k}={v.get('provider','?')}/{v.get('model','?')}")
    if evidence_fp:
        parts.append(f"ev={evidence_fp}")
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
    # 2026-09-13（用户要求）：默认路由 = 「当前使用模型的提供商」（会话级 → 全局
    # model_config.json → env），pro/con 等角色全部跟随界面当前模型，不再吃启动时的旧 env。
    _cur = _current_model_route(provider_keys)
    if _cur:
        return _cur
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
# 2026-08-27 实测修复：deepseek-v4-pro 推理模型在 judge 2048 上限时
# completion_tokens 全被 reasoning 吃掉（finish_reason=length, content 为空），
# 导致裁决永远是 need_more_info/low。提升上限后终稿 JSON 正常输出。
_ROLE_MAX_TOKENS = {"judge": 8192}  # 其余角色（pro/con）默认 8192（推理模型防 reasoning 吃满）
_ROLE_MAX_TOKENS_DEFAULT = 8192

# 2026-09-18：裁判主路由「已知故障」备忘。
# 仲裁前多了一次「首席整理编辑」调用（judge_digest），它与正式裁决共用同一条 judge 路由：
# 主路由挂掉时一次失败要付 3×120s 超时（实测 opencode-go ReadTimeout 全场约 6 分钟），
# 若不做备忘，整理+裁决会对着同一条死路由连付两遍。这里记录刚失败过的主路由，
# TTL 内的后续 judge 调用直接走回退链（回退链本身就是原有逻辑，只是跳过已知死亡的主路由）。
_JUDGE_ROUTE_BAD = {}          # (base_url, model) -> 失败时间戳
_JUDGE_ROUTE_BAD_TTL = 600.0   # 秒


def _role_max_tokens(label: str, cfg: dict = None) -> int:
    """按角色返回 max_tokens；config debate.max_tokens 可覆盖（v2 配置化）。"""
    mt = (cfg or {}).get("max_tokens") or {}
    if not mt:
        return _ROLE_MAX_TOKENS.get(label, _ROLE_MAX_TOKENS_DEFAULT)
    try:
        if label == "judge":
            return max(1024, int(mt.get("judge") or _ROLE_MAX_TOKENS.get("judge", 8192)))
        return max(512, int(mt.get("role") or _ROLE_MAX_TOKENS_DEFAULT))
    except Exception:
        return _ROLE_MAX_TOKENS.get(label, _ROLE_MAX_TOKENS_DEFAULT)


def _call_llm_role(label: str, prompt: str, cfg: dict, temperature: float = None) -> dict:
    """按角色解析模型后调用 _call_llm_sync（隔离性不变：messages 只有该角色自己的 prompt）。"""
    rc = _resolve_role_llm(label, cfg)
    return _call_llm_sync(prompt, label, rc["api_key"], rc["base_url"], rc["model"],
                          temperature=rc["temperature"] if temperature is None else temperature,
                          max_tokens=_role_max_tokens(label, cfg))


def _call_llm_role_resilient(label: str, prompt: str, cfg: dict, temperature: float = None) -> dict:
    """角色 LLM 调用 + 失败回退链（2026-09-13 加固）。

    judge 是整场辩论的单点故障：8 个角色里只有 judge 走 config.yaml 的 debate.judge
    分组 provider（本机 = opencode-go/deepseek-v4-pro），该 provider 一旦 key 失效/
    缺附加头/额度耗尽，L2 就是 100% 失败（2026-09-13 实测：7 个角色全部成功，judge
    一律 400 MissingSessionID，4 次 L2 全部返回 error）。

    回退策略（2026-09-13 用户要求）：分组路由失败后按序回退
    ①「当前使用模型的提供商」（会话级 model_config → 全局 model_config.json → env）
    ②「可用提供商」（provider_keys 里有非占位 key 的通道，deepseek 官方优先）
    成功则标记 fallback_used/fallback_from/fallback_route，让「一个 provider 挂掉」不再拖垮整场辩论。
    非 judge 角色不做回退（保持角色间模型隔离与成本可控）。
    """
    # 2026-09-18：若这条 judge 主路由刚刚失败过（见 _JUDGE_ROUTE_BAD），
    # 不再重付一次 3×120s 超时，直接进入下面的回退链。
    _primary_pre = None
    if label == "judge":
        try:
            _rc_pre = _resolve_role_llm(label, cfg)
            _primary_pre = (str(_rc_pre.get("base_url") or "").rstrip("/").lower(),
                            str(_rc_pre.get("model") or ""))
        except Exception:
            _primary_pre = None
        if _primary_pre and _JUDGE_ROUTE_BAD.get(_primary_pre, 0) > time.time() - _JUDGE_ROUTE_BAD_TTL:
            logger.warning(f"debate judge 主路由 {_primary_pre[1]} 近期已失败"
                           f"（{int(time.time() - _JUDGE_ROUTE_BAD[_primary_pre])}s 前），本次跳过主路由直接用回退链")
            res = {"content": f"[{label} 辩论生成失败]", "call_id": f"{label}_skipped_primary",
                   "isolation_verified": True, "messages_count": 1, "error": True,
                   "error_detail": "primary judge route skipped (recent failure, see _JUDGE_ROUTE_BAD)"}
        else:
            res = _call_llm_role(label, prompt, cfg, temperature=temperature)
    else:
        res = _call_llm_role(label, prompt, cfg, temperature=temperature)
    if not res.get("error"):
        return res
    if label != "judge":
        return res
    if _primary_pre:
        _JUDGE_ROUTE_BAD[_primary_pre] = time.time()
    try:
        rc = _resolve_role_llm(label, cfg)
        _pk = _load_provider_keys()
        _primary_sig = (str(rc.get("base_url") or "").rstrip("/").lower(),
                        str(rc.get("model") or ""))
        # 回退链（2026-09-13 用户要求）：① 当前使用模型的提供商 → ② 可用提供商（deepseek 官方优先）
        _chain = []
        _cur = _current_model_route(_pk)
        if _cur:
            _chain.append(_cur)
        _chain.extend(_available_routes(_pk, exclude=[_primary_sig]))
        _tried = set()
        _last = res
        for _cand in _chain[:3]:
            _sig = (str(_cand.get("base_url") or "").rstrip("/").lower(),
                    str(_cand.get("model") or ""))
            if _sig == _primary_sig or _sig in _tried:
                continue
            _tried.add(_sig)
            logger.warning(
                f"debate judge 主路由 {rc.get('provider')}/{rc.get('model')} 失败"
                f"（{str(res.get('error_detail', ''))[:120]}）"
                f"→ 回退 {_cand.get('provider')}/{_cand.get('model')}")
            res2 = _call_llm_sync(prompt, label, _cand["api_key"], _cand["base_url"], _cand["model"],
                                  temperature=_cand["temperature"] if temperature is None else temperature,
                                  max_tokens=_role_max_tokens(label, cfg))
            res2["fallback_from"] = f"{rc.get('provider')}/{rc.get('model')}"
            if not res2.get("error"):
                res2["fallback_used"] = True
                res2["fallback_route"] = f"{_cand.get('provider')}/{_cand.get('model')}"
                res2["fallback_detail"] = str(res.get("error_detail", ""))[:200]
                return res2
            res2["error_detail"] = (str(res.get("error_detail", ""))[:200]
                                     + " || fallback: " + str(res2.get("error_detail", ""))[:200])
            _last = res2
        return _last
    except Exception as e:
        logger.warning(f"debate judge fallback attempt failed: {e}")
        return res


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
        base = Path(os.environ.get("HERMES_HOME", "E:/MemOmics-Agent/hermes_home"))
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
        in_str = False
        escaped = False
        while j < n:
            ch = text[j]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == '\\':
                    escaped = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        cands.append(text[i:j + 1])
                        break
            j += 1
        if j >= n:
            break
        i = j + 1
    return cands


_ALLOWED_VERDICTS = {"support", "modify", "need_more_info", "ok"}


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
        if isinstance(o, dict):
            v = o.get("verdict")
            # v2(2026-08-27): verdict 必须是合法枚举字符串（防 {"verdict": 1} 误判）
            if isinstance(v, str) and v.strip() and v.lower() in _ALLOWED_VERDICTS:
                o["verdict"] = v.lower()
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
    # v2(2026-08-27): 高置信 + 缺失证据清单 = 矛盾（证据不足还自称高置信）
    if conf == "high" and result.get("missing"):
        issues.append("confidence=high 但 missing 非空（证据不足不可能高置信）")
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

_L1_JUDGE_PROMPT = """你是{persona}。{n}组正反方编辑（独立评审、互不可见）对以下决策给出了意见，请总结双方并裁决。

主题：{topic}
背景：{context}

{debates}

{digest_section}输出格式（严格 JSON）：
{{"verdict": "ok|modify|need_more_info", "confidence": "high|medium|low", "recommended_params": {{}}, "reasoning": "50字内总结"}}"""


def _debate_l1_lightweight(topic: str, context: str, kb: str, cfg: dict, fingerprint: str,
                               evidence_cards: str = "", scenario=None, scenario_res=None) -> str:
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
    use_v2 = _use_v2_prompts(cfg)
    ev = evidence_cards or ""
    _mt = (cfg.get("max_tokens") or {})
    try:
        _l1_role_max = int(_mt.get("l1_role") or 2048)
    except Exception:
        _l1_role_max = 2048
    try:
        _l1_judge_max = int(_mt.get("l1_judge") or 8192)
    except Exception:
        _l1_judge_max = 8192
    # v2 结构化论据较长，记录保留 800 字（legacy 500 字）
    _keep = 800 if use_v2 else 500
    for i in range(n_samples):
        temp = _TEMP_POOL[i % len(_TEMP_POOL)]
        if use_v2:
            pro_prompt = _v2_role_prompt("pro_biology", topic, context, kb or "无", "", ev, scenario=scenario)
            con_prompt = _v2_role_prompt("con_biology", topic, context, kb or "无", "", ev, scenario=scenario)
        else:
            pro_prompt = _L1_PRO_PROMPT.format(topic=topic, context=context, kb_info=kb or "无")
            con_prompt = _L1_CON_PROMPT.format(topic=topic, context=context, kb_info=kb or "无")
        pro = _call_llm_sync(pro_prompt, f"l1_pro_{i}", rc["api_key"], rc["base_url"],
                             rc["model"], temperature=temp, max_tokens=_l1_role_max)
        con = _call_llm_sync(con_prompt, f"l1_con_{i}", rc["api_key"], rc["base_url"],
                             rc["model"], temperature=temp + 0.1, max_tokens=_l1_role_max)
        if pro.get("error") or con.get("error"):
            continue
        debates_text.append(f"### 第{i+1}组（采样温度 {temp:.1f}）\n"
                            f"正方：{pro['content'][:_keep]}\n反方：{con['content'][:_keep]}")
        sample_records.append({"pro": pro["content"][:800], "con": con["content"][:800],
                               "pro_call_id": pro["call_id"], "con_call_id": con["call_id"],
                               "pro_draft_only": str(pro["content"]).startswith("[reasoning草稿"),
                               "con_draft_only": str(con["content"]).startswith("[reasoning草稿")})

    if not debates_text:
        return _fallback_debate(topic, context, kb, "")

    # 2026-09-18（用户要求）：裁决前先做一次「裁判整理」——L1 的采样同样大量返回草稿，
    # 直接喂给裁判 → 卷面很乱、论据挂不上锚点。整理稿同时进入裁判 prompt 与归档。
    _l1_blocks = []
    for _i, _s in enumerate(sample_records):
        _t = _TEMP_POOL[_i % len(_TEMP_POOL)]
        _l1_blocks.append(_digest_block(f"第{_i+1}组 · 正方（采样温度 {_t:.1f}）", _s["pro"], _s.get("pro_draft_only")))
        _l1_blocks.append(_digest_block(f"第{_i+1}组 · 反方（采样温度 {_t:.1f}）", _s["con"], _s.get("con_draft_only")))
    digest_res = _judge_digest(topic, context, _l1_blocks, ev, cfg,
                               extra_note=("## 说明\n本场是 L1 轻量采样：同一模型在不同温度下独立采样 "
                                           f"{len(sample_records)} 组正反方，双方互不可见；请按「组」合并同类陈述，"
                                           "不要把它们当成不同模型的观点。\n\n"))
    _dg_section = _digest_section_text(digest_res)

    if use_v2:
        pro_args = "\n\n".join(s["pro"] for s in sample_records)
        con_args = "\n\n".join(s["con"] for s in sample_records)
        judge_prompt = _v2_judge_prompt(topic, context, pro_args, con_args, ev, digest=_dg_section,
                                        scenario=scenario)
    else:
        _l1_persona = ("生信分析评审的**裁判**" if not isinstance(scenario, dict)
                       or not scenario.get("judge_persona")
                       else f"{scenario['judge_persona']}（本场评审的裁判）")
        judge_prompt = _L1_JUDGE_PROMPT.format(persona=_l1_persona, n=len(debates_text), topic=topic,
                                               context=context, debates="\n\n".join(debates_text),
                                               digest_section=_dg_section)
    judge = _call_llm_sync(judge_prompt, "l1_judge", rc["api_key"], rc["base_url"],
                           rc["model"], temperature=0.3, max_tokens=_l1_judge_max)


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
    _attach_digest(result, digest_res)
    result.update(_scenario_fields(scenario_res))
    if not judge.get("error"):
        try:
            obj = _parse_judge_json(judge["content"])
            result["verdict"] = obj.get("verdict") or "need_more_info"
            result["confidence"] = obj.get("confidence") or "low"
            result["recommended_params"] = obj.get("recommended_params", {}) or {}
        except Exception as e:
            result["verdict_parse_error"] = str(e)[:100]
    else:
        # v2(2026-08-27): L1 裁判失败不再静默 — 下游可区分“信息不足”和“裁判故障”
        result["judge_error"] = True
        result["judge_error_detail"] = "L1 judge LLM call failed (retry exhausted)"

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
                    auto_kb: bool = True, evidence_cards: str = "",
                    role_preset: str = None, judge_count: int = None) -> str:
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
    if role_preset is not None:
        cfg["role_preset"] = str(role_preset)
    if judge_count is not None:
        try:
            cfg["judge_count"] = max(1, min(3, int(judge_count)))
        except Exception:
            cfg["judge_count"] = 1
    mode = str(cfg.get("mode", "homogeneous")).lower()
    # v2(2026-08-27): rounds 上限护栏（默认 5），防极端配置打爆调用量
    _r_raw = int(cfg.get("rounds", 1) or 1)
    try:
        _r_cap = max(1, int(cfg.get("rounds_max") or 5))
    except Exception:
        _r_cap = 5
    rounds = max(1, min(_r_raw, _r_cap))
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
    # v2: 证据卡指纹 — 证据内容变化必须隔离缓存
    ev_fp = _evidence_fingerprint(evidence_cards)
    cfg["evidence_fingerprint"] = ev_fp
    fingerprint = _debate_fingerprint(mode, rounds, rmm, cfg, level=level, evidence_fp=ev_fp)

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
    # ========== 赛前场景预判（2026-09-18 用户要求） ==========
    # 用户原话：「如果辩论的东西不是生物学相关的东西，而是排版，一些技术上的，是不是需要采取
    # 其他的裁判呢？所以辩论之前，也要分析一下场景呢？」→ 先用 1 次短调用判断本场属于哪类问题，
    # 再据此决定各席位身份与裁判评分维度；预判失败就用原有生物学模板继续，不阻断辩论。
    scenario_res = _analyze_scenario(topic, context, cfg)
    scenario = scenario_res.get("scenario") if isinstance(scenario_res, dict) else None

    if level == "L1":
        return _debate_l1_lightweight(topic, context, kb, cfg, fingerprint, evidence_cards,
                                      scenario=scenario, scenario_res=scenario_res)

    try:
        # ========== 辩论轮次循环（P0：rounds>1 时轮间注入上一轮裁判摘要） ==========
        prev_round_summary = ""
        final_judge = None
        final_consensus = None
        digest_res = {}          # 2026-09-18: 裁判整理结果（最后一轮为准，失败留痕）
        for round_no in range(1, rounds + 1):
            round_note = ""
            if round_no > 1 and prev_round_summary:
                round_note = (
                    f"\n\n## 上一轮辩论摘要（第 {round_no - 1} 轮裁判结论，供本轮参考）\n"
                    f"{prev_round_summary}"
                )

            # v2 提示词开关（含证据卡注入）
            use_v2 = _use_v2_prompts(cfg)
            ev = evidence_cards or ""

            # ========== 正方 3 专业编辑（互相不知道，各用专属知识库） ==========
            if use_v2:
                pro_tasks = [
                    ("pro_biology", _v2_role_prompt("pro_biology", topic, context, bio_kb, "", ev, scenario=scenario) + round_note),
                    ("pro_statistics", _v2_role_prompt("pro_statistics", topic, context, stat_kb, "", ev, scenario=scenario) + round_note),
                    ("pro_bioinformatics", _v2_role_prompt("pro_bioinformatics", topic, context, bioinfo_kb_val, "", ev, scenario=scenario) + round_note),
                ]
            else:
                pro_tasks = [
                    ("pro_biology", PRO_BIO_PROMPT.format(topic=topic, context=context, kb_info=bio_kb) + round_note),
                    ("pro_statistics", PRO_STAT_PROMPT.format(topic=topic, context=context, kb_info=stat_kb) + round_note),
                    ("pro_bioinformatics", PRO_BIOINFO_PROMPT.format(topic=topic, context=context, kb_info=bioinfo_kb_val) + round_note),
                ]
            pro_results = _retry_transient_roles(_call_role_parallel(pro_tasks, cfg), pro_tasks, cfg)
            pro_bio = pro_results["pro_biology"]
            pro_stat = pro_results["pro_statistics"]
            pro_bioinfo = pro_results["pro_bioinformatics"]

            # ========== 反方 4 专业编辑（互相不知道，也看不到正方，各用专属知识库） ==========
            if use_v2:
                con_tasks = [
                    ("con_biology", _v2_role_prompt("con_biology", topic, context, bio_kb, "", ev, scenario=scenario) + round_note),
                    ("con_statistics", _v2_role_prompt("con_statistics", topic, context, stat_kb, "", ev, scenario=scenario) + round_note),
                    ("con_bioinformatics", _v2_role_prompt("con_bioinformatics", topic, context, bioinfo_kb_val, "", ev, scenario=scenario) + round_note),
                    ("con_history", _v2_role_prompt("con_history", topic, context, "", hist, ev, scenario=scenario) + round_note),
                ]
            else:
                con_tasks = [
                    ("con_biology", CON_BIO_PROMPT.format(topic=topic, context=context, kb_info=bio_kb) + round_note),
                    ("con_statistics", CON_STAT_PROMPT.format(topic=topic, context=context, kb_info=stat_kb) + round_note),
                    ("con_bioinformatics", CON_BIOINFO_PROMPT.format(topic=topic, context=context, kb_info=bioinfo_kb_val) + round_note),
                    ("con_history", CON_HISTORY_PROMPT.format(topic=topic, context=context, history_errors=hist) + round_note),
                ]
            con_results = _retry_transient_roles(_call_role_parallel(con_tasks, cfg), con_tasks, cfg)
            con_bio = con_results["con_biology"]
            con_stat = con_results["con_statistics"]
            con_bioinfo = con_results["con_bioinformatics"]
            con_history = con_results["con_history"]

            # ========== core9 中立评审（实验设计 / 可重复性） ==========
            use_core9 = use_v2 and str(cfg.get("role_preset", "core7")).lower() == "core9"
            neutral_results = {}
            neutral_args_v2 = ""
            if use_core9:
                for _nl in ("design_review", "reproducibility_review"):
                    _nr = _call_llm_role(_nl, _v2_role_prompt(_nl, topic, context, "通用知识库", "", ev,
                                                     scenario=scenario), cfg)
                    neutral_results[_nl] = _nr
                neutral_args_v2 = "\n\n".join(
                    [f"### {_nl}\n{neutral_results[_nl]['content']}"
                     for _nl in ("design_review", "reproducibility_review")])

            # ========== 裁判整理（2026-09-18 用户要求）：先把草稿整理成清晰言论+论据 ==========
            # 实跑证据：8 个角色里常有 5-7 个不按 JSON 契约输出，只回 [reasoning草稿…]；
            # 裁判直接读草稿 → 卷面乱、论据挂不上锚点。这里先整理一遍，再交给裁判裁决。
            _failed_early = [
                _role_title(_lbl, scenario) for _lbl, _r in (
                    ("pro_biology", pro_bio), ("pro_statistics", pro_stat), ("pro_bioinformatics", pro_bioinfo),
                    ("con_biology", con_bio), ("con_statistics", con_stat), ("con_bioinformatics", con_bioinfo),
                    ("con_history", con_history))
                if (_r or {}).get("error") or "辩论生成失败" in str((_r or {}).get("content", ""))
            ]
            _l2_blocks = [
                _digest_block("正方 · " + _role_title("pro_biology", scenario), pro_bio.get("content", "")),
                _digest_block("正方 · " + _role_title("pro_statistics", scenario), pro_stat.get("content", "")),
                _digest_block("正方 · " + _role_title("pro_bioinformatics", scenario), pro_bioinfo.get("content", "")),
                _digest_block("反方 · " + _role_title("con_biology", scenario), con_bio.get("content", "")),
                _digest_block("反方 · " + _role_title("con_statistics", scenario), con_stat.get("content", "")),
                _digest_block("反方 · " + _role_title("con_bioinformatics", scenario), con_bioinfo.get("content", "")),
                _digest_block("反方 · " + _role_title("con_history", scenario), con_history.get("content", "")),
            ]
            for _nl, _nr in (neutral_results or {}).items():
                _l2_blocks.append(_digest_block("中立 · " + _role_title(_nl, scenario), (_nr or {}).get("content", "")))
            _dg_note = ("## 说明\n本场是多角色对抗（v3）：每个角色是独立 LLM 调用、上下文切断，"
                        "正方看不到反方。请按角色整理上述发言。\n\n"
                        + (_scenario_line(scenario) if scenario else ""))
            if _failed_early:
                _dg_note += ("## 注意\n以下角色本场调用失败、没有发言，请在整理结果里如实注明"
                             "「该角色本次没有输出」，不要替它们编造观点：" + "、".join(_failed_early) + "\n\n")
            digest_res = _judge_digest(topic, context, _l2_blocks, ev, cfg, extra_note=_dg_note)
            _dg_section = _digest_section_text(digest_res)

            # ========== 裁判（唯一看到所有角色论点的，单/多裁判采样） ==========
            if use_v2:
                pro_args_v2 = "\n\n".join([
                    "### 生物学编辑（正方）\n" + pro_bio["content"],
                    "### 统计学编辑（正方）\n" + pro_stat["content"],
                    "### 生信编辑（正方）\n" + pro_bioinfo["content"],
                ])
                con_args_v2 = "\n\n".join([
                    "### 生物学编辑（反方）\n" + con_bio["content"],
                    "### 统计学编辑（反方）\n" + con_stat["content"],
                    "### 生信编辑（反方）\n" + con_bioinfo["content"],
                    "### 历史经验编辑（反方）\n" + con_history["content"],
                ])
                judge_prompt = _v2_judge_prompt(topic, context, pro_args_v2, con_args_v2, ev,
                                                neutral_args=neutral_args_v2, digest=_dg_section,
                                                scenario=scenario)
            else:
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
            primary_judge, consensus = _collect_judge_consensus(judge_prompt, cfg)
            # 2026-09-13 修复：原写法 `primary_judge or _call_llm_role(...)` 里，失败裁判结果是
            # 非空 dict（真值）→ 回退分支永不触发，裁判故障会被当作有效裁决继续走。
            if primary_judge and not primary_judge.get("error"):
                judge = primary_judge
            else:
                judge = _call_llm_role_resilient("judge", judge_prompt, cfg)
            final_judge = judge
            final_consensus = consensus

            # 🔧 P0-1 修复(2026-08-01): 失败检测 — 8个角色任一失败则不缓存不归档
            # 之前: 401/超时失败占位符仍被 _save_debate 缓存72h → 相同topic+context再命中返回占位符
            _all_roles = [pro_bio, pro_stat, pro_bioinfo, con_bio, con_stat, con_bioinfo, con_history, judge] + list(neutral_results.values())
            _failed_roles = [r.get("call_id", "?") for r in _all_roles if r.get("error") or "辩论生成失败" in str(r.get("content", ""))]
            if _failed_roles:
                logger.warning(f"debate FAILED {len(_failed_roles)}/{len(_all_roles)} roles: {_failed_roles[:3]}... 不缓存不归档")
                # 2026-09-13: 失败原因随结果回传（provider/模型 + HTTP 正文）。
                # 之前只有一句「有角色返回占位符」，judge 连续 4 次 L2 失败都要翻日志才能定位。
                _fail_details = {}
                for _r in _all_roles:
                    if not isinstance(_r, dict):
                        continue
                    if _r.get("error") or "辩论生成失败" in str(_r.get("content", "")):
                        _fail_details[_r.get("call_id", "?")] = {
                            "model": str(_r.get("error_model", "")),
                            "detail": str(_r.get("error_detail", "placeholder content"))[:300],
                        }
                return json.dumps({
                    "topic": topic,
                    "debate_format": "多角色对抗（v3）",
                    "error": True,
                    "failed_roles": len(_failed_roles),
                    "failed_role_ids": _failed_roles,
                    "failed_role_details": _fail_details,
                    "judge_verdict": judge.get("content", "") if not judge.get("error") else "裁判也失败",
                    "judge_error_detail": str(judge.get("error_detail", ""))[:300] if judge.get("error") else "",
                    "note": "辩论失败（8角色中有角色返回占位符）。未缓存未归档。failed_role_details 写明每个失败角色"
                             "的 provider/模型与 HTTP 正文：400/401 多为配置或附加头问题，429/5xx 属瞬时问题（已自动重跑一次）。",
                }, ensure_ascii=False, indent=2)

            # 轮间摘要（供下一轮 pro/con 参考；rounds=1 时不生效）
            prev_round_summary = (judge.get("content") or "")[:1500]

        judge = final_judge

        # ========== 组装结果（含隔离验证信息） ==========
        result = {
            "topic": topic,
            "debate_format": "多角色对抗（v3）",
            "pro_arguments": {
                "biology": {"argument": pro_bio["content"], "call_id": pro_bio["call_id"],
                            "draft_only": str(pro_bio["content"]).startswith("[reasoning草稿"),
                            "used_reasoning_fallback": bool(pro_bio.get("used_reasoning_fallback"))},
                "statistics": {"argument": pro_stat["content"], "call_id": pro_stat["call_id"],
                               "draft_only": str(pro_stat["content"]).startswith("[reasoning草稿"),
                               "used_reasoning_fallback": bool(pro_stat.get("used_reasoning_fallback"))},
                "bioinformatics": {"argument": pro_bioinfo["content"], "call_id": pro_bioinfo["call_id"],
                                   "draft_only": str(pro_bioinfo["content"]).startswith("[reasoning草稿"),
                                   "used_reasoning_fallback": bool(pro_bioinfo.get("used_reasoning_fallback"))},
            },
            "con_arguments": {
                "biology": {"argument": con_bio["content"], "call_id": con_bio["call_id"],
                            "draft_only": str(con_bio["content"]).startswith("[reasoning草稿"),
                            "used_reasoning_fallback": bool(con_bio.get("used_reasoning_fallback"))},
                "statistics": {"argument": con_stat["content"], "call_id": con_stat["call_id"],
                               "draft_only": str(con_stat["content"]).startswith("[reasoning草稿"),
                               "used_reasoning_fallback": bool(con_stat.get("used_reasoning_fallback"))},
                "bioinformatics": {"argument": con_bioinfo["content"], "call_id": con_bioinfo["call_id"],
                                   "draft_only": str(con_bioinfo["content"]).startswith("[reasoning草稿"),
                                   "used_reasoning_fallback": bool(con_bioinfo.get("used_reasoning_fallback"))},
                "history": {"argument": con_history["content"], "call_id": con_history["call_id"],
                            "draft_only": str(con_history["content"]).startswith("[reasoning草稿"),
                            "used_reasoning_fallback": bool(con_history.get("used_reasoning_fallback"))},
            },
            "draft_only_roles": [
                _l for _l, _r in [("pro_biology", pro_bio), ("pro_statistics", pro_stat),
                                  ("pro_bioinformatics", pro_bioinfo), ("con_biology", con_bio),
                                  ("con_statistics", con_stat), ("con_bioinformatics", con_bioinfo),
                                  ("con_history", con_history),
                                  ("design_review", neutral_results.get("design_review")),
                                  ("reproducibility_review", neutral_results.get("reproducibility_review"))]
                if isinstance(_r, dict) and str(_r.get("content", "")).startswith("[reasoning草稿")
            ],
            "neutral_reviews": {
                name: {"argument": nr.get("content", ""), "call_id": nr.get("call_id", ""),
                       "draft_only": str(nr.get("content", "")).startswith("[reasoning草稿"),
                       "used_reasoning_fallback": bool(nr.get("used_reasoning_fallback"))}
                for name, nr in neutral_results.items()
            },
            "judge_verdict": judge["content"],
            # 2026-09-18: 裁判整理稿（草稿→清晰言论+论据；[找不到论据]=原文没有外部证据）
            **_digest_fields(digest_res),
            # 2026-09-18: 赛前场景预判（角色身份与裁判 rubric 按本场场景生成；失败也留痕）
            **_scenario_fields(scenario_res),
            # 2026-09-13: 裁判走回退路由时留痕（实验记录必须能看出真实使用的模型）
            "judge_fallback": ({"from_route": judge.get("fallback_from"),
                                "detail": str(judge.get("fallback_detail", ""))[:200]}
                               if judge.get("fallback_used") else None),
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
            # v2: rubrics / missing 与多裁判一致性
            if _judge_obj.get("rubrics"):
                result["rubrics"] = _judge_obj.get("rubrics") or {}
            if _judge_obj.get("missing"):
                result["missing"] = _judge_obj.get("missing") or []
            if final_consensus and final_consensus.get("judge_count", 1) > 1:
                result["judge_consensus"] = final_consensus
                if final_consensus.get("majority_verdict"):
                    result["verdict"] = final_consensus["majority_verdict"]
                    result["confidence"] = final_consensus.get("majority_confidence") or result["confidence"]
                else:
                    # 多裁判全部解析失败 → 没有可靠裁决
                    result["verdict"] = "need_more_info"
                    result["confidence"] = "low"
                    result["judge_consensus"]["all_judges_failed"] = True
        except Exception as _je:
            result["verdict"] = "need_more_info"
            result["confidence"] = "low"
            result["recommended_params"] = {}
            result["verdict_parse_error"] = str(_je)[:100]
            if final_consensus and final_consensus.get("judge_count", 1) > 1:
                result["judge_consensus"] = final_consensus
                result["judge_consensus"]["primary_parse_failed"] = True

        # ========== B2(2026-08-11): 裁决一致性门禁 ==========
        # 实证 bug：_debates/ 中 3 条 need_more_info+high 矛盾裁决已进入缓存。
        # 矛盾裁决 → judge 独立重裁一次（上下文切断）→ 仍矛盾则强制降级 low，
        # 且禁止回流 skill_evolution（垃圾不得入库）。
        _issues = _check_consistency(result)
        if _issues:
            logger.warning(f"debate verdict inconsistent {_issues}; judge 重裁一次")
            try:
                _judge2 = _call_llm_role_resilient("judge", judge_prompt, cfg)
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
                evidence_cards=args.get("evidence_cards", ""),
                role_preset=args.get("role_preset") or None,
                judge_count=args.get("judge_count") or None,
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
