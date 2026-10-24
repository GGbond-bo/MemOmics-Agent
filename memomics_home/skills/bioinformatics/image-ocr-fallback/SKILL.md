---
name: image-ocr-fallback
description: >-
  从「读不了」的文档里取文字：上传的图片/截图、扫描版 PDF、旧版 Word 97-2003 二进制
  `.doc`（read_file 直接拒读）。图片/扫描页走 RapidOCR（rapidocr_onnxruntime，ONNX
  模型随 pip wheel 打包，零联网）；旧版 `.doc` 走 antiword；`.docx` 走 read_file。
  含整册扫描 PDF 的批量 OCR 循环（scripts/ocr_scanned_pdf.py）。
  🔴 含**读图三级降级链（模型无视觉时的兜底）**：⚠️ 2026-10-24 起 vision_describe v3
  自动选路——当前模型有视觉（deepseek-flash / kimi-k2.6 / MiniMax-M3 / gpt-4o / gemini /
  claude 等都算）就由模型直接实读，**不要再当纯文本环境处理**；确无视觉或 mode=model
  失败回退时才走 L1 `vision_describe` 本地像素事实 → L2 文本抽取（RapidOCR/antiword）→
  L3 多模态模型语义实读（DashScope `qwen3-vl-plus`，scripts/read_image_via_qwen_vl.py）。
  用户问"你能看懂这张图吗"时走 vision_describe（auto），不够再 L3，**不许回"我看不了"**。
  用于：用户上传图问"能识图吗"/"能看懂这张图吗"/"描述一下这张图"/"read this image"、
  PDF 抽文字返回空、用户给一批 学校/单位下发的 .doc 或扫描件原件要求整理标注。
category: General Utility
trigger:
  when:
    - User uploads image and asks "能识图吗" / "can you read this image" / "看看这个图"
    - 用户上传图问"你能看懂这张图吗" / "描述一下这张图" / "这张图是什么" / "describe this image"（要语义，不是要文字）
    - Current session model has no native vision（⚠️ 2026-10-24 更正：deepseek-flash / deepseek-v4 系实测有视觉，vision_describe v3 会自动用模型实读，勿再当纯文本例子）and the image has no text at all → 走 L1 vision_describe + L3 qwen3-vl-plus
    - PDF text extraction returns empty (scanned/image-based PDF)
    - Model lacks vision_analyze tool and has no native vision
    - read_file 报 "Cannot read binary file '...doc'"（旧版 .doc 原件）
    - 用户给一批下发的 .doc / 扫描版 PDF 原件，要求整理、标注、后续按格式产出
---

# Image OCR Fallback (No-Vision Models)

## When to Use

- User uploads a screenshot/table/figure-caption image and expects the text read back
- Current session model has no native vision（⚠️ 2026-10-24 更正：deepseek-v4-flash 实测有视觉；无视觉的例子是 deepseek-v3/r1 等老款）and no
  `vision_analyze` tool is exposed
- PDF is scanned/image-based → pymupdf text extraction returns empty

## 🚦 读图三级降级链（先判图，再选路 —— 别一上来就说"我读不了"）

本平台有**两条真实可用的读图通道**（不止 OCR）。用户问"你能看懂这张图吗 / 描述一下这张图"时，
按 L1 → L3 走，**不要回"我看不了，请找有视觉的模型"**：

| 层级 | 手段 | 拿到什么 | 适用 |
|:--:|---|---|---|
| **L1** | `tool_call vision_describe(image_path=<绝对路径>)` | **2026-10-24 v3 起自动选路**：当前模型有视觉 → 模型自己实读（返回语义理解）；无视觉/调用失败 → 纯本地像素管道（OCR 文本 + 主色/HSV + 柱状/坐标轴/网格检测 + ASCII 亮度图）。本地管道免费、不联网 | **任何图先跑这个**拿客观事实；要强制本地管道（机器判据/核验）用 `mode="local"`（等价手写探针：`scripts/image_pixel_probe.py`） |
| **L2** | `read_file`（`.docx`）/ RapidOCR（图片、扫描 PDF） | 逐字文本 + 坐标 + 置信度 | 文字类图：截图 / 表格 / PPT 页 / 扫描件 |
| **L3** | **多模态模型实读**：DashScope `qwen3-vl-plus`（见下节 + `scripts/read_image_via_qwen_vl.py`） | 语义：主体是什么、在做什么、风格、配色、背景、有无文字 | 需要"看懂"图：照片 / 插画 / 角色 / 场景 / 表情包；或 L1 只给出像素事实时 |

- **L1 的 OCR 为空 ≠ 图有问题**：纯图形图本来就没字 —— 这本身是一条证据（"图中无文字"由 L1 与 L3 双证）。
- **汇报口径（重要）**：L3 的语义描述必须**说明来源**（"由外部多模态模型 qwen3-vl-plus 读取"），
  纯文本模型没有视觉、不得声称"我看到了图片"（铁律 32）——但 2026-10-24 起 vision_describe
  mode=model 的返回**就是当前模型自己实读**，此时可以声称看到了图片。把 L1 像素事实与 L3 语义**互相印证**后再下结论，
  单靠 L3 一段话作答 = 单一来源。
