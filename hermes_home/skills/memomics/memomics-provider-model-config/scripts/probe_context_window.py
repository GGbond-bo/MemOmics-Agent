#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
端点真实上下文窗口探针（MemOmics / Hermes 模型配置类任务专用）

用法:
    python probe_context_window.py                      # 默认阶梯 131072,200000,600000
    python probe_context_window.py 200000,600000,900000 # 自定义目标 token 阶梯

结论怎么读:
  - usage.prompt_tokens = 精确 token 数（唯一可信的记账口径，不要用 chars/4 估）
  - needle_recalled=True        -> 整段 prompt 真的进了窗口
  - http=429 "... TPM limit"    -> 限流，不是窗口不足，不能当窗口证据
  - max_tokens 报错里的区间      -> 即该模型的 max output 上限（如 [1, 393216]）

坑（实测）:
  - 字符/token 比例随语言与文本重复度剧烈变化: 重复英文句实测 ≈ 6.94 chars/token。
    先用一次小请求拿 usage.prompt_tokens 自校准 CHARS_PER_TOKEN，否则阶梯会严重偏小。
  - /models 端点常超时不响应: 必须 try/except 包住，拿不到就靠 chat 探针。
  - 大 prompt 会撞 TPM 限流: 阶梯一次跑完 + 相邻大请求留间隔，不要一步一个终端调用
    （重复同类探针会触发平台循环检测强制干预）。
"""
import json, os, re, sys, time

# ---- 按需修改 ----
CFG = r"E:/MemOmics-Agent/hermes_home/config.yaml"   # 读根级 api_base / api_key（不打印 key）
MODEL = "deepseek-flash"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "probe_context_window.json")
CHARS_PER_TOKEN = 6.94        # 自校准起点（重复英文句），跑完第一档请按 usage 修正
# ----------------

def read_cfg():
    txt = open(CFG, encoding="utf-8").read()
    base = re.search(r"^api_base:\s*(\S+)", txt, re.M).group(1).rstrip("/")
    key = re.findall(r"^api_key:\s*(\S+)", txt, re.M)[0]   # 根级那条
    return base, key

def post(url, key, payload, timeout=600):
    import requests
    r = requests.post(url, headers={"Authorization": f"Bearer {key}",
                                    "Content-Type": "application/json"},
                      json=payload, timeout=timeout)
    try:
        body = r.json()
    except Exception:
        body = {"_raw": r.text[:2000]}
    return r.status_code, body

def err_text(body):
    if isinstance(body, dict):
        e = body.get("error")
        if isinstance(e, dict):
            return str(e.get("message") or e)
        if e:
            return str(e)
        return json.dumps(body, ensure_ascii=False)[:600]
    return str(body)[:600]

def make_prompt(approx_tokens, needle):
    """构造约 approx_tokens 个 token 的英文文本，needle 埋在 ~92% 深度。"""
    chunk = ("The hippocampus shows age related decline in neural stem cell activity "
             "and chromatin accessibility across mammalian species. ")
    n = max(1, int(approx_tokens / (len(chunk) / CHARS_PER_TOKEN)))
    body = [chunk] * n
    body.insert(int(len(body) * 0.92),
                f"  [MAGIC] The secret code is {needle}. Remember it. [/MAGIC]  ")
    return ("".join(body) +
            "\n\nQuestion: what is the secret code? Answer with only the code.")

def main():
    approx = [int(x) for x in (sys.argv[1].split(",") if len(sys.argv) > 1
                               else ["131072", "200000", "600000"])]
    base, key = read_cfg()
    url_chat = f"{base}/chat/completions"
    res = {"base_url": base, "model": MODEL, "maxtok_probe": [], "steps": []}
    print(f"[cfg] base={base} key={key[:7]}**** model={MODEL}")

    # 1) /models —— 端点自报的 context_length（常常超时，非致命）
    try:
        import requests
        r = requests.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=60)
        md = r.json()
        ids = [m.get("id") for m in md.get("data", [])]
        res["models_endpoint"] = {"status": r.status_code, "count": len(ids)}
        hit = [m for m in md.get("data", []) if (m.get("id") or "").endswith(MODEL)]
        print(f"[1] /models status={r.status_code} n={len(ids)} 命中={hit[:1]}")
        res["models_endpoint"]["entry"] = hit[:1]
    except Exception as e:
        res["models_endpoint"] = {"status": -1, "error": str(e)[:200]}
        print(f"[1] /models 不可用（{type(e).__name__}），改用 chat 探针")

    # 2) max_tokens 巨值探针 —— 从报错文案抠 max output 上限（极便宜）
    for mt in [2_000_000, 1_000_000, 262_144, 131_072, 65_536]:
        try:
            c, b = post(url_chat, key, {"model": MODEL, "max_tokens": mt,
                                        "messages": [{"role": "user", "content": "hi"}]})
            msg = err_text(b) if c >= 400 else "OK"
        except Exception as e:
            c, msg = -1, f"EXC {e}"
        res["maxtok_probe"].append({"max_tokens": mt, "http": c, "msg": msg[:300]})
        print(f"[2] max_tokens={mt:>9,} -> http={c} : {msg[:180]}")
        if c < 400:
            break

    # 3) 长 prompt 阶梯 + 针尖召回
    for t in approx:
        needle = "ZQ7" + str(t)[-3:]
        text = make_prompt(t, needle)
        step = {"target_tokens_approx": t, "chars": len(text), "needle": needle}
        t0 = time.time()
        try:
            c, b = post(url_chat, key, {"model": MODEL, "max_tokens": 64, "stream": False,
                                        "messages": [{"role": "user", "content": text}]})
            step["http"] = c
            step["latency_s"] = round(time.time() - t0, 1)
            if c < 400:
                u = b.get("usage") or {}
                content = ""
                for ch in (b.get("choices") or []):
                    content = (ch.get("message") or {}).get("content") or ""
                step.update(prompt_tokens=u.get("prompt_tokens"),
                            completion_tokens=u.get("completion_tokens"),
                            answer=content.strip()[:120],
                            needle_recalled=needle in content)
                print(f"[3] ~{t:>9,} tok (exact {u.get('prompt_tokens')}) -> http={c} "
                      f"recall={step['needle_recalled']} {step['latency_s']}s  {content.strip()[:40]!r}")
            else:
                step["error"] = err_text(b)[:400]
                print(f"[3] ~{t:>9,} tok -> http={c} ERROR: {step['error'][:180]}")
        except Exception as e:
            step.update(http=-1, error=f"EXC {type(e).__name__}: {e}"[:300])
            print(f"[3] ~{t:>9,} tok -> EXC {e}")
        res["steps"].append(step)

    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n[saved] {OUT}")

if __name__ == "__main__":
    main()
