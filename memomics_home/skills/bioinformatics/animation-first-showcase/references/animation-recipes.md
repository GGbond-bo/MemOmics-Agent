# 动画优先展示页 — 可直接复制的配方

`animation-first-showcase` 的配套代码库。全部零依赖（原生 CSS/JS，无 CDN）。

---

## 0. 数正文（交付前必跑，验证 ≤2000 字）

```python
import re
for f in ['旧版.html', '新版.html']:
    s = open(f, encoding='utf-8').read()
    b = re.sub(r'<script.*?</script>|<style.*?</style>', '', s, flags=re.S)
    t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', b)).strip()
    print(f'{f}: 总 {len(s)//1024} KB / 正文字数 {len(t)}')
```

实测基线：文字版 20,588 字 → 动画版 1,888 字（−91%），117 KB → 40 KB。

---

## 1. 页面骨架 chrome

```html
<div id="bar"></div>                      <!-- 顶部进度条 -->
<div id="dots"></div>                     <!-- 右侧圆点导航（JS 生成） -->
<div id="hint">← → 翻页 · 点击卡片展开</div>
<div id="pager">01 / 10</div>
<main>
  <section class="slide" id="s1">…</section>
  …
</main>
```

```css
#bar{position:fixed;top:0;left:0;height:3px;background:var(--grad);width:0;z-index:60;transition:width .25s}
#dots{position:fixed;right:20px;top:50%;transform:translateY(-50%);z-index:60;display:flex;flex-direction:column;gap:10px}
#dots i{width:9px;height:9px;border-radius:50%;background:#c3d4e6;cursor:pointer;transition:.25s;display:block}
#dots i.on{background:var(--blue);transform:scale(1.5);box-shadow:0 0 0 4px rgba(37,99,235,.15)}
#hint{position:fixed;left:20px;bottom:16px;z-index:60;font-size:11px;color:#93a7bb}
#pager{position:fixed;right:20px;bottom:16px;z-index:60;font-size:12px;color:#93a7bb;font-variant-numeric:tabular-nums}
.slide{min-height:100vh;display:flex;flex-direction:column;justify-content:center;
  padding:76px 6vw 76px;max-width:1240px;margin:0 auto;gap:26px}
.reveal{opacity:0;transform:translateY(26px);
  transition:opacity .7s cubic-bezier(.2,.7,.2,1),transform .7s cubic-bezier(.2,.7,.2,1)}
.reveal.in{opacity:1;transform:none}
```

---

## 2. 导航 + 滚轮守卫（⚠️ 坑 1）

```js
var slides = [].slice.call(document.querySelectorAll('.slide'));
var dots = document.getElementById('dots');
var bar  = document.getElementById('bar');
var pager = document.getElementById('pager');
var cur = 0;

slides.forEach(function(s){
  var d = document.createElement('i');
  d.onclick = function(){ s.scrollIntoView({behavior:'smooth'}) };
  dots.appendChild(d);
});
var dotEls = [].slice.call(dots.children);
function pad(n){ return (n<10?'0':'')+n }

function onScroll(){
  var h = document.documentElement.scrollHeight - window.innerHeight;
  bar.style.width = (h>0 ? window.scrollY/h*100 : 0) + '%';
  var best = 0, bd = 1e9;
  slides.forEach(function(s,i){
    var r = s.getBoundingClientRect();
    var d = Math.abs(r.top + r.height/2 - window.innerHeight/2);
    if (d < bd){ bd = d; best = i }
  });
  cur = best;
  dotEls.forEach(function(d,i){ d.classList.toggle('on', i===best) });
  pager.textContent = pad(best+1) + ' / ' + pad(slides.length);
}
window.addEventListener('scroll', onScroll, {passive:true});
onScroll();

function go(n){
  var t = Math.max(0, Math.min(slides.length-1, cur+n));
  slides[t].scrollIntoView({behavior:'smooth'});
}
document.addEventListener('keydown', function(e){
  if (e.key==='ArrowDown'||e.key==='ArrowRight'||e.key===' '){ e.preventDefault(); go(1) }
  if (e.key==='ArrowUp'||e.key==='ArrowLeft'){ e.preventDefault(); go(-1) }
});

/* ⚠️ 仅当当前页完全放得下时才接管滚轮，否则高于屏幕的页会卡死 */
var lock = false;
window.addEventListener('wheel', function(e){
  if (lock || Math.abs(e.deltaY) < 40) return;
  var ae = document.activeElement;
  if (ae && /INPUT|TEXTAREA/.test(ae.tagName)) return;
  var cs = slides[cur];
  if (cs && cs.scrollHeight > window.innerHeight + 40) return;   /* 交给原生滚动 */
  lock = true; setTimeout(function(){ lock = false }, 820);
  go(e.deltaY > 0 ? 1 : -1);
}, {passive:true});
```

