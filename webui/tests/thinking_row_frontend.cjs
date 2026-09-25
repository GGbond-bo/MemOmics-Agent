#!/usr/bin/env node
// 思考行（💭「思考过程」那一行）前端行为测试（2026-09-25）
// 需求（用户原话）：💭 思考过程那一行 —— 不应该新建一行；默认只显示最新一条思考、快速闪过；
//                   点开可以看到全文，而且运行中能看到持续更新的内容。
// 做法：把 webui/index.html 里真实的函数抠出来，在最小 DOM 桩上跑（index.html 没有构建步骤）。
// 桩 DOM 会模拟布局（scrollHeight 由文字长度算出来）和浏览器对 scrollTop 的夹取，
// 这样"先判断贴底、再写内容"的顺序 bug 才测得出来。
'use strict';
const fs = require('fs');
const path = require('path');
const NL = String.fromCharCode(10);
const HTML_PATH = process.env.THINK_INDEX_HTML || path.join(__dirname, '..', 'index.html');
const HTML = fs.readFileSync(HTML_PATH, 'utf8');

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  ok   ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra === undefined ? '' : '  -> ' + extra)); }
}

// ---- 从 index.html 抠真实代码 ----
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
function grabVar(name) {
  const i = HTML.indexOf('var ' + name + ' =');
  if (i < 0) throw new Error('找不到变量 ' + name);
  return HTML.slice(i, HTML.indexOf(NL, i));
}

// ---- 最小 DOM 桩（含布局模拟）----
function classListOf(el) {
  return {
    add: function (c) { el._ops.push('add:' + c); const s = el.className ? el.className.split(' ') : []; if (s.indexOf(c) < 0) s.push(c); el.className = s.filter(Boolean).join(' '); },
    remove: function (c) { el._ops.push('remove:' + c); el.className = (el.className ? el.className.split(' ') : []).filter(function (x) { return x && x !== c; }).join(' '); },
    contains: function (c) { return (el.className ? el.className.split(' ') : []).indexOf(c) >= 0; },
    toggle: function (c, on) { if (on === undefined) on = !this.contains(c); if (on) this.add(c); else this.remove(c); }
  };
}
function MiniEl(tag) {
  this.tagName = String(tag || 'div').toUpperCase();
  this.className = '';
  this.children = [];
  this.textContent = '';
  this.open = false;
  this.clientHeight = 0;
  this._scrollH = 0; this._scrollTop = 0;
  this._ops = []; this._reflows = 0;
  this._listeners = {};
  this.classList = classListOf(this);
  const self = this;
  Object.defineProperty(this, 'offsetWidth', { get: function () { self._reflows++; return 0; } });
}
Object.defineProperty(MiniEl.prototype, 'scrollHeight', {
  get: function () {
    // _autoLayout 的元素按文字长度算高度（20 字一行、每行 12px），模拟真实排版
    if (this._autoLayout) return Math.ceil(String(this.textContent || '').length / 20) * 12;
    return this._scrollH;
  },
  set: function (v) { this._scrollH = v; }
});
Object.defineProperty(MiniEl.prototype, 'scrollTop', {
  get: function () { return this._scrollTop; },
  // 浏览器会把 scrollTop 夹在 [0, scrollHeight - clientHeight]
  set: function (v) { this._scrollTop = Math.min(Math.max(0, v), Math.max(0, this.scrollHeight - this.clientHeight)); }
});
function matchesSel(el, sel) {
  const s = String(sel || '');
  if (s.charAt(0) === '#') return el.id === s.slice(1);
  const parts = s.split('.').filter(Boolean);          // 支持 .a.b 复合类选择器
  const cls = (el.className || '').split(' ');
  return parts.length > 0 && parts.every(function (p) { return cls.indexOf(p) >= 0; });
}
MiniEl.prototype.querySelector = function (sel) {
  for (let i = 0; i < this.children.length; i++) {
    const c = this.children[i];
    if (matchesSel(c, sel)) return c;
    const d = c.querySelector(sel);
    if (d) return d;
  }
  return null;
};
MiniEl.prototype.querySelectorAll = function (sel) {
  const out = [];
  for (let i = 0; i < this.children.length; i++) {
    const c = this.children[i];
    if (matchesSel(c, sel)) out.push(c);
    out.push.apply(out, c.querySelectorAll(sel));
  }
  return out;
};
MiniEl.prototype.appendChild = function (el) { this.children.push(el); el.parentNode = this; return el; };
MiniEl.prototype.addEventListener = function (t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); };
MiniEl.prototype.fire = function (t) { (this._listeners[t] || []).forEach(function (fn) { fn({ type: t }); }); };
Object.defineProperty(MiniEl.prototype, 'innerHTML', {
  get: function () { return this._html || ''; },
  set: function (v) {
    this._html = String(v);
    this.children = [];
    const re = /<(span|div)(?: class="([^"]*)")?>([^<]*)<\/\1>/g;
    let m;
    while ((m = re.exec(this._html))) {
      const el = new MiniEl(m[1]);
      el.className = m[2] || '';
      el.textContent = m[3] || '';
      this.children.push(el);
    }
  }
});
// 一条回答消息（.message.assistant > .bubble）
function Assistant() {
  MiniEl.call(this, 'div');
  this.className = 'message assistant';
  const self = this;
  this.bubble = new MiniEl('div');
  this.bubble.className = 'bubble';
  this.bubble.before = function (el) { self.children.push(el); el.parentNode = self; el._beforeBubble = true; };
  this.appendChild(this.bubble);
}
Assistant.prototype = Object.create(MiniEl.prototype);
Assistant.prototype.constructor = Assistant;

