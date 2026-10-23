#!/usr/bin/env node
// 交互框增量渲染 —— 「旧段删不掉 → 同一段输出重复累积」回归（2026-10-23 事故）
//
// 事故现场（真机会话 memomics-f3cbef42，长任务跑了约 1 小时）：
//   用户报告「交互框输出的内容一直在重复」—— 同一个回答气泡里，早先的过程叙述
//   被后来更长的版本一遍遍盖在下面，粘贴出来是层层包含的多份（实测 4 份）。
//
// 根因（renderBubbleIncremental 的引用丢失）：
//   一次「内容没变」的渲染（切会话后重挂载 liveBubble / 节流定时器 flush / 进度重放）
//   让 common == segs.length，追加循环不跑，但它照样执行 state.segs = segs ——
//   而 segs 是 splitMsgBlocks() 现切出来的新对象，没有 .node 引用。
//   此后任何一次内容变化：删除循环拿 state.segs[r].node === undefined → 跳过删除，
//   旧节点留在 DOM 里；新节点又 append 进来 → 同一段文字越积越多。
//
// 本文件：抠 webui/index.html 里的真实函数（renderBubbleIncremental / splitMsgBlocks /
//   extractFenceBlocks），配一个最小 DOM 桩，按事故时序复现并锁死修法：
//   ① 未变化的段必须继承（或按位置补回）node 引用；
//   ② DOM 子节点数与 state.segs 失配（历史残留副本）→ 清空整块重建；
//   ③ 快照恢复回来的气泡（DOM 有渲染块、但没有 JS 状态）→ 复用该块，不新挂第二个。
'use strict';
const fs = require('fs');
const path = require('path');
const NL = String.fromCharCode(10);
const HTML_PATH = process.env.INCR_INDEX_HTML || path.join(__dirname, '..', 'index.html');
const HTML = fs.readFileSync(HTML_PATH, 'utf8');

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  ok   ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra === undefined ? '' : '  -> ' + extra)); }
}
function grab(name) {
  const sig = 'function ' + name + '(';
  const i = HTML.indexOf(sig);
  if (i < 0) throw new Error('找不到函数 ' + name);
  let depth = 0;
  for (let k = HTML.indexOf('{', i); k < HTML.length; k++) {
    if (HTML[k] === '{') depth++;
    else if (HTML[k] === '}') { depth--; if (depth === 0) return HTML.slice(i, k + 1); }
  }
  throw new Error('括号不配对 ' + name);
}

// ---------- 最小 DOM 桩 ----------
class El {
  constructor(tag) {
    this.tagName = tag || 'div';
    this._children = [];
    this.parentNode = null;
    this.className = '';
    this._html = '';
    this._own = '';
  }
  // children 用 Proxy 保持"活集合"语义（每次取 length/索引都看当前子节点）
  get children() {
    const el = this;
    return new Proxy([], {
      get(t, k) {
        if (typeof k === 'symbol') return t[k];
        if (k === 'length') return el._children.length;
        const i = Number(k);
        if (Number.isInteger(i) && i >= 0 && i < el._children.length) return el._children[i];
        return t[k];
      }
    });
  }
  get isConnected() {
    let n = this;
    while (n.parentNode) n = n.parentNode;
    return n === ROOT;
  }
  appendChild(c) {
    if (c.parentNode) c.parentNode.removeChild(c);
    c.parentNode = this;
    this._children.push(c);
    return c;
  }
  removeChild(c) {
    const i = this._children.indexOf(c);
    if (i >= 0) { this._children.splice(i, 1); c.parentNode = null; }
    return c;
  }
  set innerHTML(v) {
    this._html = String(v == null ? '' : v);
    // 测试里 renderSegmentHtml 桩返回的就是纯文本 → 直接当作本节点的文字内容
    this._own = this._html;
    if (this._html === '') {
      for (const c of this._children) c.parentNode = null;
      this._children = [];
    }
  }
  get innerHTML() { return this._html; }
  set textContent(v) { this._own = String(v == null ? '' : v); }
  get textContent() { return this._own + this._children.map((c) => c.textContent).join(''); }
  _match(sel) {
    if (sel.charAt(0) !== '.') return false;
    return String(this.className).split(/\s+/).indexOf(sel.slice(1)) >= 0;
  }
  querySelector(sel) {
    for (const c of this._children) {
      if (c._match(sel)) return c;
      const r = c.querySelector(sel);
      if (r) return r;
    }
    return null;
  }
  querySelectorAll(sel, out) {
    out = out || [];
    for (const c of this._children) {
      if (c._match(sel)) out.push(c);
      c.querySelectorAll(sel, out);
    }
    return out;
  }
}
const ROOT = new El('root');
const documentStub = { createElement: (tag) => new El(tag) };

