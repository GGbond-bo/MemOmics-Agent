# 科研 Agent / 系统 演示页 —— 内容模板与链式流配方

配套 SKILL.md §2.6（内容骨架）与 §2.5（链式流）。
适用：给老师/同学/评委/答辩演示一个自研系统或 Agent。2026-09-16 实测固化。

---

## 一、三段骨架的文案模板

### ① 定义条（放封面页，横条承载，不新开页）

结构：`N 个组成元素 + "=" + 结果卡片`，元素**顺序点亮**（CSS `animation-delay` 错峰）。

| 位 | 短名词 | 3 字说明 |
|----|--------|---------|
| 脑 | 模型 | 会推理 |
| 手 | 工具 | 会动手 |
| 忆 | 记忆 | 会积累 |
| 环 | 循环 | 自己定下一步 |
| = | **Agent** | 不只回答，而是把事做完 |

要点：每个元素 = 图标字（单汉字）+ 名词 + 极短说明。三段式不要写"能够/可以"这类虚词。

### ② 定位等式（紧跟①，一行）

```
科研 Agent  =  Agent  +  领域知识库  +  工具链  +  可验证的结论
```

限定项用 `<em>` 高亮成主题色。**这一行是全页信息密度最高的一句**，不要多加解释。

### ③ 模块盘点（放资产页）

用户说「**按模块展示名字即可，选一些重要的**」→ 就是名称 chip，**每项不配解释句**。

分组呈现（两组之间放一个小标题标签）：

```
分析模块  单细胞 RNA · 染色质 ATAC · 空间转录组 · Bulk/表观 · 蛋白组 · 多组学整合
          遗传/GWAS · 药物/临床 · 微生物/植物 · 分子克隆 · 组织/病理 · 成像/流式

平台能力  文献检索 · 知识库 · 全文翻译 · 引用管理 · 论文写作 · 报告生成 · 辩论审查 · 自进化
```

- 每组 8–12 项，用**胶囊 chip**（圆角 999px）自动换行，不用表格
- 两组用颜色区分（分析模块=中性白，平台能力=淡紫底）
- 数字与文字**同源**：所有数量必须来自同一个采集脚本的同一个 key（见 SKILL.md 坑 9）

---

## 二、链式流配方（多环节链 + 闭合回流）

用于「从 A 到 B 全链跑完」这类叙事（如：读文献 → 写论文）。

### 结构

```
一行进度轨（光带从左扫到右，6.4s 循环）
  └ 8 个站点，每站 animation-delay = 站点序号 × 0.8s  → 形成依次点亮波
底部回流虚线（反向流动），标注「… 回流成新的知识 —— 循环闭合」
```

**同步铁律**：站点点亮周期 = 进度轨周期 = 站点数 × 错峰步长。
`8 × 0.8s = 6.4s`（本次实测值）。三者不一致 → 光带走完了站点还没亮完，一眼就假。

### CSS 骨架

```css
.chain{display:grid;grid-template-columns:repeat(8,1fr);gap:8px}

/* 站点：错峰点亮（--d 由行内 style 逐站给）*/
.ch{animation:chpulse 6.4s linear infinite;animation-delay:var(--d)}
@keyframes chpulse{
  0%,100%{background:transparent;transform:none}
  3%,15%  {background:#f2f8ff;transform:translateY(-4px)}
  24%     {background:transparent;transform:none}
}
/* 图标块与站点同 delay，才不会脱节 */
.ch .ic{animation:icpulse 6.4s linear infinite;animation-delay:var(--d)}
@keyframes icpulse{
  0%,100%{background:#eef5ff;color:#7f96ae;border-color:#dbe9fb;box-shadow:none}
  3%,15%  {background:linear-gradient(120deg,#2563eb,#7c3aed 55%,#06b6d4);color:#fff;
           border-color:transparent;box-shadow:0 8px 20px rgba(37,99,235,.30)}
  24%     {background:#eef5ff;color:#7f96ae;border-color:#dbe9fb;box-shadow:none}
}

/* 进度轨：与站点同周期 */
.chainrail{height:6px;border-radius:99px;background:#e8f0fa;overflow:hidden}
.chainrail i{position:absolute;inset:0 auto 0 0;width:0;border-radius:99px;
  background:linear-gradient(120deg,#2563eb,#7c3aed 55%,#06b6d4);
  animation:railsweep 6.4s cubic-bezier(.45,0,.55,1) infinite}
@keyframes railsweep{0%{width:0}90%{width:100%}100%{width:100%}}

/* 回流虚线：反向流动 = 背景位移取负 */
.returnline .rt{flex:1;height:2px;
  background:repeating-linear-gradient(270deg,#cfdff2 0 9px,transparent 9px 18px);
  animation:revflow 1.1s linear infinite}
@keyframes revflow{to{background-position:-36px 0}}
```

