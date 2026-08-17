#!/usr/bin/env python3
"""DashScope qwen-image 文生图 CLI — 读取 image_gen_config.json 调通义万相生成图片。

用法:
  python generate_image.py "PROMPT" [--size 1024*1024] [--out DIR]

端点（2026-08-12 实测有效）:
  POST https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation
错误端点（勿用）:
  /compatible-mode/v1/images/generations  -> 404
  /api/v1/services/aigc/text2image/image-synthesis -> 400 InvalidParameter url error
关键坑（勿踩）:
  - api_key 在 cfg["dashscope"]["api_key"] 嵌套路径，顶层读取得空 key -> 401
  - 禁止 X-DashScope-Async: enable header -> 403（必须同步 POST）
  - read_file 工具输出对 sk- 脱敏，必须 Python open() 读原始字节
"""
import argparse
import base64
import json
import os
import sys
import urllib.request
import urllib.error

CFG = r"MEMOMICS_HOME/hermes_home/image_gen_config.json"
URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


def main():
    ap = argparse.ArgumentParser(description="DashScope qwen-image 文生图")
    ap.add_argument("prompt", help="图像描述 prompt")
    ap.add_argument("--size", default=None, help="默认读配置 (1024*1024)")
    ap.add_argument("--out", default=None, help="输出目录，默认 cwd/image_gen")
    args = ap.parse_args()

    with open(CFG, encoding="utf-8") as f:
        cfg = json.load(f)["dashscope"]
    api_key = cfg["api_key"]
    model = cfg.get("model", "qwen-image-3.0")
    size = args.size or cfg.get("size", "1024*1024")
    out_dir = args.out or os.path.join(os.getcwd(), "image_gen")
    os.makedirs(out_dir, exist_ok=True)

    payload = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": [{"text": args.prompt}]}]},
        "parameters": {"size": size, "n": 1},
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        sys.exit(f"HTTP {e.code}: {body[:800]}")

    choices = result.get("output", {}).get("choices", [])
    imgs = []
    for c in choices:
        content = c.get("message", {}).get("content", [])
        for m in content if isinstance(content, list) else [content]:
            if isinstance(m, dict) and m.get("image"):
                imgs.append(m["image"])
    if not imgs:
        sys.exit("no image in response: " + json.dumps(result, ensure_ascii=False)[:500])

    saved = []
    for i, url in enumerate(imgs):
        path = os.path.join(out_dir, f"image_{i+1}.png")
        if url.startswith("data:"):
            with open(path, "wb") as f:
                f.write(base64.b64decode(url.split(",", 1)[1]))
        else:
            urllib.request.urlretrieve(url, path)
        saved.append((path, os.path.getsize(path)))
    for path, nbytes in saved:
        print(f"SAVED {path} ({nbytes} bytes)")
    if not saved:
        sys.exit("no image saved")


if __name__ == "__main__":
    main()
