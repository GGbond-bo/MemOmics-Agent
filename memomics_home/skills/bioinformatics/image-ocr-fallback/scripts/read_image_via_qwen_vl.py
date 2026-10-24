# -*- coding: utf-8 -*-
"""L3 · 多模态模型语义读图（DashScope OpenAI 兼容模式）。

为什么需要：纯文本模型（deepseek-v3/r1 等老款）没有视觉时，vision_describe 只能给像素事实，
拿"这张图是什么/在做什么"必须调外部多模态模型。
（⚠️ 2026-10-24 更正：deepseek-flash 实测有视觉——vision_describe v3 会自动用当前模型实读，
本脚本只在「当前模型确无视觉」时仍是兜底。）

实测（2026-10）：
  可用   ：qwen3-vl-plus
  不可用 ：qwen-vl-max / qwen-vl-max-latest / qwen-vl-plus  -> 404 model_not_found
           qwen2.5-vl-7b-instruct                         -> 403 access_denied
           qwen-image-3.0                                 -> 404 model_not_supported
  → 一次失败就换 qwen3-vl-plus，不要在模型名上反复试。

用法：
  python read_image_via_qwen_vl.py <图片绝对路径> [模型名]
  # 例：python read_image_via_qwen_vl.py "C:/Users/x/Pictures/a.webp"

前一张图请先跑 vision_describe（或 image_pixel_probe.py）拿像素事实，
再把两边结论对账（尤其"有无文字"）后才向用户下结论。
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_MODEL = "qwen3-vl-plus"
ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# key 来源：项目内 image_gen_config.json（平台自带，与图像生成共用）→ env 兜底
KEY_CANDIDATES = [
    r"<安装目录>/memomics_home/image_gen_config.json",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "memomics_home", "image_gen_config.json"),
]

PROMPT = ("请客观描述这张图片：画面主体是什么（物体/人物/动物/场景）、在做什么、"
          "风格（照片/插画/卡通/截图/表情包/3D渲染）、配色与背景、"
          "有无文字（若有请逐字抄出）。只描述你确实看到的，不要联想或编造。")


def load_key():
    for p in KEY_CANDIDATES:
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8"))["dashscope"]["api_key"]
            except Exception:
                pass
    k = os.environ.get("DASHSCOPE_API_KEY")
    if k:
        return k
    sys.exit("[ERROR] 找不到 dashscope key（查过 image_gen_config.json 与 DASHSCOPE_API_KEY）")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    img = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL
    if not os.path.exists(img):
        sys.exit(f"[ERROR] 图片不存在: {img}")

    ext = (os.path.splitext(img)[1].lstrip(".") or "png").lower()
    if ext == "jpg":
        ext = "jpeg"
    b64 = base64.b64encode(open(img, "rb").read()).decode()

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{b64}"}},
            {"type": "text", "text": PROMPT},
        ]}],
        "max_tokens": 900,
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {load_key()}",   # 永不打印 key
                 "Content-Type": "application/json"},
    )
    try:
        r = json.load(urllib.request.urlopen(req, timeout=120))
        print(f"[MODEL] {model}")
        print(r["choices"][0]["message"]["content"])
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            code = json.loads(body).get("error", {}).get("code")
        except Exception:
            code = "?"
        print(f"[HTTP {e.code}] code={code} {body[:400]}")
        print("提示：404 model_not_found → 换 qwen3-vl-plus；403 access_denied → 该模型未开通，换 qwen3-vl-plus")
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()