---

## 3. 入场 + 分页触发

```js
var io = new IntersectionObserver(function(es){
  es.forEach(function(e){
    if (!e.isIntersecting) return;
    var s = e.target;
    [].slice.call(s.querySelectorAll('.reveal')).forEach(function(el,i){
      setTimeout(function(){ el.classList.add('in') }, 40 + i*70);
    });
    /* 每页动画只播一次 */
    if (s.id==='s2' && !s.dataset.done){ s.dataset.done=1; countUp() }
    if (s.id==='s3' && !s.dataset.done){ s.dataset.done=1; setTimeout(pipe, 450) }
    if (s.id==='s4' && !s.dataset.done){ s.dataset.done=1; setTimeout(gate, 600) }
  });
}, {threshold:.22});
slides.forEach(function(s){ io.observe(s) });
```

> `threshold:.22` 对「比视口高的页」也能触发（22% 高度可见即可）。

---

## 4. 数字滚动

```js
function countUp(){
  [].slice.call(document.querySelectorAll('.stat .n')).forEach(function(el){
    var to = +el.dataset.to, t0 = performance.now();
    (function tick(t){
      var p = Math.min(1, (t-t0)/1200), e = 1 - Math.pow(1-p, 3);   /* easeOutCubic */
      el.textContent = Math.round(to*e);
      if (p < 1) requestAnimationFrame(tick);
    })(t0);
  });
}
```

```html
<div class="stat"><div class="n" data-to="350">0</div><div class="l">生信技能模板</div></div>
```

---

## 5. 流水线火花动画

```js
var pipeTimers = [];
function clearTimers(){ pipeTimers.forEach(clearTimeout); pipeTimers = [] }

function pipe(){
  clearTimers();
  var track = document.getElementById('track');
  var nodes = [].slice.call(track.querySelectorAll('.pn'));
  var spark = document.getElementById('spark');
  var fill  = document.getElementById('railFill');
  nodes.forEach(function(n){ n.classList.remove('lit') });
  fill.style.width = '0';
  spark.style.opacity = 1;
  spark.style.left = '4%';
  var i = 0;
  function step(){
    if (i >= nodes.length){ spark.style.opacity = 0; pipeTimers.push(setTimeout(pipe, 3200)); return }
    var n = nodes[i], tr = track.getBoundingClientRect(), r = n.getBoundingClientRect();
    spark.style.left = ((r.left - tr.left + r.width/2)/tr.width*100) + '%';
    fill.style.width = ((i+1)/nodes.length*100) + '%';
    pipeTimers.push(setTimeout(function(){ n.classList.add('lit') }, 240));
    i++;
    pipeTimers.push(setTimeout(step, 620));
  }
  step();
}
document.getElementById('replay').onclick = pipe;
```

CSS：轨道 `.rail` + 绝对定位 `.spark`，节点 `.pn.lit` 时去灰度并抬升：

```css
.track{display:grid;grid-template-columns:repeat(8,1fr);gap:8px;position:relative;padding-top:14px}
.rail{position:absolute;left:4%;right:4%;top:66px;height:2px;background:#e7eff9;border-radius:2px}
.rail i{display:block;height:100%;width:0;background:var(--grad);border-radius:2px;transition:width .5s}
.spark{position:absolute;top:60px;left:4%;width:14px;height:14px;border-radius:50%;background:#fff;
  border:3px solid var(--blue);box-shadow:0 0 0 5px rgba(37,99,235,.15);
  transition:left .45s cubic-bezier(.3,.8,.3,1);opacity:0;z-index:3}
.pn .g{transition:.4s;filter:grayscale(.55);opacity:.65}
.pn.lit .g{filter:none;opacity:1;transform:translateY(-4px);box-shadow:0 8px 22px rgba(37,99,235,.18)}
```

**CSS 图形 glyph（替代 emoji）**：

```css
.g-dots{background-image:radial-gradient(circle,#2563eb 1.7px,transparent 1.8px);background-size:9px 9px}
.g-funnel{background:linear-gradient(#06b6d4,#0e7490);clip-path:polygon(0 0,100% 0,63% 100%,37% 100%)}
.g-clu{background-image:
  radial-gradient(circle at 28% 34%,#2563eb 6px,transparent 7px),
  radial-gradient(circle at 66% 28%,#8b5cf6 5.5px,transparent 6.5px),
  radial-gradient(circle at 44% 72%,#06b6d4 5.5px,transparent 6.5px)}
.g-up{border-left:7px solid transparent;border-right:7px solid transparent;border-bottom:15px solid #f43f5e}
.g-dn{border-left:7px solid transparent;border-right:7px solid transparent;border-top:15px solid #2563eb}
```

