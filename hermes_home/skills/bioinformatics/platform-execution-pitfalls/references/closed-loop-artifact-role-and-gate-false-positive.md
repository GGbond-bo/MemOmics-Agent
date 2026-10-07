# 闭环「看图找茬 → 修复 → 复看」：产物角色 与 rail_review 假阳性门禁

来源：2026-10-04 cli-anything Illustrator harness 闭环 B 实测（会话 memomics-486d1516），全程 `saved=false`，未碰用户文件。

## 为什么需要这份文件

闭环验证里 **第 1 轮的图往往"看起来是坏的"——因为它就是 bug 的物证**。
质量门禁（`rail_review(post)`）不知道测试意图，会把**刻意缺陷态对照图**判成"空白图/坏图，必须重新生成"。
按它重生成 → **摧毁 before/after 差分基线** → 闭环失去 0 基线，测试白做。

## 标准夹具：白底白字（最小可判「不可见」缺陷）

```
new-doc 800x600
text-add --content "看不见的文字" --x 60 --y 120 --size 48 --color "#ffffff"   # 白字
rect     --x 60 --y 360 --w 680 --h 160 --color "#333333"                      # 深灰块：证明画布确实有内容
export   loop_B_v1.png -f png --bg white                                        # 2419 B
```

关键：**对象真实存在，但对比度为零**。`--json items` 能查到
`textframes[0] = {contents:"看不见的文字", size:48, bounds:[60,511.68,348,457.25], fill:"#ffffff"}`，
所以"看不见"不是导出失败，是渲染对比度问题 —— 这正是要验证 agent 能否**通过看图**发现它。

## 三源交叉验证（修复必须由"看图"证据确认，缺一不可）

| 证据源 | before（#ffffff 字） | after（#111111 字） |
|---|---|---|
| `vision_describe` OCR | 无文本条目 | **「看不见的文字」@(60,86) 置信=1.0** |
| ASCII 亮度图 | 文字区均匀无字形 | y≈94–130 行出现字形笔画 |
| **PIL 像素审计**（最硬，不依赖 OCR） | `dark_px(<100)=0 / 17280 = 0.00%` | `dark_px=1475 / 17280 = 8.54%` |
| 文件字节（旁证） | 2419 B | 6393 B（+164%，与文字由不可见→可见一致） |

第三源依赖最少 → 直接用 `scripts/loop_artifact_audit.py`。

### ⚠️ OCR 校准（重要，别误判成"工具坏了"）
第 1 轮 `vision_describe` 返回「OCR 文本: 无（OCR 引擎不可用）」，第 2 轮同一条链路却读出文字（置信 1.0）。
→ **"引擎不可用"的真实成因常常是图内确实无字可读**（低对比/空白/无字形）。
不要据此下"OCR 不可用"的结论；**全文以像素/字节为准，OCR 只作辅助**。

## 坐标换算（别把两套坐标混读）

Most 图形软件 `bounds` 是原生坐标（y 向上、原点左下），导出 PNG 是屏幕坐标（y 向下、原点左上）：

```
screen_y_top = artboard_height - bounds[1]    # bounds[1] = 对象上边 y_ai
screen_y_bot = artboard_height - bounds[3]    # bounds[3] = 对象下边 y_ai
PIL box      = (x0, screen_y_top - pad, x1, screen_y_bot + pad)    # pad≈5
```

实测：`bounds=[60,511.68,348,457.25]`, height=600 → 理论 box `(60, 83.3, 348, 147.8)` → 实取 `(60,86,348,146)` = 17280 px。
**框是否对准的自检**：after 图 dark_px 显著 >0，且 vision OCR 报出的 bbox 左上角 ≈ box 左上角（实测 OCR@(60,86)）。
若两图 dark_px 都 ≈0 或都 ≈平滑值 → 框没对准，先修框再下结论。

## 假阳性门禁：`rail_review(post)` 实际返回与正确处置

```
passed=false
issues:   ["图片太小 (2419B): loop_B_v1.png — 可能是空白图或错误图，必须重新生成"]
warnings: ["No result files found in output directory"]
figure_count: 2
```

逐条核实：
- 「2419B = 空白/错误图」→ **不成立**：`Image.open(p).verify()` = OK、800×600、sha256 可校验、主色含 `#202020 21.7%`（非全空）。
- 「No result files found」→ **与 `ls` 实测矛盾**（两 PNG 都在 output 目录）。不能当独立失败依据。

### ✅ 正确处理（禁止重生成）
1. **冻结** before 原图，不覆盖、不重生成；
2. 补 `artifact_manifest.json`（schema 见下），把角色写清楚；
3. 如实汇报「门禁口径不匹配（阈值判据面向交付图，缺 artifact_role 维度）」，**不补假产物、不硬凑**；
4. 必要时 `debate_analysis` 复核 —— 实测裁决 `modify` / 置信 medium：
   `gate_fit=3`、`false_positive_cost=3`（判据适配性差）、`evidence_chain=8`、`non_destructive=8`（证据链与纪律达标）。

### ❌ 禁止
- ❌ 为让审查变绿覆盖缺陷物证（摧毁 before/after 差分）；
- ❌ 把 failed 直接当"图像真损坏"的结论交给用户；
- ❌ 因门禁红了反复重跑同一张图（触发系统循环检测强制干预）。

## artifact_manifest.json schema（实测落盘样例）

```json
{
  "test": "closed_loop_B (see-bug -> fix -> re-verify)",
  "tool": "cli-anything-illustrator harness (COM->ExtendScript)",
  "doc_saved": false,
  "artifacts": [
    {"file":"loop_B_v1.png","role":"before_negative_control","expected_blank":true,
     "bytes":2419,"size":[800,600],"png_verify":"OK",
     "sha256":"27826fba…e94a","text_region_dark_px":0,"text_region_px":17280,"dark_ratio":0.0,
     "note":"#ffffff text on #ffffff bg -> intentionally invisible (bug evidence, DO NOT regenerate)"},
    {"file":"loop_B_v2.png","role":"after_deliverable","expected_blank":false,
     "bytes":6393,"size":[800,600],"png_verify":"OK",
     "sha256":"e170125a…de31","text_region_dark_px":1475,"text_region_px":17280,"dark_ratio":0.0854,
     "note":"recolor text -> #111111, OCR reads 看不见的文字 @(60,86) conf=1.0"}
  ]
}
```

**role 约定**：`before_negative_control`（缺陷物证，禁重生成） / `after_deliverable`（按交付标准审）。

## 收尾验收（不碰用户资产的硬证据）

```
saved=false                    # 每条命令 JSON 里都有
close-untitled                 # docs_before=1, closed=["未标题-1"], docs_after=0
doctor                         # bridge=true, doc_count=0, active_doc=null
```

## 可复用判据建议（写门禁/复核时）

- 体积阈值（如 `<5KB = 疑似空白`）**只对 role=deliverable/after 生效**；before 对照走 `warning + 像素审计`。
- 判空白不能只看体积：要 `PNG verify` + 尺寸 + 全图非背景像素占比 + **期望空白区域的 dark_px 比例**。
- 产物收集用 manifest / 声明的输出目录，避免 "No result files" 这类路径口径假警告。
- 推荐策略：`apply_size_fail_to_roles=[deliverable, after]`；`before_control_action=warning_plus_pixel_audit`。