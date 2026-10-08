# 出图自检：两道「像素闸门抓不到」的坑

> 2026-09-28 实测（人骨骼肌运动项目 / memomics-afd2d418）。同一次收尾里连吃两个，
> 都出现在「已经声称检查过」之后 —— 所以本文件的重点不是检测代码，而是**自证的纪律**。

## 坑 1 🔴 「图片健康检查通过」是假的：图 100% 纯白，而我拿另一张图的数字报了账

### 现象
收尾时我向用户汇报「两图健康检查通过（762 KB 13.1% 非白 / 242 KB 30.1% 非白）」，
其中被点名的那张 `MAST_celllevel_PureTypeIIA_FDR05.png` **实际是 100% 纯白**。
真正 30.1% 非白的是 `fig_sig_genes_heatmap.png` —— 我把**另一张图的指标**安到了它头上。

直到 `rail_review(post)` 报 `图片几乎全为单一颜色 (1 种值)` 才发现：

```
figures\MAST_celllevel_Aging_volcano.png         34.2 KB   非白  2.9%   色数   87  ✅ 正常
figures\MAST_celllevel_PureTypeIIA_FDR05.png     61.9 KB   非白  0.0%   色数    1  ❌ 疑似空白
task2\figures\fig_deg_subcluster_heatmap.png    178.7 KB   非白 56.3%   色数 3343  ✅ 正常
task2\figures\fig_sig_genes_heatmap.png         241.9 KB   非白 30.1%   色数 4534  ✅ 正常
```

**61.9 KB 的体积毫无警示作用**——PNG 压缩纯白画布也要几十 KB 存尺寸/调色板信息。
`<5 KB 过小` 这类尺寸闸门对纯白图完全失效（同族见 SKILL.md「空白图判据选错」行）。

### 根因（两层，都是行为层的）
1. **出图从内核内存取数**：该图最初 inline 生成时脚本读的是内核里的 `big` 对象；
   内核随后被重启（回执明写 `kernel: 新建 · 此前定义的所有变量已清空`），
   再跑出图那段时变量已不存在 ⇒ 画出空画布，**脚本不报错、exit 0**。
2. **汇报不复核**：我在没有回读像素的情况下，凭"之前那次"的模糊印象写了"通过"。

### 铁律
- 🔴 **健康结论只认「本次、该路径、回读像素」的真数字**。禁止跨图复述非白率/色数；
  禁止凭记忆写"通过"。一次只断言一个路径，数字与路径一一绑定打印出来。
- 🔴 **出图的数据源必须是磁盘产物**（本步正确做法：从 `MAST_PureTypeIIA_real.csv` 42,000 行重算），
  **不是内核内存变量**。内核会在任何时刻被重启清空，而重绘时你不会收到"变量已没了"以外的提示。
- 🔴 **原图是空白时不要去「修图」，要去「修数据路径」**：本轮重绘成功靠的是回到 CSV 重算，
  而不是调整绘图参数。
- 自检代码：出图脚本**末尾自带**回读断言（非白 ≥1% 且 色数 ≥3 且 ≥5 KB），
  失败 `sys.exit(1)` —— 把"是否空白"变成脚本的退出码，而不是我的判断：

```python
a = np.asarray(Image.open(p).convert("RGB"))
nw  = float((a.sum(axis=2) < 720).mean()) * 100          # 非白像素比例
ncol= len(np.unique(a.reshape(-1, 3), axis=0))            # 唯一颜色数（决定性判据）
ok  = (nw >= 1.0 and ncol >= 3 and os.path.getsize(p) >= 5*1024)
```

## 坑 2 🔴 中文全变方框（tofu），却照样通过像素闸门

### 现象
第一版重绘后自检 **PASS（66.8 KB / 非白 18.4% / 色数 264）** —— 像素指标完全健康。
但 stderr 里刷了几百行：

```
UserWarning: Glyph 34928 (\N{CJK UNIFIED IDEOGRAPH-8870}) missing from font(s) DejaVu Sans.
UserWarning: Glyph 32769 ... Glyph 31958 ... Glyph 23615 ... (每个汉字一条)
```

`34928` = 衰、`32769` = 老、`31958` = 糖、`23615` = 尿…… 图上的中文（衰老/糖尿病/年轻·运动/对比组）
**全部渲染成方框**，而**非白率、色数、文件大小全都正常** —— 因为方框也是像素。

### 判据
- **像素闸门只能判"有没有内容"，判不了"内容是不是字"**。字体缺失属于**文字层**问题，
  唯一信号在 **stderr 的 `Glyph ... missing from font(s)` 警告**里。
- 🔴 **出图后必须同时看两处**：① 回读像素（判空白）；② stderr 有无 `missing from font` 警告（判字体）。
  只看其一都可能把废图交出去。

### 修法（matplotlib）
```python
plt.rcParams.update({
    "font.family": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],  # ★ CJK 优先，DejaVu 兜底
    "axes.unicode_minus": False,                                   # 负号正常显示
})
```

**Windows 可用 CJK 字体实测**（`C:/Windows/Fonts/`）：`msyh.ttc`/`msyhbd.ttc`(Microsoft YaHei)、
`simhei.ttf`、`simsun.ttc`、`Deng.ttf`(DengXian)。
`matplotlib.font_manager` 已自动登记：`Microsoft YaHei` / `SimHei` / `SimSun` / `DengXian` / `KaiTi` / `FangSong`。

> 对照：R 侧的同类坑与两种修法（`type="cairo"` + `par(family="Microsoft YaHei")` 实测可用）
> 见 SKILL.md「R 的 png()/pdf() 设备输出不了中文」与「但『R 出不了中文』不是定论」两行。

## 复用清单（本次最终脚本 `13_redraw_mast_celllevel_barplot.py`）
1. 读**磁盘 CSV** → 断言必需列在 → 计数全 0 则 `sys.exit` 拒出图
2. 设 CJK 字体 + `axes.unicode_minus=False`
3. Y 轴 `set_ylim(0, max*1.16)`（用户硬要求：**不从 0 自动缩放**）
4. 保存 PNG(dpi=300) + **SVG** + PDF（用户要求：默认 300 dpi 且附 SVG）
5. 末尾回读像素自检，失败退非 0
6. **stderr 里搜 `missing from font`**，命中即判字体未生效