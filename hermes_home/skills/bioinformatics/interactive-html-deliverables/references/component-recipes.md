# 组件配方：浅色交互展示页（全部实测通过，2026-09-16）

来源：MemOmics 自我展示页（`results/memomics-a74bc2ed/reports/MemOmics_Showcase.html`，12 章节 / 14 类交互 / 115 KB / 单文件）。
直接照抄修改即可，不要从零写。

---

## 0. 分段落盘 + 拼接

```
reports/parts/p1_head.html          # <!DOCTYPE> + <head> + <style> 的前 2/3（⚠️ 不写 </style>）
reports/parts/p2_css2.html          # 余下 CSS + </style></head><body> + 导航栏
reports/parts/p3..p8_*.html         # 各章节（每段 10–17 KB）
reports/parts/p9_script.html        # <script> 全部 JS + </body></html>
```
```python
parts = ["p1_head.html","p2_css2.html", ... ,"p9_script.html"]
html = "".join(open(os.path.join(base,"parts",p), encoding="utf-8").read()+"\n" for p in parts)
open(os.path.join(base,"Showcase.html"),"w",encoding="utf-8").write(html)
# 自检
assert html.count("<style") == 1 and html.count("</style>") == 1
assert html.count("<div") == html.count("</div>")
```
> ⚠️ 分段只是为了绕开单次输出长度上限。**`</style>` 全文件只能一个**——第 1 段闭合掉，第 2 段 CSS 会变成页面正文。

---

## 1. 浅色设计令牌

```css
:root{
  --bg:#f5f8fd; --bg-soft:#eef3fb; --card:#ffffff; --card-2:#fbfdff;
  --ink:#0d1b2e; --ink-2:#33455e; --muted:#6b7f99; --line:#e2eaf5; --line-2:#d3e0f0;
  --brand:#1f6feb; --brand-d:#1550b0; --cyan:#0ea5b7; --violet:#7b4dfa; --amber:#f59e0b;
  --green:#10b981; --rose:#f43f5e;
  --grad:linear-gradient(115deg,#1f6feb 0%,#0ea5b7 55%,#7b4dfa 100%);
  --grad-soft:linear-gradient(135deg,rgba(31,111,235,.10),rgba(14,165,183,.08) 50%,rgba(123,77,250,.10));
  --sh-s:0 1px 2px rgba(13,27,46,.05),0 2px 8px rgba(13,27,46,.05);
  --sh-m:0 6px 22px rgba(19,44,84,.09),0 2px 6px rgba(19,44,84,.05);
  --sh-l:0 22px 60px rgba(19,44,84,.14),0 6px 18px rgba(19,44,84,.07);
  --mono:"JetBrains Mono",Consolas,monospace;
  --sans:"Inter","HarmonyOS Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
}
html[data-theme="dark"]{ --bg:#0b1424; --card:#121f34; --ink:#eaf2ff; --ink-2:#c3d3e8;
  --muted:#8aa0bd; --line:#22344f; --line-2:#2b405e; }
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;scroll-padding-top:88px}
body{font-family:var(--sans);color:var(--ink);background:var(--bg);line-height:1.75}
/* 未来感网格底纹（顶部渐隐） */
body::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.55;
  background-image:linear-gradient(rgba(31,111,235,.045) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(31,111,235,.045) 1px,transparent 1px);
  background-size:46px 46px;
  -webkit-mask-image:radial-gradient(ellipse 90% 60% at 50% 0%,#000 20%,transparent 78%);
          mask-image:radial-gradient(ellipse 90% 60% at 50% 0%,#000 20%,transparent 78%);}
.wrap{position:relative;z-index:1;max-width:1180px;margin:0 auto;padding:0 26px}
section{padding:74px 0 18px}
```

---

## 2. 组件配方（逐个可复制）