const ENV = {
  document: documentStub,
  // 渲染桩：段正文 = 该段原始文本（本测试只关心分段/节点簿记，不关心 markdown 细节）
  renderSegmentHtml: (seg) => String(seg.raw || ''),
  splitMsgBlocks: null, extractFenceBlocks: null, renderBubbleIncremental: null
};

const code = [grab('extractFenceBlocks'), grab('splitMsgBlocks'), grab('renderBubbleIncremental')].join(NL);
const factory = new Function('env', [
  'var document = env.document;',
  'var renderSegmentHtml = env.renderSegmentHtml;',
  code,
  'return { render: renderBubbleIncremental, split: splitMsgBlocks };'
].join(NL));
const api = factory(ENV);

// ---------- 工具 ----------
function newBubble() {
  const b = new El('div');
  b.className = 'bubble';
  ROOT.appendChild(b);   // 保持 connected，走正常渲染分支
  return b;
}
function countOf(text, needle) {
  let c = 0, i = 0;
  while ((i = text.indexOf(needle, i)) >= 0) { c++; i += needle.length; }
  return c;
}
const T1 = '开场白段。' + NL + NL + '```' + NL + 'code-one' + NL + '```' + NL + NL + '中段内容-MARK1';
const T2 = '开场白段。' + NL + NL + '```' + NL + 'code-one' + NL + '```' + NL + NL + '中段内容-MARK1-后续续写-MARK2';

console.log('== A. 首渲染：段数 = DOM 子节点数，node 引用齐全 ==');
{
  const b = newBubble();
  api.render(b, T1);
  const st = b._incr;
  const body = b.querySelector('.md-incremental-body');
  check('初始渲染出 3 段（text/code/text）', body.children.length === 3, 'children=' + body.children.length);
  check('每段都记录了 node 引用', st.segs.every((s) => !!s.node));
  check('子节点数 == 段数', body.children.length === st.segs.length);
}

console.log('== B. 无变化渲染（切会话重挂载 / flush 重复调用）不能丢 node 引用 ==');
{
  const b = newBubble();
  api.render(b, T1);
  api.render(b, T1);   // 同样的文本再渲染一次 —— 事故触发点
  const st = b._incr;
  const body = b.querySelector('.md-incremental-body');
  check('无变化渲染没有动 DOM', body.children.length === 3);
  check('无变化渲染后 node 引用仍在（此前会全部丢失）', st.segs.every((s) => !!s.node),
    JSON.stringify(st.segs.map((s) => !!s.node)));
}

console.log('== C. 事故时序：无变化渲染 → 内容续写 → 不能出现两份 ==');
{
  const b = newBubble();
  api.render(b, T1);
  api.render(b, T1);            // 丢引用的那一步
  api.render(b, T2);            // 中段续写：旧中段必须被替换
  const body = b.querySelector('.md-incremental-body');
  check('旧段被替换（子节点数仍为 3）', body.children.length === 3, 'children=' + body.children.length);
  check('没有出现两份中段（MARK1 只出现一次）', countOf(body.textContent, 'MARK1') === 1,
    'MARK1 x' + countOf(body.textContent, 'MARK1'));
  check('续写内容在（MARK2 在）', countOf(body.textContent, 'MARK2') === 1);
}

