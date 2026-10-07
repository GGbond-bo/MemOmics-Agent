# 多轮闭环验收：实测记录与判定口径（Illustrator COM harness，2026-10-04）

用 Illustrator COM→JSX 桥（或任何 agent-native CLI harness）跑 3 轮
「画 → 导出 → 看图 → 调整 → 再看图」的完整留痕。
用途：① 复现这套闭环；② 直接复用判定口径与"结论强度分级"；③ 避免重踩 top-N 调色板坑。

命令通道：`cli-anything-illustrator.exe`（`--json` 必须在子命令**之前**）。
纪律：全程不保存任何文档、不碰用户文件、产物只写 `results/<sid>/ai_loop_A/`。

---

## 1. 复现命令（逐轮，勿用 `&&` 串成一条）

```bash
AI=<repo>/.venv/Scripts/cli-anything-illustrator.exe
OUT=<repo>/results/<sid>/ai_loop_A

# 第1轮（画）
$AI --json new-doc --width 800 --height 600
$AI --json rect --x 60 --y 60 --w 300 --h 180 --color "#e04040"
$AI --json text-add --content "闭环测试 第1轮" --x 70 --y 300 --size 40
$AI --json export "$OUT/loop_A_r1.png" -f png --bg white

# 第2轮（调整：改色 + 改字号）
$AI --json recolor --color "#00aa55" --index 0
$AI --json text-set --size 60
$AI --json export "$OUT/loop_A_r2.png" -f png --bg white

# 第3轮（调整：位移 + 新增元素）
$AI --json move --index 0 --dx 200 --dy 120
$AI --json text-add --content "第3轮新增：看图后调整" --x 260 --y 420 --size 28 --color "#0044cc"
$AI --json export "$OUT/loop_A_r3.png" -f png --bg white

# 收尾三件套
$AI --json close-untitled      # docs_before=1 → closed=["未标题-1"] → docs_after=0
$AI --json doctor              # bridge=true, doc_count=0, active_doc=null
ls -la "$OUT"; sha256sum "$OUT"/*.png
```

## 2. 每轮实际返回（关键字段）

| 轮 | 命令 | 关键字段 | PNG 字节 / sha256[:16] |
|:--:|------|----------|------------------------|
| 1 | new-doc | `created=true doc_count=1 active_doc=未标题-1 artboard_rect=[0,600,800,0]` | 6845 / `4e52401e927abc55` |
| 1 | rect | `pathitems=1 bounds=[60,540,360,360] fill=#e04040 saved=false` | |
| 1 | text-add | `textframes=1 contents=闭环测试 第1轮 size=40 error=null`（中文回显正常） | |
| 1 | export | `exists=true bytes=6845` | |
| 2 | recolor | `changed=1 total=1 fill=#00aa55` | 9151 / `f4930023d968ba46` |
| 2 | text-set | `changed=1 skipped=0 size=60` | |
| 3 | move | `ok=true bounds=[260,420,560,240] error=null` | 15454 / `0561a55e6bc5f3d2` |
| 3 | text-add | `textframes=2 fill=#0044cc size=28 error=null` | |

> `saved` 字段在 new-doc 时为 `true`（新建未标题文档本身无未存改动），其余为 `false`；
> 判"有没有落文档"要**看磁盘**，不看这个字段。

## 3. 三层证据链（缺一层就会被质疑）

| 层 | 证据 | 说明 |
|----|------|------|
| ① 命令层 | `--json` 关键字段 | `changed/ok/index/total/bounds/fill/textframes/error` |
| ② 产物层 | 导出文件路径 + 字节数 + sha256 + 目录清单 | 字节数变化必须能解释（如字号 40→60 → PNG 变大 6845→9151） |
| ③ 像素层 | `vision_describe`（OCR 文本+置信+bbox）＋ **PIL 精确色复核** | 主色榜只作**辅助** |

## 4. 看图结论（本轮实测）