---

## 6. 闸门「打回 → 修复 → 放行」循环

```js
function gate(){
  var ids = ['c1','c2','c3','c4'], el = ids.map(function(x){ return document.getElementById(x) });
  var vd = document.getElementById('vd'), vt = document.getElementById('vtxt');
  el.forEach(function(e){ e.className = 'ck' });
  vd.className = 'verdict'; vt.textContent = '等待审查…';
  /* [节点, 动作, 文案]；动作 ok=通过 / no=不通过 / reset=清空；-1 = 全部放行 */
  var seq = [[0,'ok',null],[1,'ok',null],[2,'no','第 3 关不通过：结果质检发现空白图'],
             [0,'reset',null],[1,'reset',null],[2,'reset',null],[3,'reset',null],[-1,'pass',null]];
  var t = 0;
  seq.forEach(function(step){
    if (step[0] === -1){
      t += 800;
      setTimeout(function(){
        el.forEach(function(e){ e.className = 'ck ok' });
        vd.className = 'verdict ok';
        vt.textContent = '全部通过 → 放行，进入下一步';
      }, t);
      return;
    }
    t += 680;
    var idx = step[0], act = step[1];
    setTimeout(function(){
      if (act === 'reset'){ el[idx].className = 'ck'; vt.textContent = '自动修复问题 → 重新审查…'; vd.className = 'verdict' }
      else if (act === 'ok'){ el[idx].className = 'ck ok'; if (idx===2) vt.textContent = '第 3 关不通过：结果质检发现空白图' }
      else { el[idx].className = 'ck no shake'; vd.className = 'verdict'; vt.textContent = '已阻断 → 修正后重跑' }
    }, t);
  });
  setTimeout(gate, 9000);      /* 循环自播 */
}
```

```css
@keyframes shk{0%,100%{transform:translateX(0)}25%{transform:translateX(-6px)}75%{transform:translateX(6px)}}
.shake{animation:shk .45s}
```

---

## 7. 多角色机制演示（点亮 → 汇入 → 裁决）

```js
var busy = false;
document.getElementById('btnDebate').onclick = function(){
  if (busy) return; busy = true;
  var pro = [].slice.call(document.querySelectorAll('#pro .role'));
  var con = [].slice.call(document.querySelectorAll('#con .role'));
  var judge = document.getElementById('judge'), cf = document.getElementById('cf');
  var beams = [].slice.call(document.querySelectorAll('#beams i'));
  pro.concat(con).forEach(function(r){ r.classList.remove('on') });
  beams.forEach(function(b){ b.classList.remove('f') });
  judge.classList.remove('on'); cf.textContent = '置信度 —';

  var t = 0;
  pro.forEach(function(r){ t += 280; setTimeout(function(){ r.classList.add('on') }, t) });
  con.forEach(function(r){ t += 260; setTimeout(function(){ r.classList.add('on') }, t) });
  beams.forEach(function(b){ t += 90; setTimeout(function(){ b.classList.add('f') }, t) });
  t += 350;
  setTimeout(function(){ judge.classList.add('on'); cf.textContent = '置信度 0.82 · 已回写技能库' }, t);
  t += 900;
  setTimeout(function(){ busy = false; document.getElementById('btnDebate').textContent = '▶ 再来一场' }, t);
};
```

---

## 8. 轨道公转（⚠️ 坑 2 的正确写法）

```css
.ring{position:absolute;inset:0;border-radius:50%;border:1px dashed #cddff2;animation:spin 34s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

.orb{position:absolute;inset:0;animation:spin 26s linear infinite}
.orb.o2{animation-duration:34s;animation-direction:reverse}

/* ✅ 把 translateX(-50%) 写进关键帧，定位与自转共存 */
.orb span{position:absolute;left:50%;top:-13px;padding:5px 11px;border-radius:999px;
  background:#fff;border:1px solid var(--line);box-shadow:var(--shs);font-size:11.5px;
  font-weight:700;white-space:nowrap;animation:upright 26s linear infinite;color:#2b4a6f}
.orb.o2 span{animation:uprightR 34s linear infinite}

@keyframes upright{ from{transform:translateX(-50%) rotate(0)}   to{transform:translateX(-50%) rotate(-360deg)} }
@keyframes uprightR{from{transform:translateX(-50%) rotate(0)}   to{transform:translateX(-50%) rotate(360deg)} }
```