| 组件 | 关键实现 | 交互钩子 |
|------|---------|---------|
| **顶部导航 + 进度条** | `#nav{position:fixed;backdrop-filter:blur(14px)}`；`#progress{height:3px;width:0;background:var(--grad)}` | scroll 事件改 `width`；`IntersectionObserver{rootMargin:"-45% 0px -50% 0px"}` 高亮当前章 |
| **数字滚动** | `<div class="v" data-to="434">0</div>` | `IntersectionObserver{threshold:.6}` + `requestAnimationFrame` 三次缓入，`toLocaleString()` |
| **标签页** | `.tabpane{display:none}` / `.tabpane.on{display:block;animation:fade .3s}` | `[data-tabs]` 容器内点 `.tab` → 切同级 `.tabpane` 的 `.on` |
| **分层/步骤点击** | 左列表 + 右侧 sticky 详情面板（`.detail{position:sticky;top:88px}`） | 点 `.layer[data-d]` → 只显示 `#detail .pane#<id>` |
| **卡片展开** | `.mech .more{max-height:0;overflow:hidden;transition:max-height .4s}` / `.mech.on .more{max-height:520px}` | 点卡片 toggle `.on` + 改按钮文案 |
| **辩论逐步揭示** | 8 个 `.drole{opacity:.28}` → `.show` | 点击后按 `order=[0,4,1,5,2,6,7,3]` 正反交替 `setTimeout(…, 420*(k+1))`，最后 `setTimeout(…,550)` 显示裁决块 |
| **类目筛选** | `.agent.hide{display:none}` | 按 `data-cat` 匹配显示/隐藏，并显示计数 |
| **表格排序** | `th[data-sort]` 可点，`.hi` 类高亮本家列 | 取 `td[ci].textContent`，数字用 `parseFloat(x.replace(/[^\d.\-]/g,""))` 否则 `localeCompare(…,"zh")` |
| **canvas 条形图** | 见 §3 | `createLinearGradient` 主色渐变；数值右标 |
| **canvas 环形图** | `arc(cx,cy,R,a0,a1)` + 反向 `arc(cx,cy,r0,a1,a0,true)` 挖空 | 中心放大号总数 |
| **canvas 雷达图** | 5 圈网格 + 轴线 + 每序列 `fill(alpha .13)` + 描边 + 点 | 径向轴标签按 `Math.cos(a)` 决定对齐方向 |
| **Hero 粒子网络** | `<canvas id="fx">` 绝对定位铺满 hero | `N=clamp(W*H/16000,38,96)`；距离 <118 连线的透明度按距离衰减；鼠标半径 150 内节点反向轻推 + 放大发光 |
| **演讲者模式** | `.speaker{display:none}` / `body.speak .speaker{display:block}` | 按钮或 `S` 键切换 `body.speak` |
| **主题切换** | `html[data-theme="dark"]` 覆盖令牌 | 切换后**必须重绘 canvas**（`drawAll()`），因为 canvas 颜色取自 CSS 变量 |
| **键盘快捷键** | `←/→` 章节跳转、`S` 讲稿、`D` 深浅色 | 用 `getBoundingClientRect().top > -innerHeight*.5` 定位当前章 |

**读取 CSS 变量给 canvas 用**：
```js
const C = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
x.fillStyle = C("--ink-2");
```

---

## 3. canvas 三个必守点

```css
canvas{width:100%;display:block}   /* ⚠️ 写 max-width:100% 会被 canvas 内置 300px 布局宽度卡死 */
```
```js
const dpr = devicePixelRatio || 1, W = cv.clientWidth || 480, H = 300;
cv.width = W*dpr; cv.height = H*dpr;
const x = cv.getContext("2d"); x.setTransform(dpr,0,0,dpr,0,0); x.clearRect(0,0,W,H);
```
```js
drawAll();
addEventListener("load", () => drawAll());
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => drawAll());
```
柱状圆角：`moveTo(a+r,b) → arcTo(...)×4 → closePath()`；`r = Math.min(r, h/2, w/2)`。