| 轮 | OCR（置信） | 视觉管道主色榜 | 像素级精确色复核 |
|:--:|-------------|----------------|------------------|
| 1 | `"闭环测试第1轮" @(75,276) 1.0` | `#e04040 9.3%`（含红 ✅） | `#e04040` exact 53044 (11.051%) |
| 2 | `"闭环测试第1轮" @(77,260) 1.0`（字框随 40→60 变宽、位置略上移） | `#00a040 10.6%`（红消失 ✅） | `#00aa55` exact 53044；红 exact **0** |
| 3 | 2 段：`"闭环测试第1轮" @(77,260)`、`"第3轮新增：看图后调整" @(262,407)` 均 1.0 ✅ | `#00a040 9.1% / #008040 0.9%` —— **蓝未进 top5** ⚠️ | 绿 `#00aa55` exact 50292 (10.477%)；**蓝 `#0044cc` exact 283 (0.059%)**，同族抗锯齿边色 `#7fa1e5 533 / #bfd0f2 381 / #4073d9 234`，bbox `x261-551 y407-432` 与 `--x 260 --y 420` 吻合 ✅ |

**两个坑（详见 SKILL.md Common Issues）**
1. top-N 主色榜**按面积**截断 → 0.435% 的细笔画被挤出 → 不能当作"缺色"。
2. 管道报的 `#00a040` 是**量化合并簇**，文档精确色是 `#00aa55` → 精确色结论必须从 PNG 像素取。

## 5. 坐标系实测
`rect --x/--y` = 距画板左/上；返回的 `bounds` 是**文档坐标（y 向上）**。
`move --dx 200 --dy 120`（`--help` 写 dy positive = DOWN）→ bounds `[60,540,360,360]` → `[260,420,560,240]`，即 y 值**减小** 120。
**别按屏幕 y 向下误读 dx/dy 符号**；对账时用 `bounds` 差值逐项核对。

## 6. 本轮 L2 辩论裁决（scenario=code_engineering，裁判=自动化测试架构师）

- **verdict = `modify`，confidence = medium**
- `decision`：先按"像素级**存在性**谓词"通过第3轮含绿+蓝；把"top5 未列蓝"降级为**管道口径待解释项**；若验收条款硬性规定"主色 = top5 面积榜"，则第3轮按该字面口径**不通过**。
- `recommended_params`（可直接复用为验收谓词）：
  ```json
  {"acceptance_predicate": "round3_has_green && round3_has_blue",
   "green_presence": {"core_color_family": "#00aa55", "min_px": 10000, "min_pct": 5},
   "blue_presence":  {"core_color": "#0044cc", "deltaE_max": 2, "min_px": 1000, "min_pct": 0.3, "bbox_tolerance_px": 5},
   "top5_policy": "top5 仅作高频色辅助；未列蓝不得单独判定缺蓝",
   "determinism_repeat": {"smoke_n": 10, "confirm_n": 29, "require_same_png_sha256": true}}
  ```
  > ⚠️ `min_pct 0.3` 实测偏严（蓝只有 0.059%），实操按 `min_px >= 200` 放宽：**`min_px` 比 `min_pct` 稳**。
- rubrics：`evidence_chain_integrity 7`（命令 JSON / PNG 字节 / OCR / bbox / 磁盘清单互相印证）／`determinism_reproducibility 3`／`failure_mode_coverage 3` —— 低分两项是本轮**已知短板**。
- `missing`（下次补齐才算完整）：top5 算法参数原文；"主色"条款定义；PNG ICC/色彩管理；N=10/N=29 重复运行矩阵；COM 临时文件/剪贴板残留审计；坐标契约（负坐标/旋转/缩放）；人眼或视觉模型复核。

## 7. 结论强度分级（写结论时照抄）

| 级别 | 证据 | 能说的话 |
|------|------|----------|
| smoke | 单次多轮闭环全绿 + 收尾三件套 | "这条路径这几次没失败；**不是**统计确定性" |
| 确认 | 固定版本/字体/颜色配置 + N=10 冒烟 + N=29 确认 + PNG sha256 稳定 | 才可称确定性；N=29 零失败约支持失败率 <10% |