规则：父级 `animation-direction:reverse` → 子级用正向关键帧（`uprightR`），反之亦然。

```css
.core{position:absolute;inset:30%;border-radius:50%;background:var(--grad);
  display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;
  box-shadow:0 0 0 12px rgba(37,99,235,.07),0 0 0 26px rgba(37,99,235,.045),0 18px 50px rgba(79,70,229,.35)}
.core::after{content:"";position:absolute;inset:-4px;border-radius:50%;
  border:2px solid rgba(37,99,235,.35);animation:pulse 2.6s ease-out infinite}
@keyframes pulse{0%{transform:scale(1);opacity:.85}100%{transform:scale(1.5);opacity:0}}
```

---

## 9. 卡片点开 + 时间线 + 路线图

```js
/* 卡片：点开显示细节 */
[].slice.call(document.querySelectorAll('.cd')).forEach(function(c){
  c.onclick = function(){ c.classList.toggle('open') };
});
```

```css
.cd .more{max-height:0;overflow:hidden;transition:max-height .45s ease}
.cd.open .more{max-height:220px}
```

```js
/* 时间线：进度条推进 + 节点错峰入场 */
function timeline(){
  document.getElementById('tlFill').style.width = '100%';
  [].slice.call(document.querySelectorAll('.tlitem')).forEach(function(el,i){
    setTimeout(function(){ el.classList.add('in') }, i*180);
  });
}
/* 路线图进度条 */
function road(){
  [].slice.call(document.querySelectorAll('.ph .bar i')).forEach(function(el,i){
    setTimeout(function(){ el.style.width = el.dataset.w + '%' }, 200 + i*220);
  });
}
```

---

## 10. 响应式与矮屏

```css
@media(max-width:960px){
  .grid4{grid-template-columns:repeat(2,1fr)}
  .track{grid-template-columns:repeat(4,1fr);row-gap:18px}
  .rail,.spark{display:none}          /* 换行后火花定位无意义 */
  .cards,.road,.loop{grid-template-columns:1fr 1fr}
  .sides{grid-template-columns:1fr;gap:14px}
  .tlrow{grid-template-columns:repeat(3,1fr);row-gap:20px}
  .tlrail{display:none}
}
@media(max-width:640px){
  .grid4,.cards,.road,.loop,.track,.tlrow{grid-template-columns:1fr}
  #dots{display:none}
}
/* 矮屏（笔记本投影）压缩纵向占用，保证一屏一页 */
@media(max-height:760px){
  .slide{padding:54px 6vw 54px;gap:18px}
  .hwrap{width:min(290px,40vw)}
  h1{font-size:clamp(30px,4.6vw,54px)}
  .stat{padding:16px}
}
```

---

## 11. 浏览器实测取样（交付前必跑，console 必须零报错）

```js
// ① 结构一致性
JSON.stringify({
  slides: document.querySelectorAll('.slide').length,
  dots: document.querySelectorAll('#dots i').length,
  pager: document.getElementById('pager').textContent,
  docW: document.documentElement.scrollWidth,
  winW: window.innerWidth                      // 两者必须相等 → 无横向溢出
})

// ② 逐页高度 vs 视口（找出会卡死的页）
var out=[];document.querySelectorAll('.slide').forEach(function(s){out.push(s.id+':'+s.scrollHeight)});out.join(' | ')

// ③ 计数器终值
[...document.querySelectorAll('.stat .n')].map(function(n){return n.textContent}).join(',')

// ④ 流水线进度
'lit='+document.querySelectorAll('#track .pn.lit').length+' railW='+document.getElementById('railFill').style.width

// ⑤ 闸门状态
[...document.querySelectorAll('.ck')].map(c=>c.id+':'+(c.classList.contains('ok')?'ok':c.classList.contains('no')?'NO':'--')).join(' ')
    + ' | ' + document.getElementById('vtxt').textContent

// ⑥ 多角色演示
'proOn='+document.querySelectorAll('#pro .role.on').length+' conOn='+document.querySelectorAll('#con .role.on').length
  +' judgeOn='+document.getElementById('judge').classList.contains('on')

// ⑦ 卡片展开
'openCards='+document.querySelectorAll('.cd.open').length
```

**实测基线（本次通过值）**：
`slides=10/dots=10 · docW==winW · 计数器 350,168,495,189 · lit 递增+railW=75% ·
闸门 c3:NO→全绿 · 辩论 proOn=3 conOn=4 beams=8 judgeOn=true · openCards=1 · js_errors=0`

---

## 12. 流动过程图（讲「演进 / 未来 / 机制」专用，2026-09-16 用户点名要）