let scrollBottomCalls = 0;
const messagesBox = new MiniEl('div');
messagesBox.id = 'messages';
const assistants = [];
const documentStub = {
  createElement: function (tag) { return new MiniEl(tag); },
  getElementById: function (id) { return id === 'messages' ? messagesBox : null; },
  querySelectorAll: function (sel) {
    if (sel === '#messages .message.assistant') return messagesBox.querySelectorAll('.assistant');
    return [];
  }
};
const env = {
  document: documentStub,
  addAssistantMsg: function () { const a = new Assistant(); assistants.push(a); messagesBox.appendChild(a); return a; },
  scrollBottom: function () { scrollBottomCalls++; }
};

// ---- 组装被测代码 ----
const code = [
  grabVar('_THINK_PREFIX_RE'), grabVar('_rbLineShown'),
  grab('_thinkLineIn'), grab('_thinkLatestLine'), grab('_rbFlash'), grab('_rbMetaText'),
  grab('_rbMakeBlock'), grab('_rbAttach'), grab('_rbRestoreHistoryRow'), grab('_rbRender'),
  grab('updateReasoningBlock'), grab('finishReasoningBlock')
].join(NL);

const factory = new Function('env', [
  'var document = env.document;',
  'var currentAssistantEl = null, currentBubble = null;',
  'var agentRunning = false, reasoningText = "";',
  'var addAssistantMsg = env.addAssistantMsg, scrollBottom = env.scrollBottom;',
  code,
  'return {',
  '  api: { update: updateReasoningBlock, finish: finishReasoningBlock, latest: _thinkLatestLine, restore: _rbRestoreHistoryRow, attach: _rbAttach },',
  '  setAssistant: function (a) { currentAssistantEl = a; currentBubble = a ? a.querySelector(".bubble") : null; },',
  '  getAssistant: function () { return currentAssistantEl; },',
  '  setText: function (t) { reasoningText = t; },',
  '  getText: function () { return reasoningText; },',
  '  setRunning: function (r) { agentRunning = r; }',
  '};'
].join(NL));

function newEnv() { return factory(env); }
function fresh(assistant, text, running) {
  const e = newEnv();
  const a = assistant || new Assistant();
  if (!assistant) { assistants.push(a); messagesBox.appendChild(a); }
  e.setAssistant(a);
  e.setText(text || '');
  e.setRunning(!!running);
  return { e: e, a: a };
}
function blockOf(a) { return a.querySelector('.reasoning-block'); }
function blockCount(a) { return a.querySelectorAll('.reasoning-block').length; }
function flashAdds(el) { return el._ops.filter(function (o) { return o === 'add:rb-flash'; }).length; }

console.log('== A. 结构：就是原来那一行，没有新建行 ==');
{
  const { e, a } = fresh(null, '第一行' + NL + '最新一行', true);
  e.api.update(true);
  const b = blockOf(a);
  check('创建 details.reasoning-block', !!b && b.tagName === 'DETAILS', b && b.tagName);
  check('摘要里有 💭 图标', !!b.querySelector('.rb-icon') && b.querySelector('.rb-icon').textContent === '💭');
  check('摘要里有最新思考文本节点', !!b.querySelector('.rb-text'));
  check('摘要里有 展开/收起 提示', !!b.querySelector('.rb-meta'));
  check('全文容器仍是 .reasoning-content', !!b.querySelector('.reasoning-content'));
  check('插在回答气泡之前（不是新起一行在输入框那边）', b._beforeBubble === true);
  e.api.update(true); e.api.update(true);
  check('反复更新只创建一次 details', blockCount(a) === 1, blockCount(a));
}

