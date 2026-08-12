#!/usr/bin/env python3
"""
DashScope qwen-image 文生图脚本（MemOmics 已验证版本 2026-08-12）。

用法:
    python dashscope_text2image.py "科研风格的真核细胞示意图" [--size 1024*1024] [--out cell.png] [--model qwen-image-3.0]

已验证的关键点:
1. 端点 = multimodal-generation/generation（同步），NOT /images/generations (404), NOT text2image/image-synthesis
2. 不要加 X-DashScope-Async header（会 403/走异步任务流）
3. key 必须用 Python open() 读原始字节 —— Hermes 工具输出层会把 sk- 开头的 key 脱敏成 «redacted:sk-…»
4. key 路径 = config["dashscope"]["api_key"]（不是顶层）
5. 响应解析 = output.choices[0].message.content[0].image -> URL
"""
import argparse
import json
import os
import sys
import time
import urllib.request

_BASE = "https://dashscope.aliyuncs.com"
_CREATE_URL = f"{_BASE}/api/v1/services/aigc/multimodal-generation/generation"


def _load_config() -> dict:
    """读 HERMES_HOME/image_gen_config.json（WebUI 设置页，优先级最高），
    回退 config.yaml image_gen.dashscope 段和环境变量 DASHSCOPE_API_KEY。"""
    merged = {}
    # 1) standalone image_gen_config.json
    for home in (os.environ.get("HERMES_HOME", ""), "hermes_home", "E:/MemOmics-Agent/hermes_home"):
        p = os.path.join(home, "image_gen_config.json")
        if home and os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    data = json.load(fh)
                sub = data.get("dashscope", {})
                if isinstance(sub, dict):
                    merged.update(sub)
                break
            except Exception:
                pass
    # 2) 环境变量兜底
    if not merged.get("api_key"):
        merged["api_key"] = os.environ.get("DASHSCOPE_API_KEY", "")
    return merged


def generate(prompt: str, size: str = "1024*1024", model: str = "qwen-image-3.0",
             out: str = None, timeout: int = 180) -> str:
    cfg = _load_config()
    api_key = str(cfg.get("api_key", "") or "").strip()
    if not api_key:
        raise RuntimeError("未找到 DashScope API key（检查 image_gen_config.json 或 DASHSCOPE_API_KEY）")
    model = cfg.get("model", model)
    size = cfg.get("size", size)

    payload = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {"size": size},
    }
    req = urllib.request.Request(
        _CREATE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if result.get("code") not in (None, "Success", "200"):
        raise RuntimeError(f"DashScope 返回错误: {result}")
    try:
        img_url = result["output"]["choices"][0]["message"]["content"][0]["image"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"响应解析失败，结构异常: {json.dumps(result, ensure_ascii=False)[:500]}") from exc

    out = out or f"image_gen_{int(time.time())}.png"
    with urllib.request.urlopen(img_url, timeout=timeout) as resp:
        data = resp.read()
    with open(out, "wb") as fh:
        fh.write(data)
    print(f"OK 已保存: {os.path.abspath(out)} ({len(data) / 1e6:.2f} MB)")
    return os.path.abspath(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="DashScope qwen-image 文生图")
    ap.add_argument("prompt", help="图片描述（中文/英文均可）")
    ap.add_argument("--size", default="1024*1024", help="尺寸: 1024*1024 / 1280*720 / 720*1280")
    ap.add_argument("--out", default=None, help="输出文件路径")
    ap.add_argument("--model", default="qwen-image-3.0")
    args = ap.parse_args()
    try:
        generate(args.prompt, size=args.size, model=args.model, out=args.out)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