> 用户原话：「重点在展示未来自主科研，和未来 AI 发展上，**这些用更多流动的过程图展示细节**」。
> 结论：讲**趋势/演进/循环**的页面，一律用「有东西在流动」的图，不要用文字段落或静态卡片。
> 共同原理：**一个持续循环的 CSS 动画做背景流 + 一个 JS `setInterval` 做节点顺序点亮**，两者同周期即为「流动感」。

### 12.1 流动带（conveyor：横向传送 + 货物在跑）

适用：封面底部 / 「数据 → 分析 → 报告」这类线性链路。

```html
<div class="flowstrip">
  <div class="belt"></div>
  <span class="pkt">data.h5ad → 扫描 → QC</span>
  <span class="pkt p2">聚类 → 注释 → 差异基因</span>
  <span class="pkt p3">通路富集 → 出图 → 报告</span>
</div>
```

```css
.flowstrip{position:relative;width:min(1000px,92vw);height:46px;border-radius:23px;background:#fff;
  border:1px solid var(--line);box-shadow:var(--shs);overflow:hidden}
.flowstrip .belt{position:absolute;inset:0;                       /* 底纹持续右移 = 传送带 */
  background-image:repeating-linear-gradient(90deg,rgba(37,99,235,.12) 0 22px,transparent 22px 44px);
  animation:belt 1.8s linear infinite}
@keyframes belt{to{background-position-x:44px}}                   /* 位移量 = 条纹周期，接缝无痕 */
.flowstrip .pkt{position:absolute;top:50%;transform:translateY(-50%);height:26px;padding:0 13px;
  border-radius:13px;background:var(--grad);color:#fff;font-size:11px;font-weight:700;
  display:flex;align-items:center;white-space:nowrap;left:-170px;
  animation:pktRun 8.4s linear infinite}                          /* 三个货物错峰 = 连续流动感 */
.flowstrip .pkt.p2{background:linear-gradient(120deg,#8b5cf6,#06b6d4);animation-delay:-2.8s}
.flowstrip .pkt.p3{background:linear-gradient(120deg,#14b8a6,#2563eb);animation-delay:-5.6s}
@keyframes pktRun{from{left:-170px}to{left:102%}}
```

要点：`from` 用**负的自身宽度**起手（从容器外滑入），三个货物用**负 `animation-delay`** 错峰 —— 负延迟让它们一开场就已分布在不同位置，不会「先空 5 秒」。

### 12.2 循环流（orbit cycle：6 节点环 + 旋转臂 + 顺序点亮）

适用：「科研循环」「闭环流程」「自驱动机制」—— 表达**自己转起来**。

```html
<div class="cycle" id="cycle">
  <div class="cyc-ring"></div>                       <!-- 虚线圈（慢转） -->
  <div class="cyc-arm"><i></i></div>                 <!-- 旋转臂 + 臂端光点 -->
  <div class="cyc-core">科研循环<small>SELF-DRIVING</small></div>
  <div class="cyc-node" style="left:50%;top:10%"><div class="t">读文献</div><div class="d">每天新增</div></div>
  <div class="cyc-node" style="left:84.6%;top:30%">…</div>   <!-- 环上 6 点，半径 40% -->
  <div class="cyc-node" style="left:84.6%;top:70%">…</div>
  <div class="cyc-node" style="left:50%;top:90%">…</div>
  <div class="cyc-node" style="left:15.4%;top:70%">…</div>
  <div class="cyc-node" style="left:15.4%;top:30%">…</div>
</div>
```

```css
.cycle{position:relative;width:min(56vh,540px,78vw);aspect-ratio:1;margin:0 auto}
.cyc-ring{position:absolute;inset:10%;border-radius:50%;border:2px dashed #cfe0f4;animation:spin 46s linear infinite}
.cyc-arm{position:absolute;inset:0;animation:spin 10.8s linear infinite}
.cyc-arm i{position:absolute;left:50%;top:10%;width:13px;height:13px;margin:-6.5px 0 0 -6.5px;   /* 臂端光点 */
  border-radius:50%;background:#fff;border:3px solid var(--blue);box-shadow:0 0 0 7px rgba(37,99,235,.12)}
.cyc-node{position:absolute;transform:translate(-50%,-50%);width:116px;background:#fff;
  border:1px solid var(--line);border-radius:13px;padding:8px 5px;text-align:center;box-shadow:var(--shs);transition:.45s}
.cyc-node.on{border-color:#bcd8f7;box-shadow:0 12px 30px rgba(37,99,235,.2);
  transform:translate(-50%,-50%) scale(1.08)}                     /* ⚠️ 缩放必须带上 translate */
```

