"""debate_analysis — 多角色正反方切断上下文对抗辩论工具。

v3 设计（多角色）:
1. 正方 3 个角色（各自独立 LLM 调用，互相看不到）：
   - 生物学 agent：从 marker gene / 已知生物学知识角度支持
   - 统计学 agent：从显著性 / 效应量 / 样本量角度支持
   - 生信 agent：从 QC 指标 / 双胞率 / 污染率 / 聚类质量角度支持
2. 反方 4 个角色（各自独立 LLM 调用，互相看不到，也看不到正方）：
   - 生物学 agent：从异质性 / 批次效应 / marker 重叠角度质疑
   - 统计学 agent：从多重比较 / 假阳性 / 统计功效角度质疑
   - 生信 agent：从降维质量 / 聚类稳定性 / 注释置信度角度质疑
   - 历史经验 agent：从 error_memory/errors.jsonl 历史报错记录角度质疑
3. 裁判（LLM 决断）— 看到正方+反方所有角色后给出最终裁决

上下文隔离机制：
- 每个角色是独立的 HTTP API 调用，messages 只包含该角色自己的 prompt
- 正方角色不知道反方角色说了什么，反之亦然
- 正方角色之间也互相不知道
- 裁判是唯一能看到所有角色论点的
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
import httpx

logger = logging.getLogger(__name__)

SCHEMA = {
    "name": "debate_analysis",
    "description": (
        "Trigger a multi-role structured debate on an analysis decision or result. "
        "Pro side has 3 independent role agents (biology/statistics/bioinformatics), "
        "Con side has 4 independent role agents (biology/statistics/bioinformatics/history). "
        "Each role makes an INDEPENDENT LLM call — they cannot see each other's arguments. "
        "A judge agent reviews ALL arguments and gives a final verdict with confidence level. "
        "Use for: parameter choices, cell type annotation disputes, method selection, "
        "result validation, biological conclusion verification. "
        "MUST call this when encountering uncertain parameters or debatable results."
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
                "description": "Relevant info from knowledge base (parameters, references). If empty, debate will use general knowledge.",
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

PRO_BIO_PROMPT = """你是一位**生物学正方辩手**。你的任务是从生物学角度**支持**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 知识库参考
{kb_info}

请从以下生物学角度论证为什么这个决策/结论是合理的：
1. **Marker gene 验证**：相关标记基因的表达模式是否支持？
2. **已知生物学知识**：与文献中已知的细胞类型/组织特征是否一致？
3. **生物学预期**：结果是否符合该物种/组织/方向的生物学预期？

要求：
- 给出具体的基因名、表达数据、文献引用
- 不要空话，要有数据支撑
- 控制在 300 字以内
- 你不知道其他辩手的观点，请独立思考
"""

PRO_STAT_PROMPT = """你是一位**统计学正方辩手**。你的任务是从统计学角度**支持**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 知识库参考
{kb_info}

请从以下统计学角度论证为什么这个决策/结论是合理的：
1. **显著性**：p值、FDR是否达到阈值？效应量是否足够大？
2. **样本量**：细胞数/样本数是否足够支持这个结论？
3. **分布特征**：数据的分布是否符合方法的假设？

要求：
- 给出具体的数值（p值、效应量、置信区间）
- 不要空话，要有数据支撑
- 控制在 300 字以内
- 你不知道其他辩手的观点，请独立思考
"""

PRO_BIOINFO_PROMPT = """你是一位**生信正方辩手**。你的任务是从生信分析质量角度**支持**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 知识库参考
{kb_info}

请从以下生信分析质量角度论证为什么这个决策/结论是合理的：
1. **QC 指标**：nFeature/nCount/percent.mt 分布是否合理？
2. **聚类质量**：轮廓系数、聚类稳定性是否达标？双胞率是否在可接受范围？
3. **分析流程**：参数选择是否符合最佳实践？是否有遗漏的步骤？

要求：
- 给出具体的 QC 数值和分析指标
- 不要空话，要有数据支撑
- 控制在 300 字以内
- 你不知道其他辩手的观点，请独立思考
"""

# ==================== 反方角色 prompts ====================

CON_BIO_PROMPT = """你是一位**生物学反方辩手**。你的任务是从生物学角度**质疑**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 知识库参考
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
- 你不知道其他辩手的观点，请独立思考
"""

CON_STAT_PROMPT = """你是一位**统计学反方辩手**。你的任务是从统计学角度**质疑**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 知识库参考
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
- 你不知道其他辩手的观点，请独立思考
"""

CON_BIOINFO_PROMPT = """你是一位**生信反方辩手**。你的任务是从生信分析质量角度**质疑**以下分析决策或结论。

## 辩论主题
{topic}

## 上下文
{context}

## 知识库参考
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
- 你不知道其他辩手的观点，请独立思考
"""

CON_HISTORY_PROMPT = """你是一位**历史经验反方辩手**。你的任务是从历史报错和经验记录角度**质疑**以下分析决策或结论。

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
- 你不知道其他辩手的观点，请独立思考
"""

# ==================== 裁判 prompt ====================

JUDGE_PROMPT = """你是生信分析多角色辩论的**裁判**。7位辩手对以下决策进行了辩论，请给出最终裁决。

