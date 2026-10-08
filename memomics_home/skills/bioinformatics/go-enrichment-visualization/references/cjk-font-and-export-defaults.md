# 中文标签渲染 + 出图导出默认（本用户项目）

## 1. 中文标签变方框 — 静默失败，必须主动挂字体

**症状**：图能生成、文件非空、没有报错，但所有中文变成豆腐块/空白。
matplotlib 默认 `DejaVu Sans` **不含 CJK**；R base graphics / ggplot 同理会挑到无中文字形的设备字体。

**为什么危险**：纯文本模型看不到图，**这个 bug 对 agent 是隐形的** ——
`os.path.getsize` 正常、`fig.savefig` 正常，只有用户打开才看到方框。
唯一可靠的判据是 `savefig` 时抛出 `UserWarning: Glyph ... missing from font(s) DejaVu Sans`
（warning 容易被 `2>&1 | grep -v warn` 顺手过滤掉 → 先裸跑一次看警告）。

**修法（Python / matplotlib，Windows）**：
```python
from matplotlib import font_manager
_cjk = sorted(set(f.name for f in font_manager.fontManager.ttflist
                  if any(k in f.name for k in ("YaHei", "SimHei", "SimSun", "Noto Sans CJK"))),
              key=lambda n: ("YaHei" not in n, "SimHei" not in n, n))
plt.rcParams["font.sans-serif"] = _cjk + ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False        # 负号也跟着变，别漏
print("CJK 字体:", _cjk or "⚠️ 未找到，中文会变方框")   # 自证
```
- 本机可用：`Microsoft YaHei` / `SimHei` / `SimSun` / `MS Gothic`（实测列出即有效）。
- 字号不变，文件大小会明显变大（实测 353 KB → 423 KB）——这是中文真的渲染出来的旁证。
- 纯英文/数字图仍建议显式走 Arial/Helvetica（期刊要求），只在含中文时挂 CJK 列表。

**交付前自检（必做）**：用本地读图工具核验，确认中文正常、不是方框；
判据以 OCR 文本为准（标题/轴标签/图例都能读出中文 = 正常）。

**⚠️ 不要为了"字体统一"擅自安装字体**。R 侧若系统无 DejaVu Sans（matplotlib 自带、
系统并不装），不要 `install` —— 改为在交付说明中声明字体族差异，由用户决定。

## 2. 导出默认（本用户长期要求，不必每轮再问）

- **@300 dpi**，且**每张图都要附 SVG**（矢量版）；不要再出 150 dpi。
- 常用组合：`png`（预览）+ `svg`（矢量）两者都给；投稿场景再加 `pdf`/`tiff`。
- 一键多变体：
  ```python
  for ext in ("png", "svg"):
      fig.savefig(f"{stem}.{ext}", dpi=300, bbox_inches="tight", facecolor="white")
  ```

## 3. 数据整理步骤也要配图（平台审查会卡）

`rail_review(post)` 会检查"每步至少 1 张图"，**纯表格重建/数据清洗步骤没有图会被判不通过**，
即使产物完全正确。

**对策**：把"数据质量核查图"作为该类步骤的标配产物——它本身也是交付价值：
- 表重建 → 完整性对照图（源表 vs 派生表逐项对照，标出被截断/丢失的项）。
- 清洗前后 → 丢失条目条形图 + 计数标注。

这样既过审查，又让用户一眼看到数据有没有被暗改，不用靠 agent 口头保证。