```js
/* 节点点亮周期 = 旋转臂周期 / 节点数 → 光点走到哪个节点，哪个节点就亮 */
function cycle(){
  var c = document.getElementById('cycle'); if (!c) return;
  var ns = [].slice.call(c.querySelectorAll('.cyc-node')); if (!ns.length) return;
  var i = 0;
  setInterval(function(){
    ns.forEach(function(n,j){ n.classList.toggle('on', j===i) });
    i = (i+1) % ns.length;
  }, 1800);                                    /* 10.8s / 6 = 1.8s */
}
```

**环上 6 点坐标**（半径 40%，容器百分比）：`(50,10) (84.6,30) (84.6,70) (50,90) (15.4,70) (15.4,30)`。
**同步铁律**：`setInterval` 的毫秒数必须 = `.cyc-arm` 动画周期 ÷ 节点数，否则光点与点亮错位（一眼假）。

### 12.3 阶梯流（capability ladder：能力阶梯 + 爬升虚线上升）

适用：「AI 能力演进」「阶段跃迁」—— 表达**一级比一级高**。

```html
<div class="ladderwrap">
  <div class="ascend"></div>                     <!-- 顶部持续右移的虚线 = 上升流 -->
  <div class="ladder" id="ladder">
    <div class="rung" style="height:24%"><div class="lv">L1</div><div class="t">对话</div><div class="y">2022</div></div>
    <div class="rung" style="height:38%">…</div>  <!-- 高度递增：24/38/52/66/80/94% -->
  </div>
</div>
```

```css
.ladderwrap{position:relative;padding-top:24px}
.ascend{position:absolute;left:0;right:0;top:6px;height:3px;
  background-image:repeating-linear-gradient(90deg,#bcd8f7 0 11px,transparent 11px 22px);
  animation:belt 1.4s linear infinite}                              /* 复用 §12.1 的 belt 关键帧 */
.ladder{display:flex;align-items:flex-end;gap:10px;height:min(36vh,250px)}
.rung{flex:1;background:#eef5ff;border:1px solid #e3eefb;border-radius:12px 12px 8px 8px;
  display:flex;flex-direction:column;justify-content:flex-end;align-items:center;transition:.55s}
.rung.on{background:linear-gradient(180deg,#eaf2ff,#fff);border-color:#bcd8f7;
  transform:translateY(-7px);box-shadow:0 14px 32px rgba(37,99,235,.17)}
```

```js
/* 逐级点亮 + 2 拍留白 → 形成「爬升—停顿—再爬升」的呼吸节奏，比匀速更抓眼 */
function ladder(){
  var L = document.getElementById('ladder'); if (!L) return;
  var rs = [].slice.call(L.querySelectorAll('.rung')); if (!rs.length) return;
  var i = 0;
  setInterval(function(){
    rs.forEach(function(r,j){ r.classList.toggle('on', j===i) });
    i = (i+1) % (rs.length + 2);                 /* +2 = 留白拍 */
  }, 850);
}
```

### 12.4 汇流带（converging lanes：两股流汇到中间结论）

适用：「A 与 B 的对比关系」→ **不是并列，而是流向一个判断**（本次：想法产能过剩 vs 验证产能稀缺 → 瓶颈迁移）。

```html
<div class="converge">
  <div><div class="lcap" style="margin-bottom:7px">想法产能 · 已经过剩</div>
       <div class="lane3"><i></i><i></i><i></i><i></i><i></i></div></div>
  <div class="converge-core"><div class="a">瓶颈在迁移</div><div class="b">会想 → 会验</div></div>
  <div><div class="lcap" style="margin-bottom:7px">验证产能 · 新的稀缺</div>
       <div class="lane3 rev"><i></i><i></i><i></i><i></i><i></i></div></div>
</div>
```

```css
.converge{display:grid;grid-template-columns:1fr 240px 1fr;gap:16px;align-items:end}
.lane3{position:relative;height:34px;border-radius:10px;background:#f5f9ff;overflow:hidden;border:1px solid #e9f1fb}
.lane3 i{position:absolute;top:50%;width:9px;height:9px;margin-top:-4.5px;border-radius:50%;
  background:var(--blue);animation:laneRun 3.8s linear infinite}
.lane3.rev i{background:var(--violet);animation-direction:reverse}  /* 反向流 = 反向态势，视觉上自带对比 */
.lane3 i:nth-child(2){animation-delay:-1.3s;opacity:.62}
.lane3 i:nth-child(3){animation-delay:-2.6s;opacity:.36}
@keyframes laneRun{from{left:-14px}to{left:100%}}
.converge-core{background:linear-gradient(150deg,#0e1b30,#1e3a5f);color:#fff;
  border-radius:16px;text-align:center;padding:15px 10px;box-shadow:0 14px 34px rgba(14,27,48,.28)}
```

