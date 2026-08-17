#!/usr/bin/env python3
"""Serial multi-role debate — validated fallback when debate_analysis 8/8 fails.

Design (user-suggested, validated 2026-08-01, 8/8 roles + judge success):
  Phase 1: pro 3 roles (serial, isolated)
  Phase 2: con 4 roles (serial, isolated, blind to pro)
  Phase 3: judge (sees everything) -> verdict JSON

Keys read from hermes_home/model_config.json (= _current_model, the WORKING
provider). DO NOT read the dcs-cloud entry in provider_keys.json — its key can
be stale (401), which is the #1 cause of 8/8 "辩论生成失败".

Usage:
  1. Edit TOPIC / CONTEXT / PROMPTS for your analysis.
  2. python run_serial_debate.py
  3. Archive auto-saved to results/<session>/log/debate_{ts}_serial_{topic}.json
"""
import json, os, time, sys, traceback
import httpx

RESULTS_DIR = "MEMOMICS_HOME/results/memomics-2f229850/log"  # EDIT: session log dir
os.makedirs(RESULTS_DIR, exist_ok=True)

with open("MEMOMICS_HOME/hermes_home/model_config.json", "r", encoding="utf-8") as f:
    mc = json.load(f)
API_KEY = mc["api_key"]
BASE_URL = mc["base_url"].rstrip("/")
MODEL = mc["model"]

TOPIC = "你的辩论主题"
CONTEXT = "数据/参数/结果摘要"

PROMPTS = {
    "pro_biology":     "你是生物学编辑（正方）。请论证以下结论可靠：\n【主题】{topic}\n【背景】{context}\n给 2-3 条支持论据。",
    "pro_statistics":  "你是统计学编辑（正方）。请论证以下结论可靠：\n【主题】{topic}\n【背景】{context}\n给 2-3 条支持论据，承认局限但给出可辩护点。",
    "pro_bioinfo":     "你是生信编辑（正方）。请论证以下结论可靠：\n【主题】{topic}\n【背景】{context}\n给 2-3 条支持论据。",
    "con_biology":     "你是生物学编辑（反方）。请质疑以下结论：\n【主题】{topic}\n【背景】{context}\n给 2-3 条质疑。",
    "con_statistics":  "你是统计学编辑（反方）。请质疑以下结论：\n【主题】{topic}\n【背景】{context}\n重点：伪重复、多重比较、效应量。",
    "con_bioinfo":     "你是生信编辑（反方）。请质疑以下结论：\n【主题】{topic}\n【背景】{context}\n给 2-3 条方法学质疑。",
    "con_history":     "你是历史经验编辑（反方）。基于过往分析教训质疑：\n【主题】{topic}\n【背景】{context}\n这类分析容易犯什么错？",
}

JUDGE_PROMPT = """你是裁判编辑（最终权威）。审阅多角色辩论并裁决。

【主题】{topic}
【背景】{context}

## 正方论证
{pro_biology}

{pro_statistics}

{pro_bioinfo}

## 反方论证
{con_biology}

{con_statistics}

{con_bioinfo}

{con_history}

## 裁判要求
给出：
1. 各方论证强度评估（1-10分）
2. 最终裁决：support / modify / need_more_info
3. 置信度：high / medium / low
4. 如建议修改，给出具体推荐
5. 裁决理由（300字以内）

格式：
```json
{{
  "scores": {{"pro_biology": <1-10>, "pro_statistics": <1-10>, "pro_bioinformatics": <1-10>,
             "con_biology": <1-10>, "con_statistics": <1-10>, "con_bioinformatics": <1-10>, "con_history": <1-10>}},
  "verdict": "support | modify | need_more_info",
  "confidence": "high | medium | low",
  "recommended_params": {{}},
  "reasoning": "..."
}}
```"""


def call_llm(prompt, label, timeout=120, max_retries=2):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": MODEL,
               "messages": [{"role": "user", "content": prompt}],
               "max_tokens": 4096, "temperature": 0.7}
    call_id = f"{label}_{int(time.time()*1000) % 1000000}"
    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(f"{BASE_URL}/chat/completions",
                                   headers=headers, json=payload)
                resp.raise_for_status()
                msg = resp.json()["choices"][0]["message"]
                content = msg.get("content", "")
                reasoning = msg.get("reasoning_content", "")
                # deepseek-v4-flash: content often empty, answer in reasoning_content
                if (not content or len(content.strip()) < 10) and reasoning:
                    content = reasoning
                if content and len(content.strip()) > 10:
                    return {"content": content, "call_id": call_id,
                            "isolation_verified": True, "messages_count": 1}
                time.sleep(2)
        except Exception as e:
            print(f"  [{label}] attempt {attempt+1} failed: {type(e).__name__}: {e}", flush=True)
            time.sleep(3)
    return {"content": f"[{label} 辩论生成失败]", "call_id": call_id,
            "isolation_verified": True, "messages_count": 1, "error": True}


def main():
    t0 = time.time()
    print("Serial multi-role debate...")
    pro, con = {}, {}
    for label in ["pro_biology", "pro_statistics", "pro_bioinfo"]:
        pro[label] = call_llm(PROMPTS[label].format(topic=TOPIC, context=CONTEXT), label)
        print(f"  {'OK' if not pro[label].get('error') else 'FAIL'} {label}")
    for label in ["con_biology", "con_statistics", "con_bioinfo", "con_history"]:
        con[label] = call_llm(PROMPTS[label].format(topic=TOPIC, context=CONTEXT), label)
        print(f"  {'OK' if not con[label].get('error') else 'FAIL'} {label}")
    judge_input = {**{k: v.get("content", "") for k, v in pro.items()},
                   **{k: v.get("content", "") for k, v in con.items()}}
    judge = call_llm(JUDGE_PROMPT.format(topic=TOPIC, context=CONTEXT, **judge_input), "judge", timeout=180)

    result = {"topic": TOPIC, "context": CONTEXT, "model": MODEL,
              "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
              "elapsed_sec": round(time.time() - t0, 1),
              "pro": {k: {"content": v.get("content", ""), "call_id": v.get("call_id", "")} for k, v in pro.items()},
              "con": {k: {"content": v.get("content", ""), "call_id": v.get("call_id", "")} for k, v in con.items()},
              "judge": {"content": judge.get("content", ""), "call_id": judge.get("call_id", "")}}
    ts = time.strftime("%Y%m%d_%H%M%S")
    archive = os.path.join(RESULTS_DIR, f"debate_{ts}_serial.json")
    with open(archive, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    ok = sum(1 for r in list(pro.values()) + list(con.values()) + [judge] if not r.get("error"))
    print(f"Success {ok}/8 | archive={archive} | elapsed={result['elapsed_sec']}s")
    jc = judge.get("content", "")
    if jc and "辩论生成失败" not in jc:
        print("\n【裁判裁决】\n" + jc[:1500])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