console.log('== B. 默认只显示最新一条 ==');
{
  const { e, a } = fresh(null, '第一行思考' + NL + '- 第二行带列表前缀' + NL + '最新一行：直接跑 pwd。', true);
  e.api.update(true);
  const txt = blockOf(a).querySelector('.rb-text');
  check('摘要只显示最后一行', txt.textContent === '最新一行：直接跑 pwd。', txt.textContent);
  check('列表前缀被剥掉（- ）', e.api.latest('- 跑一下 pwd') === '跑一下 pwd');
  check('引用前缀被剥掉（> ）', e.api.latest('> 看目录') === '看目录');
  check('序号前缀被剥掉（1. ）', e.api.latest('1. 看目录') === '看目录');
  check('普通正文原样保留', e.api.latest('看目录即可') === '看目录即可');
  check('正文里的年份数字不被吃', e.api.latest('2026 年要发版') === '2026 年要发版', e.api.latest('2026 年要发版'));
  const long = 'x'.repeat(300);
  e.setText(long); e.api.update(true);
  const t2 = blockOf(a).querySelector('.rb-text').textContent;
  check('超长行截断到 161 字且带省略号', t2.length === 161 && t2.charAt(0) === '…', t2.length);
  e.setText(''); e.api.update(true);
  check('没有思考时回到「思考过程」', blockOf(a).querySelector('.rb-text').textContent === '思考过程');
}

console.log('== C. 快速闪过：只在末行变化时闪一次 ==');
{
  const { e, a } = fresh(null, '第一行', true);
  e.api.update(true);
  const txt = blockOf(a).querySelector('.rb-text');
  check('首次出现会闪一次', flashAdds(txt) === 1, flashAdds(txt));
  check('闪之前强制重排（能重放同一动画）', txt._reflows >= 1, txt._reflows);
  e.api.update(true); e.api.update(true);
  check('末行没变 → 不重复闪（不抖）', flashAdds(txt) === 1, flashAdds(txt));
  e.setText('第一行' + NL + '第二行');
  e.api.update(true);
  check('末行变了 → 再闪一次', flashAdds(txt) === 2, flashAdds(txt));
  check('文字也跟着更新', txt.textContent === '第二行', txt.textContent);
}

console.log('== D. 点开看全文 + 运行中持续更新 ==');
{
  const { e, a } = fresh(null, '第一行' + NL + '第二行', true);
  e.api.update(true);
  const b = blockOf(a), content = b.querySelector('.reasoning-content'), meta = b.querySelector('.rb-meta');
  check('全文内容 = reasoningText（含换行）', content.textContent === '第一行' + NL + '第二行', JSON.stringify(content.textContent));
  check('收起态提示 = 展开 · N 字', meta.textContent === '展开 · ' + e.getText().length + ' 字', meta.textContent);
  b.open = true;
  b.fire('toggle');
  check('点开后提示变「收起 · N 字」', meta.textContent === '收起 · ' + e.getText().length + ' 字', meta.textContent);

  // 真排版模拟：内容一直变长，每次更新都应该贴底（顺序写反就会从第一次变长起永远跟不上）
  content._autoLayout = true; content.clientHeight = 300;
  let n = 0, follows = 0;
  for (let i = 0; i < 12; i++) {
    e.setText(e.getText() + '思考内容'.repeat(40));
    e.api.update(true);
    if (content.scrollHeight > content.clientHeight) {
      n++;
      if (Math.abs(content.scrollTop + content.clientHeight - content.scrollHeight) < 2) follows++;
    }
  }
  check('内容变长后每次都自动跟到最新', n > 0 && follows === n, follows + '/' + n);
  check('全文随流式更新增长', content.textContent.indexOf('思考内容') > 0);
  content.scrollTop = 0;   // 用户自己往上翻到顶
  e.setText(e.getText() + NL + '又一段');
  e.api.update(true);
  check('用户往上翻时不抢滚动位置', content.scrollTop === 0, content.scrollTop);
  content.scrollTop = content.scrollHeight;   // 用户又滑回底部
  e.setText(e.getText() + NL + '再一段');
  e.api.update(true);
  check('用户滑回底部后恢复跟随', Math.abs(content.scrollTop + content.clientHeight - content.scrollHeight) < 2, content.scrollTop);
  b.open = false;
  content.scrollTop = 0;
  e.setText(e.getText() + NL + '第五行');
  e.api.update(true);
  check('收起状态不自动滚动', content.scrollTop === 0, content.scrollTop);
  check('收起时全文照样在更新', content.textContent.indexOf('第五行') > 0);
}

console.log('== E. 收尾 ==');
{
  const { e, a } = fresh(null, '想完了', true);
  e.api.update(true);
  const b = blockOf(a);
  check('运行中有 running 标记（图标呼吸）', b.classList.contains('running'));
  e.setRunning(false);
  e.api.finish();
  check('收尾后 running 标记移除', !b.classList.contains('running'));
  check('收尾后提示带字数', b.querySelector('.rb-meta').textContent === '展开 · ' + e.getText().length + ' 字', b.querySelector('.rb-meta').textContent);
  check('收尾后全文仍在（可点开看）', b.querySelector('.reasoning-content').textContent === '想完了');
  const before = assistants.length;
  e.setAssistant(null);
  let threw = null;
  try { e.api.finish(); } catch (err) { threw = String(err); }
  check('没有气泡时收尾不报错', threw === null, threw);
  check('没有气泡时收尾不新建空气泡', assistants.length === before, assistants.length - before);
}