要点：**同一条 lane 里放 3–5 个点、负延迟错峰、透明度递减** → 用最少的 DOM 做出「密度感」。反向流用 `animation-direction:reverse`，不要写第二组关键帧。

### 12.5 封面粒子网络（canvas 背景，鼠标可联动）

适用：封面做底纹（「未来感」成本最低的加分项）。**纯本地 canvas，不引任何库。**

```css
#s1 canvas{position:absolute;inset:0;width:100%;height:100%;z-index:0;opacity:.55;pointer-events:none}
```

```js
(function stars(){
  var cv = document.getElementById('stars'); if (!cv || !cv.getContext) return;
  var ctx = cv.getContext('2d'), W=0, H=0, ps=[], mx=-9999, my=-9999, host=cv.parentNode;
  function size(){
    var r = host.getBoundingClientRect();
    W = cv.width = Math.max(320, Math.round(r.width));
    H = cv.height = Math.max(320, Math.round(r.height));
    var n = Math.max(26, Math.min(60, Math.round(W*H/28000)));   /* 按面积定粒子数，封顶 60 保证流畅 */
    ps = []; for (var i=0;i<n;i++) ps.push({x:Math.random()*W, y:Math.random()*H,
      vx:(Math.random()-.5)*.26, vy:(Math.random()-.5)*.26, r:Math.random()*1.5+.9});
  }
  function draw(){
    /* 滚出封面后不再绘制（省电，投影机风扇会安静很多） */
    if (window.scrollY > window.innerHeight*1.3){ requestAnimationFrame(draw); return }
    ctx.clearRect(0,0,W,H);
    for (var i=0;i<ps.length;i++){
      var p = ps[i]; p.x += p.vx; p.y += p.vy;
      if (p.x<-20) p.x = W+20; else if (p.x>W+20) p.x = -20;      /* 环绕回卷，不留空区 */
      if (p.y<-20) p.y = H+20; else if (p.y>H+20) p.y = -20;
      var dmx=p.x-mx, dmy=p.y-my, dm=Math.sqrt(dmx*dmx+dmy*dmy);
      if (dm < 150){                                               /* 鼠标半径内连线 */
        ctx.strokeStyle='rgba(37,99,235,'+(0.2*(1-dm/150)).toFixed(3)+')';
        ctx.lineWidth=1; ctx.beginPath(); ctx.moveTo(p.x,p.y); ctx.lineTo(mx,my); ctx.stroke();
      }
      for (var j=i+1;j<ps.length;j++){
        var q=ps[j], dx=p.x-q.x, dy=p.y-q.y, d=Math.sqrt(dx*dx+dy*dy);
        if (d < 116){                                              /* 粒子间连线，距离越近越深 */
          ctx.strokeStyle='rgba(79,70,229,'+(0.17*(1-d/116)).toFixed(3)+')';
          ctx.lineWidth=1; ctx.beginPath(); ctx.moveTo(p.x,p.y); ctx.lineTo(q.x,q.y); ctx.stroke();
        }
      }
      ctx.fillStyle='rgba(37,99,235,.5)'; ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,6.2832); ctx.fill();
    }
    requestAnimationFrame(draw);
  }
  host.addEventListener('mousemove', function(e){                   /* ⚠️ 监听 host，不要监听 canvas */
    var r = cv.getBoundingClientRect(); mx = e.clientX - r.left; my = e.clientY - r.top;
  });
  host.addEventListener('mouseleave', function(){ mx = my = -9999 });
  window.addEventListener('resize', size);
  size(); draw();
})();
```

> ⚠️ canvas 设了 `pointer-events:none`（避免挡住封面其它元素的点击）→ **`mousemove` 绑在父容器上**，
> 绑 canvas 永远不会触发。这是本配方唯一容易踩空的地方。

**验收断言（canvas 必须真的画了东西）**：

```js
(()=>{const c=document.getElementById('stars');const d=c.getContext('2d')
  .getImageData(0,0,c.width,c.height).data;let nz=0;
  for(let i=3;i<d.length;i+=4){if(d[i]>0)nz++}
  return JSON.stringify({canvas:c.width+'x'+c.height, nonEmptyPixels:nz,
    ratio:+(nz/(c.width*c.height)).toFixed(4)})})()
/* 通过值：非空像素 > 2000（本次 3276 / 886600 ≈ 0.37%）——0 就是没画 */
```