console.log('== D. 连续流式更新：子节点数不膨胀 ==');
{
  const b = newBubble();
  let text = 'T' + NL + NL + '```' + NL + 'c' + NL + '```' + NL + NL + 'part-0';
  api.render(b, text);
  for (let i = 1; i <= 30; i++) {
    if (i % 3 === 0) api.render(b, text);                    // 夹杂无变化渲染
    text += ' +写' + i;
    api.render(b, text);
  }
  const st = b._incr;
  const body = b.querySelector('.md-incremental-body');
  check('30 轮更新后子节点数 == 段数（无膨胀）', body.children.length === st.segs.length,
    body.children.length + ' vs ' + st.segs.length);
  check('正文只有一份 part-0', countOf(body.textContent, 'part-0') === 1,
    'part-0 x' + countOf(body.textContent, 'part-0'));
}

console.log('== E. 失配兜底：DOM 里残留历史副本 → 下一次渲染必须清干净 ==');
{
  const b = newBubble();
  api.render(b, T1);
  const body = b.querySelector('.md-incremental-body');
  // 手工塞一份"历史事故"残留（旧版本节点留在 DOM 里）
  const orphan = new El('div');
  orphan.className = 'md-seg md-seg-text';
  orphan.textContent = '中段内容-MARK1';
  body.appendChild(orphan);
  check('先确认残留已塞进去（4 个子节点）', body.children.length === 4);
  api.render(b, T1);   // 同文本渲染 → 应识别失配并整块重建
  check('残留副本被清掉（回到 3 个子节点）', body.children.length === 3, 'children=' + body.children.length);
  check('正文只有一份 MARK1', countOf(body.textContent, 'MARK1') === 1,
    'MARK1 x' + countOf(body.textContent, 'MARK1'));
}

console.log('== F. 快照恢复：气泡里已有旧渲染块 → 复用，不新挂第二个 ==');
{
  const b = newBubble();
  // 模拟"刷新/切回后从快照 HTML 恢复"：DOM 里有一个渲染块，但没有 JS 状态
  const pre = new El('div');
  pre.className = 'md-incremental-body';
  const oldSeg = new El('div');
  oldSeg.className = 'md-seg md-seg-text';
  oldSeg.textContent = '恢复出来的旧内容-STALE';
  pre.appendChild(oldSeg);
  b.appendChild(pre);
  api.render(b, T1);
  const bodies = b.querySelectorAll('.md-incremental-body');
  check('渲染块只有一个（没有新挂第二个）', bodies.length === 1, 'bodies=' + bodies.length);
  check('旧内容被当前全文重建掉（STALE 消失）', countOf(b.textContent, 'STALE') === 0);
  check('当前全文在（MARK1 只有一份）', countOf(b.textContent, 'MARK1') === 1);
}

console.log('== G. 文本回退（段变少）：多余旧节点要被删掉 ==');
{
  const b = newBubble();
  api.render(b, T2);
  api.render(b, '只剩一段了。');   // 没有任何 fence → 只 1 段
  const st = b._incr;
  const body = b.querySelector('.md-incremental-body');
  check('子节点数 == 段数（1）', body.children.length === 1, 'children=' + body.children.length);
  check('旧 code 段已删掉', countOf(body.textContent, 'code-one') === 0);
  check('段数记录同步', st.segs.length === 1);
}

console.log('== H. 已「过程/结论分层」收尾的气泡：不能再挂第二份 ==');
{
  const b = newBubble();
  // 模拟 _splitProcessConclusion 的产物：折叠块 + 结论正文，没有增量渲染块
  const proc = new El('div');
  proc.className = 'proc-block';
  proc.textContent = '①② 阶段小结';
  const concl = new El('div');
  concl.className = 'md-seg md-seg-text';
  concl.textContent = '结论正文';
  b.appendChild(proc);
  b.appendChild(concl);
  const before = b.children.length;
  api.render(b, T1);   // 若没有守卫 → 会再挂一个渲染块，整稿重复出现在结论下面
  const bodies = b.querySelectorAll('.md-incremental-body');
  check('不新挂渲染块（结构保持不变）', bodies.length === 0 && b.children.length === before,
    'children=' + b.children.length + ' bodies=' + bodies.length);
  check('正文没有再冒出一份 MARK1', countOf(b.textContent, 'MARK1') === 0);
}

console.log(NL + '----');
console.log(pass + ' pass, ' + fail + ' fail');
process.exit(fail ? 1 : 0);