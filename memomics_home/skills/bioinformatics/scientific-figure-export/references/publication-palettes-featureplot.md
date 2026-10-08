# 发表级配色速查：FeaturePlot 连续型 score（Nature 级三套）

> 来源：2026-09-21 会话——用户把 `cols = c("lightyellow","darkblue")` 拿来找「专业好看、Nature 级别」的替代
> 场景：`FeaturePlot` / `sc.pl.umap(color=)` 这类**连续型数值上色**（score、module score、表达量）

## 1. 三套配色锚点（可直接粘进 `cols=`）

Seurat `FeaturePlot(cols=)` 接受**任意长度**的颜色向量并自动插值 ⇒ 给 5 个锚点即等价于 100 级连续色阶。
下列 hex 由 `colorRampPalette(..., bias=1)(100)` 取 0/25/50/75/100% 位置**程序化算出**（不是手抄色卡）：

| 方案 | 锚点 hex（低 → 高） | 定位 |
|---|---|---|
| **A · viridis** | `#440154`, `#3a528a`, `#238f8c`, `#5ec762`, `#fde725` | 感知均匀 + 色盲友好，**投稿首选安全牌**；灰度打印下同样分得开 |
| **B · Blues** | `#deebf7`, `#a7cee4`, `#58a1cf`, `#1b6aaf`, `#08306b` | 浅灰→深蓝，最干净的发表级单色阶，低背景干扰 |
| **C · YlOrRd** | `#ffeda0`, `#febb56`, `#fd7034`, `#da141e`, `#800026` | 黄→橙→红，「高值 = 发热」直觉感强 |

**选型**：Nature/Cell 系投稿优先 A（色盲 + 灰度双友好）；要强调「高表达」的直觉用 C；B 用于与其它彩色图共存、不希望抢视觉的场合。

⚠️ **`c("lightyellow","darkblue")` 不要再用**——两端色相距过远、中点经过灰暗区，中间表达量的细胞看着像「没染上」。

## 2. 极简代码（用户偏好：只给核心逻辑，<20 行）

```r
p1 <- FeaturePlot(seurat_obj, features = "Type_IIA_score",
                  cols = c("#440154", "#3a528a", "#238f8c", "#5ec762", "#fde725"),
                  pt.size = 0.5, order = TRUE) +
      ggtitle("Type IIA score") +
      theme(plot.title = element_text(hjust = 0.5, size = 18))
```

## 2b. 🔴 图例要改就先看这条：`cols=` 本身已是 min→max，**不要再叠 `scale_*_gradientn()`**（2026-09-21 实测）

Seurat v5 的 `FeaturePlot` 返回 **patchwork**，且**内部把 feature 重缩放到 `1~2`**（自带 colour scale `Limits: 1 -- 2`）。
若叠一层 `scale_colour_gradientn(limits = range(obj$score))`（如 `0~0.974`）→ 数据全部落在界外 →
默认 `oob = censor` 全变 **NA** → `na.value` 默认 **`grey50`** → **整图黑白灰**；把 `oob` 改 `squish` 则全压到端点 → **单色图**。
（本次实测：用户照此写法拿到黑白图后当场发火；诊断 `head(ggplot_build(p[[1]])$data[[1]]$colour)` = `grey50`。）

要改图例文字，只改**内层** scale（ggplot2 scale 是 R6 引用语义，原地改立即生效）：

```r
p  <- FeaturePlot(obj, features = "scoreI_AUC",
                  cols = c("#440154","#3a528a","#238f8c","#5ec762","#fde725"),
                  pt.size = 0.5, order = TRUE) + ggtitle("Type I score")
sc <- p[[1]]$scales$get_scales("colour")     # ⛔ 不要用 p + scale_*_gradientn(...)
sc$breaks <- sc$limits                       # 只标两端 = breaks 给两个值
sc$labels <- c("Min", "Max")                 # 或 sprintf("%.3f", range(obj$score, na.rm=TRUE))
sc$name   <- "Score"
```

**交付前实跑 + 像素验证**：PIL 取非背景像素主色，应为锚点两端 hex（如 `#fde725` + `#440154`）；
**主色出现 `#7f7f7f`(grey50) 或单一色 = 失败**（实测失败图 `#7f7f7f n=64,297`）。
完整根因/探针/被否决的过度工程清单 → `celltype-proportion-comparison` → `references/featureplot-score-color-scale.md` §0。

## 3. 配色包探测与回退

脚本内用 `tryCatch(library(p), error=...)` **真加载**探测（`requireNamespace` 只查描述不加载 DLL，是坏包假象来源）。
2026-09-21 实测 `viridis=FALSE scico=FALSE`（未装）、`RColorBrewer=TRUE` ⇒ 走内置 hex 向量回退。
**不必为此提示用户装包**（铁律 29：装包需用户同意）——锚点 hex 硬编码进脚本即可，效果与装包一致。

## 4. 出图加速（本会话教训：用户问「为什么这么久？」）

实测：脚本 15:39:59 落盘 → 4 张图 15:40:10 写完，**运算只有 11 秒**。延迟来自别处：

| 慢在哪 | 实测 | 处置 |
|---|---|---|
| **R 内核冷启动** | 日志 `[kernel: 新建 · 此前定义的所有变量已清空]` ⇒ 必须重新 `library(Seurat)`，Windows 首次加载 20–40 s | 配色图**不需要 Seurat**，只 `library(ggplot2)`；更不要为配色演示去 `readRDS` 一个 528MB 对象 |
| **拆成多轮调用** | 探测包 → 算 hex → 出色卡 → 出 3 张演示图 = 4 轮往返 | 🔴 **一次 `execute_r` 做完**：探测 + 算 hex + 出色卡 + 出全部图 + `cat()` 打印全部结论 |

**判据：凡「探测→计算→出图」这类无人工判断介入的流水线，写成一个脚本一次跑完**（详见 `platform-execution-pitfalls` 同名条目）。

## 5. 产出物命名（复用）

```
figures/palette_card_featureplot.png   # 三套色带对比色卡
figures/demo_palette_A_viridis.png     # 上色演示（模拟点云）
figures/demo_palette_B_blues.png
figures/demo_palette_C_ylorrd.png
scripts/featureplot_nature_palettes.R  # 可复用脚本
```

⚠️ 演示图必须向用户**明确标注是模拟点云**（非真实分析结果），不得把配色演示图当真实结论交付。