---

## 13. 本轮新增三坑（2026-09-16 加页/改版时踩到）

### 坑 4：`#sN > *` 通用选择器会覆盖子元素的绝对定位

为了给封面元素统一加 `z-index`，写了 `#s1>*{position:relative;z-index:1}` ——
结果 `.scrollcue{position:absolute}` 被 `#s1>*`（同为 id+1 特异性，且规则在后）压掉，**回到底部提示跑到文档流里**。

```css
/* ❌ 通用子选择器一网打尽，绝对定位子元素全部变 relative */
#s1>*{position:relative;z-index:1}

/* ✅ 枚举需要的元素；确需绝对定位的用更高特异性回写 */
#s1 .badge,#s1 h1,#s1 .hero-kicker,#s1 .gwrap,#s1 .flowstrip,#s1 .hero-stats,#s1 .chips,#s1 .scrollcue{position:relative;z-index:1}
#s1 .scrollcue{position:absolute}          /* id+class 特异性 (1,1,0) > (1,0,1)，稳赢 */
```

**通用规则**：`#id > *` 这类「一网打尽」选择器，只要子元素里有一个需要 `absolute/fixed`，就一定出事。
落笔前先问：「这层里有谁要脱离文档流？」

### 坑 5：封面尺寸必须用 `min(vh, px, vw)` 三元封顶

只写 `width:min(580px,74vw)` → 在 1366×768 笔记本（视口高 ≈640）上，封面总高 > 视口，
**底部数字条被推到屏幕外**，演示时看不见。

```css
.gwrap{width:min(50vh,540px,72vw)}   /* 高度、绝对上限、宽度 三重封顶，取最小 */
```

配套：**矮屏媒体查询不要过度压缩**（上一版把封面压到 `min(290px,40vw)`，用户要的「面积大一点」直接没了）：

```css
@media(max-height:760px){
  .gwrap{width:min(38vh,340px,54vw)}     /* 矮屏只降到 ~70%，不是腰斩 */
  .flowstrip{height:40px} .hero-stats .hs{padding:6px 13px}
}
```

**封面总高预算**（实测核算，视口高 H）：`固定元素 ≈ 440px + 封面圆直径 ≤ H`
⇒ 圆直径取 `50vh` 时，1080p(1000) 用 500 → 总 940 ✓；768p(640) 用 320 → 总 760 ✗ 需再降。
所以矮屏那一档是**必须**的，不是可选。

### 坑 6：删一个章节要四处联动，漏一处就出 bug

用户说「去掉 MemOmics 跟别的对比」→ 删掉 `#s8` 后**必须同步改 4 处**：

| # | 位置 | 不改会怎样 |
|---|------|-----------|
| 1 | 新增页的 `id`（`s8/s9→s9/s10/s11`） | **id 重复** → `getElementById` 只取第一个，动画全部错位 |
| 2 | JS 触发块 `if(s.id==='s9'){road()}` | 路线图动画永不播放（静默失效，看不出来） |
| 3 | CSS 里 `#s9{...}` / `#s10{...}` 选择器 | 样式丢失（如收尾页居中失效） |
| 4 | `#pager` 里的 `01 / 10` 默认值 | 首帧显示错页码（JS 跑起来才纠正，闪烁可见） |

**验收脚本（改版后必跑）**：

```js
JSON.stringify({
  ids: [...document.querySelectorAll('.slide')].map(s=>s.id),        // 顺序且无重复
  dup: [...document.querySelectorAll('[id]')].map(e=>e.id)
        .filter((v,i,a)=>a.indexOf(v)!==i),                            // 必须为空数组
  slides: document.querySelectorAll('.slide').length,
  dots: document.querySelectorAll('#dots i').length                    // 与 slides 相等
})
/* 通过值：ids=["s1"…"s11"] · dup=[] · slides=11 · dots=11 */
```

删除后**逐个确认动效仍在跑**（本次 5 项）：

```js
JSON.stringify({
  cycOn:  [...document.querySelectorAll('.cyc-node')].map((n,i)=>n.classList.contains('on')?i:null).filter(v=>v!==null),
  rungOn: [...document.querySelectorAll('.rung')].map((n,i)=>n.classList.contains('on')?i:null).filter(v=>v!==null),
  laneDot: getComputedStyle(document.querySelector('.lane i')).left,   // 持续变化 = 在流动
  pktLeft: getComputedStyle(document.querySelector('.pkt')).left,      // 持续变化 = 在跑
  ascend:  getComputedStyle(document.querySelector('.ascend')).backgroundPositionX
})
```