console.log('== F. 新气泡 / 刷新切会话回放 ==');
{
  const { e, a } = fresh(null, '第一轮思考', true);
  e.api.update(true);
  const a2 = new Assistant(); assistants.push(a2); messagesBox.appendChild(a2);
  e.setAssistant(a2);
  e.api.update(true);
  const txt2 = blockOf(a2).querySelector('.rb-text');
  check('新气泡重新闪一次', flashAdds(txt2) === 1, flashAdds(txt2));
  check('新气泡有自己的一份全文', blockOf(a2).querySelector('.reasoning-content').textContent === '第一轮思考');
  check('老气泡不受影响', blockOf(a).querySelector('.rb-text').textContent === '第一轮思考');

  // 回放已完成的任务：没有流式气泡 → 挂到最后一条真实回答上，不新建空气泡
  const e2 = newEnv();
  e2.setAssistant(null); e2.setRunning(false);
  e2.setText('历史思考第一行' + NL + '历史思考最后一行');
  const before = assistants.length;
  const lastHist = messagesBox.querySelectorAll('.assistant').slice(-1)[0];
  e2.api.update(false);
  check('回放不新建空气泡', assistants.length === before, assistants.length - before);
  check('回放挂到最后一条回答上', !!lastHist.querySelector('.reasoning-block'));
  check('回放行显示最后一行', lastHist.querySelector('.rb-text').textContent === '历史思考最后一行', lastHist.querySelector('.rb-text').textContent);
  check('回放行字数按自己那份算', lastHist.querySelector('.rb-meta').textContent === '展开 · ' + e2.getText().length + ' 字', lastHist.querySelector('.rb-meta').textContent);
  check('回放行也是收起态（默认不展开）', lastHist.querySelector('.reasoning-block').open === false);

  // _rbAttach 幂等 + 不覆盖已有行
  const host = new Assistant();
  const b1 = e2.api.attach(host, '挂一次', false);
  const b2 = e2.api.attach(host, '挂第二次', false);
  check('_rbAttach 幂等（同一宿主不重复挂）', b1 === b2 && host.querySelectorAll('.reasoning-block').length === 1);
  check('_rbAttach 挂在气泡之前', b1._beforeBubble === true);

  // _rbRestoreHistoryRow：干净消息区要挂上；已有 💭 行时不能重复挂
  const saved = messagesBox.children.slice();
  messagesBox.children = [];
  const host2 = new Assistant(); messagesBox.appendChild(host2);
  const e3 = newEnv();
  e3.setText('持久化思考'); e3.setRunning(false);
  let threw = null;
  try { e3.api.restore(); } catch (err) { threw = String(err); }
  check('历史恢复不报错', threw === null, threw);
  check('消息区没有 💭 行 → 挂到最后一条回答', !!host2.querySelector('.reasoning-block'));
  check('挂上的是这份持久化思考', host2.querySelector('.reasoning-content').textContent === '持久化思考');
  const cnt = messagesBox.querySelectorAll('.reasoning-block').length;
  e3.api.restore();
  check('已有 💭 行时不重复挂', messagesBox.querySelectorAll('.reasoning-block').length === cnt, messagesBox.querySelectorAll('.reasoning-block').length);
  messagesBox.children = saved;
  const e5 = newEnv();
  let threw2 = null;
  try { e5.api.restore(); } catch (err) { threw2 = String(err); }
  check('没有持久化思考时恢复是空操作', threw2 === null, threw2);
}

console.log('== G. 大文本 ==');
{
  const { e } = fresh(null, 'x', false);
  const big = ('这是一条很长的思考内容，用来压测尾部扫描。'.repeat(20) + NL).repeat(500) + '最后一行：收工。';
  e.setText(big);
  check('大文本也能取到真正的最后一行', e.api.latest(big) === '最后一行：收工。', e.api.latest(big).slice(0, 40));
  const t0 = Date.now();
  for (let i = 0; i < 2000; i++) { e.setText(big + 'x'.repeat(i % 7)); e.api.update(true); }
  const ms = Date.now() - t0;
  check('2000 次流式更新 < 400ms（真机数千条 reasoning 事件）', ms < 400, ms + 'ms');
  console.log('       (大文本 ' + big.length + ' 字，2000 次更新 ' + ms + 'ms)');
}

console.log(NL + '----');
console.log(pass + ' pass, ' + fail + ' fail');
process.exit(fail ? 1 : 0);