- 出图/图表类图（UMAP / 箱线 / 热图）语义问题 → 先 L1，再按 `cns-visualization` 那一侧的口径看数据本身。

## Verified Pipeline (2026-07, Windows + miniconda3)

### 1. Install

```bash
# CRITICAL: pip may install to a different python than the one you run.
# On this machine: `pip` → D:\Python (3.13), system python → Python312,
# but the package landed in miniconda3. Use the interpreter that has it:
/e/miniconda3/python.exe -m pip install rapidocr_onnxruntime -q
```

### 2. Run

```bash
/e/miniconda3/python.exe -c "
from rapidocr_onnxruntime import RapidOCR
ocr = RapidOCR()
result, elapse = ocr('E:/path/to/image.png')
if result:
    for item in result:
        box, text, conf = item[0], item[1], item[2]
        x = int(box[0][0]); y = int(box[0][1])
        print(f'[{x},{y}] conf={conf} text={text}')
else:
    print('NO TEXT FOUND - 可能是纯图形图')
"
```

Pitfalls:
- `conf` is a **str** — do NOT `%.2f` format it (ValueError). Use `conf={conf}` or str().
- Locate uploaded files first: webui uploads live under
  `<安装目录>/webui/uploads/<timestamp>_<name>.png` — find with
  `find <安装目录> -name "<filename>"`.

## 整册扫描 PDF 批量 OCR（实测 2026-09，26 页 / 263 s）

先判有没有文字层——**有文字层就不要 OCR**：

```python
import pymupdf
d = pymupdf.open(src)
print(d.page_count, [len(d[i].get_text().strip()) for i in range(min(5, d.page_count))])
# 全 0 → 扫描版，走下面的循环
```

批量循环（脚本见 `scripts/ocr_scanned_pdf.py`，可直接 `exec(open(...).read())`）：

```python
import pymupdf
from rapidocr_onnxruntime import RapidOCR

doc, ocr = pymupdf.open(src), RapidOCR()
parts = []
for i, page in enumerate(doc):
    pix = page.get_pixmap(dpi=200)              # 200 dpi 足够；再高只增耗时
    res, _ = ocr(pix.tobytes("png"))
    parts.append(f"\n===== PAGE {i+1} =====\n" + "\n".join(r[1] for r in (res or [])))
    print(f"page {i+1}/{doc.page_count} chars={len(parts[-1])}", flush=True)   # 逐页报进度
open(out_txt, "w", encoding="utf-8").write("".join(parts))
```

要点：
- **逐页 print 进度**：整册 OCR 要几分钟，没有进度输出看起来像卡死（也方便外部判断是否还在跑）。
- 实测节拍 **≈10 s/页**（26 页 263 s），可按页数预估时间再决定同步还是后台。
- 结果先**落盘 txt**，再 `read_file` 分段读——不要把整册 OCR 文本灌进上下文。
- **表格/多栏页会 OCR 串行错位**：标准、规范、附件表这类内容 OCR 后**结构不可信**，
  可以看大意，**不能当权威表格引用**；涉及格式/数值细节回原件核对，或在交付物里注明"待核原件"。

## 旧版 `.doc`（Word 97-2003 二进制）→ antiword

`read_file` 对 `.doc` 报 `Cannot read binary file '...doc'` 是**预期行为**（不是文件损坏），别重试，
换 antiword（git-bash 自带，`/mingw64/bin/antiword`，免安装）：

```bash
for f in *.doc; do
  antiword -w 0 -m UTF-8.txt "$f" > "${f%.doc}.txt"
done
```

- **`-w 0` 必须加**：否则按 79 字符自动折行，中文正文被拦腰断行，读回来无法引用。
- **`-m UTF-8.txt`**：中文映射表，保证 UTF-8 输出。
- 表格用 `|` 分隔，**合并单元格会错位**（封面版式表的竖排文字被拆到每行左侧）——看结构可以，数值需核对原件。
- 断言"文件不存在"之前先 `ls` 目录：用户给的路径常带多余引号，或实际文件名与所说不一致；
  顺带能发现配套附件（封面格式/声明页/国标/名称表），一并抽取。

## 抽取之后：整理成「标注版」

用户说"整理出来，并做好标记"时，交付物不是原始 OCR 文本，而是**带标记的速查**：
适用对象（`【硕】/【博】/【通】`）、约束强度（`🔴硬性` / `⚪可选`）、来源条款号 + 章节骨架 + 自查清单。
学位论文/校内规范这类场景 → `cn-degree-thesis-writing` skill。

## L3 · 多模态模型语义读图（DashScope Qwen-VL，实测 2026-10 可用）