行内错峰（Python 生成时循环给值）：

```html
<div class="ch" style="--d:0s">…</div>
<div class="ch" style="--d:.8s">…</div>
<div class="ch" style="--d:1.6s">…</div>
```

### 站点内容规范

- 图标位用**单汉字**（文 / 译 / 库 / 数 / 析 / 图 / 引 / 著），不用 emoji —— 与整体专业基调一致
- 每站三行：序号（角标）· 图标 + 名称 · 2 行极短说明（含真实数字）
- 站点文案里的数字同样要同源（坑 9）

### 静态图版本（配套 PNG）

同一叙事要做静态图时，用 matplotlib `FancyBboxPatch` + `FancyArrowPatch` 做 **2 行 × 4 列蛇形**
（第 1 行左→右，第 2 行右→左），换行处用 `connectionstyle="arc3,rad=-0.42"` 画折返弧，
再用 `rad=0.55` 从末站回到首站表示闭合。配色沿用展示页 CSS 变量。

---

## 三、交付前必查（脚本化，别凭肉眼）

```python
# 最小字号 + 逐页溢出（≥3 档分辨率）
CHECK = """() => {
  var sl=[].slice.call(document.querySelectorAll('.slide'));
  var over=sl.map(function(s,i){
    var r=s.getBoundingClientRect(), b=0;
    [].slice.call(s.children).forEach(function(c){
      if(c.tagName=='CANVAS') return;
      var x=c.getBoundingClientRect().bottom-r.top;
      if(x>b) b=x;
    });
    return [i+1, Math.round(b - r.height)];
  }).filter(function(p){return p[1]>2;});
  var mn=99, wh='';
  document.querySelectorAll('*').forEach(function(e){
    if(!e.offsetParent) return;
    var f=parseFloat(getComputedStyle(e).fontSize);
    if(e.textContent.trim() && f<mn){ mn=f; wh=(e.className||e.tagName)+''; }
  });
  return {slides:sl.length, over:over, min:mn, minEl:wh.slice(0,40)};
}"""
```

三档分辨率：**1920×1080**（投影）· **1366×768**（笔记本）· **1280×600**（矮屏）。
合格线：`over == []`（零溢出）· `min >= 14`（最小字号）· `slides == dots.length`。

用 playwright 跑（`page.on('pageerror')` 收 JS 错误，必须为空），顺便逐页截图存档当备用图。

---

## 四、本次踩到的两个真缺陷（复现要点）

1. **非贪婪正则只吃掉第一张卡** → 第 2 页换数字卡后残留 3 张旧卡，肉眼看不出，
   靠 OCR（`vision_describe`）拍到重复标签才暴露。改用 index 边界法（SKILL.md 坑 7），
   改完 `grep` 旧值清零。
2. **配套图与页面口径不一致** → 页面写 170、图里算成 174；首页写 350、第 2 页写 352。
   统一到 `collect_stats.py` 的单一 key（SKILL.md 坑 9）。
   注意递归 glob 差异：`results/*/log/run_record` = 504 vs `results/**/run_record` = 536。