## 辩论主题
{topic}

## 上下文
{context}

## 正方论证（3位角色，各自独立）

### 生物学正方
{pro_bio}

### 统计学正方
{pro_stat}

### 生信正方
{pro_bioinfo}

## 反方论证（4位角色，各自独立）

### 生物学反方
{con_bio}

### 统计学反方
{con_stat}

### 生信反方
{con_bioinfo}

### 历史经验反方
{con_history}

## 裁判要求

请给出：
1. **各方论证强度评估**（1-10分）
2. **最终裁决**：支持原决策 / 修改参数 / 需要更多信息
3. **置信度**：高 / 中 / 低（表示对裁决的信心程度）
4. 如果建议修改，给出具体推荐参数
5. 裁决理由（300字以内）

**重要**：正方和反方是独立生成的（切断上下文），你不能假设他们看过彼此的论点。你需要综合判断哪方更有说服力。

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


def debate_analysis(topic: str, context: str, knowledge_base_info: str = "",
                    history_errors: str = "") -> str:
    """多角色辩论 — 正方3角色 + 反方4角色 + 裁判，全部独立 LLM 调用。

    上下文隔离实现：
    - 每个角色调用 _call_llm_sync()，传入只包含该角色 prompt 的 messages
    - 正方角色之间不知道彼此（各自独立调用）
    - 反方角色之间不知道彼此（各自独立调用）
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

    try:
        # ========== 正方 3 角色（各自独立调用，互相不知道） ==========
        pro_bio = _call_llm_sync(
            PRO_BIO_PROMPT.format(topic=topic, context=context, kb_info=kb),
            "pro_biology", api_key, base_url, model
        )
        time.sleep(0.5)

        pro_stat = _call_llm_sync(
            PRO_STAT_PROMPT.format(topic=topic, context=context, kb_info=kb),
            "pro_statistics", api_key, base_url, model
        )
        time.sleep(0.5)

        pro_bioinfo = _call_llm_sync(
            PRO_BIOINFO_PROMPT.format(topic=topic, context=context, kb_info=kb),
            "pro_bioinformatics", api_key, base_url, model
        )
        time.sleep(0.5)

        # ========== 反方 4 角色（各自独立调用，互相不知道，也看不到正方） ==========
        con_bio = _call_llm_sync(
            CON_BIO_PROMPT.format(topic=topic, context=context, kb_info=kb),
            "con_biology", api_key, base_url, model
        )
        time.sleep(0.5)

        con_stat = _call_llm_sync(
            CON_STAT_PROMPT.format(topic=topic, context=context, kb_info=kb),
            "con_statistics", api_key, base_url, model
        )
        time.sleep(0.5)

        con_bioinfo = _call_llm_sync(
            CON_BIOINFO_PROMPT.format(topic=topic, context=context, kb_info=kb),
            "con_bioinformatics", api_key, base_url, model
        )
        time.sleep(0.5)

        con_history = _call_llm_sync(
            CON_HISTORY_PROMPT.format(topic=topic, context=context, history_errors=hist),
            "con_history", api_key, base_url, model
        )
        time.sleep(0.5)

        # ========== 裁判（唯一看到所有角色论点的） ==========
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
                "多角色辩论（v3）：正方3角色（生物学/统计学/生信）+ 反方4角色（生物学/统计学/生信/历史经验），"
                "每个角色独立 LLM 调用（切断上下文），裁判综合7方给出裁决+置信度。"
            )
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.warning(f"Multi-role debate failed, using fallback: {e}")
        return _fallback_debate(topic, context, knowledge_base_info, history_errors)


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
            "正方（3角色，各自独立思考，互相不知道）：\n"
            "1. 生物学正方：从 marker gene / 已知生物学知识角度支持\n"
            "2. 统计学正方：从显著性 / 效应量 / 样本量角度支持\n"
            "3. 生信正方：从 QC 指标 / 双胞率 / 聚类质量角度支持\n\n"
            "反方（4角色，各自独立思考，互相不知道，也看不到正方）：\n"
            "4. 生物学反方：从异质性 / 批次效应 / marker 重叠角度质疑\n"
            "5. 统计学反方：从多重比较 / 假阳性 / 统计功效角度质疑\n"
            "6. 生信反方：从降维质量 / 聚类稳定性 / 注释置信度角度质疑\n"
            "7. 历史经验反方：从 error_memory 历史报错记录角度质疑\n\n"
            "裁判（看到所有7方后裁决）：\n"
            "8. 综合裁决：支持/修改/需要更多信息 + 置信度（高/中/低）\n\n"
            "注意：正方和反方必须独立思考，不能互相看到。"
        ),
        "isolation_note": (
            "上下文隔离实现：每个角色是独立的 LLM 调用，messages 只包含该角色自己的 prompt。"
            "正方不知道反方说了什么，正方角色之间也互相不知道。"
            "裁判是唯一能看到所有角色论点的。"
        ),
        "note": "LLM API 调用失败，退化为 prompt 模式。请在回复中按上述步骤执行辩论。"
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


def _register():
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

_register()