**平台自己就有 key，不要另配、不要问用户要 key**（`qwen-image-3.0` 图像生成用的是同一个 key）：

| 项 | 值 |
|---|---|
| Endpoint | `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`（OpenAI 兼容模式） |
| Key | `memomics_home/image_gen_config.json` → `dashscope.api_key`（备选：env `DASHSCOPE_API_KEY`） |
| **可用模型** | **`qwen3-vl-plus`** —— 目前唯一实测通过的 |
| 传图 | base64 **data URI**，`data:image/webp;base64,<...>`；**webp 可直接传，无需先转 png** |
| 脚本 | `scripts/read_image_via_qwen_vl.py` → `python scripts/read_image_via_qwen_vl.py <图片绝对路径>` |

**同一 key 下不可用的模型名（别在这上面反复试，一次失败就直接换 qwen3-vl-plus）**：

| 模型名 | 返回 |
|---|---|
| `qwen-vl-max` / `qwen-vl-max-latest` / `qwen-vl-plus` | 404 `model_not_found` |
| `qwen2.5-vl-7b-instruct` | 403 `access_denied` |
| `qwen-image-3.0` | 404 `model_not_supported`（图像生成模型不支持 OpenAI 兼容的 chat 模式） |

要点：

- **提示词写死两条约束**："只描述你确实看到的，不要联想或编造" + "有无文字（若有请逐字抄出）"——
  这是防止 L3 幻觉、也是让 L3 能与 L1 的"OCR 空"对账的关键。
- **key 只从 json 读、只 print 模型回复**：不要把 key 写进日志/回复/交付文件。
- **隐私闸门**：L3 会把原图发到外部 API。图里若是未发表数据、病人信息、涉密材料 → **先问用户能不能外发**，
  不能就只走 L1（本地像素事实）+ L2（本地 OCR）。
- 输出渲染：把 L3 回复整理成「文件 / 主体 / 结构或服装 / 背景 / 风格 / 配色 / 文字」表 + 关键过程 ≤3 行
  （写明 L1 与 L3 在哪几条结论上互证），再给 1-2 条后续可选项（局部放大、判定是否 AI 生成、写图注/英文说明）。

## Failure Chain (do not re-try these)

| Tool | Why it fails here | Verdict |
|------|-------------------|:---:|
| `pytesseract` | 依赖 tesseract 二进制且要配 PATH/语言包；本机实装在 `C:\Program Files\Tesseract-OCR\`（不在 PATH）——能用但不免配置，中文识别还需 chi_sim 语言包 | ⚠️ 需配置 |
| `easyocr` | First run downloads ~100MB detection model; on slow networks hangs at "Downloading detection model..." then times out (400s) | ❌ |
| PowerShell WinRT OCR (`Windows.Media.Ocr`) | Async WinRT interop from bash/PowerShell is flaky; GetAwaiter calls fail on COM objects | ❌ skip |
| **RapidOCR** (`rapidocr_onnxruntime`) | ONNX models **bundled inside the pip wheel** — zero network download, works offline | ✅ |

## Output Convention

Return OCR text as a readable block, with coordinates/confidence when useful.
If the image is a screenshot of previous chat content (user testing ability),
state what the image contains and confirm whether it matches expected content.

## Common Issues

| Error | Cause | Fix |
|-------|-------|-----|
| ModuleNotFoundError: easyocr/rapidocr | installed under different python | find via `pip show <pkg> \| grep Location`, use that interpreter |
| ValueError: Unknown format code 'f' | conf is str | `conf={conf}` not `conf={conf:.2f}` |
| easyocr hangs at model download | slow network, ~100MB model | don't wait — switch to RapidOCR |
| OCR returns nothing | pure-graphics image (chart/photo) —— **这不是故障** | 走 L1 `vision_describe`（或 `scripts/image_pixel_probe.py`）拿像素事实 → L3 `scripts/read_image_via_qwen_vl.py` 拿语义；"图中无文字"由 L1+L3 双证后再告知用户，别回"读不了" |
| 多模态模型 404 model_not_found / 403 access_denied | 换错模型名或该模型未开通 | 固定用 `qwen3-vl-plus`（见 L3 节） |

## 附带脚本（都在本 skill 的 scripts/ 下，直接执行）

| 脚本 | 作用 | 用法 |
|---|---|---|
| `scripts/image_pixel_probe.py` | **L1** 本地像素事实：主色板/HSV、饱和度亮度、纹理梯度、唯一色数、3×3 分区、ASCII 亮度图 | `python scripts/image_pixel_probe.py <图>` |
| `scripts/read_image_via_qwen_vl.py` | **L3** 多模态语义实读（DashScope `qwen3-vl-plus`，key 自动从 image_gen_config.json 读，不打印） | `python scripts/read_image_via_qwen_vl.py <图> [模型名]` |
| `scripts/ocr_scanned_pdf.py` | **L2** 整册扫描 PDF 批量 OCR | 见上文批量 OCR 节 |