---

## 4. 浏览器验收断言（直接粘进 `browser_console(expression=...)`）

先看有没有 JS 错：
```
browser_console()            # 期望 js_errors: []，total_errors: 0
```

canvas 尺寸 + 非空白采样（`alpha>8` 的采样点数量）：
```js
JSON.stringify({sk:(()=>{const c=document.querySelector('#chartSkills');const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=200)if(d[i]>8)n++;return[c.clientWidth,c.width,c.height,n]})(),
kb:(()=>{const c=document.querySelector('#chartKB');const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=200)if(d[i]>8)n++;return[c.clientWidth,c.width,c.height,n]})()})
```
> 期望 `clientWidth === width`（约 500+）且 `n > 200`。若 `clientWidth === 300` ⇒ 命中 §3 的宽度坑。

交互 + 主题 + 布局一次跑完：
```js
JSON.stringify((()=>{document.querySelectorAll('#layers .layer')[3].click();const l=document.querySelector('#detail .pane.on').id;
document.querySelectorAll('#flowSteps .fstep')[4].click();const f=document.querySelector('.fpane.on').id;
document.querySelectorAll('[data-tabs] .tab')[1].click();const t=document.querySelector('.tabpane.on').id;
document.querySelectorAll('.mech')[0].click();const m=document.querySelectorAll('.mech')[0].classList.contains('on');
document.querySelectorAll('#agentFilters .tab')[2].click();const a=document.querySelectorAll('#agentGrid .agent:not(.hide)').length;
document.getElementById('debateBtn').click();document.getElementById('speakBtn').click();
return{layer:l,flow:f,tab:t,mech:m,agents:a,speak:document.body.classList.contains('speak'),
bodyBg:getComputedStyle(document.body).backgroundColor,overflowX:document.documentElement.scrollWidth-innerWidth}})())
```
> 期望：`layer/flow/tab` 是预期的面板 id、`agents` 等于该类的真实条数、`bodyBg` 是浅色（如 `rgb(245,248,253)`）、`overflowX === 0`。

CSS 是否真生效（CSS 半失效的判据）：
```js
JSON.stringify({hasRule:[...document.styleSheets[0].cssRules].filter(r=>r.selectorText==='canvas').map(r=>r.cssText),
canvasDisplay:getComputedStyle(document.querySelector('canvas')).display})
```
> `hasRule` 为空数组 ⇒ `</style>` 提前闭合，CSS 已成正文。

图片是否真加载：`document.querySelector('.chartcard img').naturalWidth`（>0 才算加载成功）。

---

## 5. 配套静态总览图（matplotlib，300 dpi）

```python
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
for f in ["Microsoft YaHei","SimHei","PingFang SC","Noto Sans CJK SC"]:
    try: font_manager.findfont(f, fallback_to_default=False); plt.rcParams["font.sans-serif"]=[f]; break
    except Exception: continue
plt.rcParams["axes.unicode_minus"] = False
fig = plt.figure(figsize=(13.2,5.4), dpi=300, facecolor="#f7fafd")
axA = fig.add_axes([0.045,0.10,0.46,0.72])          # 资产条形
axB = fig.add_axes([0.565,0.06,0.42,0.80], polar=True)  # 能力雷达
fig.savefig("figures/overview.png", dpi=300, facecolor="#f7fafd", bbox_inches="tight")
```
- 中文标签**必须**先设字体，否则全是方框。
- 数据从 `_stats.json` 读；图注写明「扫描时间 + 脚本名 + 定性评估非基准成绩」。

---

## 6. 页脚（写清可溯源信息）

```
MemOmics · <一句话定位>　　生成于 2026-09-16 · 自包含单文件 HTML（无外部依赖）
results/<sid>/reports/<file>.html
```
旁边配 `collect_stats.py → _stats.json` 与 `scripts/make_showcase_figure.py` 的路径，用户可当场复跑核对。
