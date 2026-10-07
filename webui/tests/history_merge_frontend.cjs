#!/usr/bin/env node
// 历史回放「同轮合并」前端行为测试（2026-10-07）
// 需求（用户原话）：交互框里一轮回答被拆成很多碎片气泡（每片各带 ⏱/🛠/📋 复制），
// 刷新页面或切走再回来必现；要求「原本怎么展示的，刷新/切回来还怎么展示」。
// 做法：把 webui/index.html 里真实的 _renderHistoryFlow / addUserMsg / addAssistantMsg
// 抠出来，在最小 DOM 桩上跑真实回放流程，断言与实时流同构：
//   · 同一轮 N 个 assistant 片段 → 恰好 1 个气泡（不是 N 个）
//   · 文本按原顺序拼接；耗时/工具数按整轮累加；一个气泡只有一个复制按钮
//   · 整轮无文本（纯工具调用）不生成空气泡
//   · msgEls 仍按源消息序号对齐（辩论卡片插入位置不受影响）
// 可选：HISTORY_FIXTURE=<json文件>（{"messages":[...]}）用真实会话数据跑同样的断言。
'use strict';
const fs = require('fs');
const path = require('path');
const NL = String.fromCharCode(10);
const HTML_PATH = process.env.HISTORY_INDEX_HTML || path.join(__dirname, '..', 'index.html');
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
function grabVar(name) {
  // 跨行 + 字符串感知：INJECT_PREFIXES 是两行数组，且元素里就带 '[' 字符，
  // 所以括号配平必须先跳过字符串字面量（否则被 ' [会话要求' 这类串带偏）。
  const i = HTML.indexOf('var ' + name + ' =');
  if (i < 0) throw new Error('找不到变量 ' + name);
  let depth = 0, seen = false, quote = '';
  for (let k = i; k < HTML.length; k++) {
    const c = HTML[k];
    if (quote) {
      if (c === '\\') { k++; continue; }
      if (c === quote) quote = '';
      continue;
    }
    if (c === "'" || c === '"') { quote = c; continue; }
    if (c === '[' || c === '{' || c === '(') { depth++; seen = true; }
    else if (c === ']' || c === '}' || c === ')') { depth--; if (seen && depth === 0) return HTML.slice(i, HTML.indexOf(';', k) + 1); }
    else if (c === ';' && !seen && depth === 0) return HTML.slice(i, k + 1);
  }
  throw new Error('变量没结束 ' + name);
}

// ---- 最小 DOM 桩 ----
function classListOf(el) {
  return {
    add: function (c) { const s = el.className ? el.className.split(' ') : []; if (s.indexOf(c) < 0) s.push(c); el.className = s.filter(Boolean).join(' '); },
    remove: function (c) { el.className = (el.className ? el.className.split(' ') : []).filter(function (x) { return x && x !== c; }).join(' '); },
    contains: function (c) { return (el.className ? el.className.split(' ') : []).indexOf(c) >= 0; }
  };
}
function MiniEl(tag) {
  this.tagName = String(tag || 'div').toUpperCase();
  this.className = ''; this.children = []; this.textContent = '';
  this._html = ''; this.id = '';
  this.classList = classListOf(this);
}
function matchesSel(el, sel) {
  const s = String(sel || '').trim();
  if (s === '.message.assistant') return (el.className || '').split(' ').indexOf('message') >= 0 && (el.className || '').split(' ').indexOf('assistant') >= 0;
  if (s === '.message.user') return (el.className || '').split(' ').indexOf('message') >= 0 && (el.className || '').split(' ').indexOf('user') >= 0;
  if (s === '.message') return (el.className || '').split(' ').indexOf('message') >= 0;
  if (s.charAt(0) === '#') return el.id === s.slice(1);
  const parts = s.split('.').filter(Boolean);
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
Object.defineProperty(MiniEl.prototype, 'lastElementChild', { get: function () { return this.children[this.children.length - 1] || null; } });
Object.defineProperty(MiniEl.prototype, 'innerHTML', {
  get: function () { return this._html; },
  set: function (v) { this._html = String(v); this.children = []; }
});

const messagesBox = new MiniEl('div');
messagesBox.id = 'messages';
const documentStub = {
  createElement: function (tag) { return new MiniEl(tag); },
  getElementById: function (id) { return id === 'messages' ? messagesBox : null; },
  querySelectorAll: function () { return []; },
  addEventListener: function () {}
};

const code = [
  grabVar('INJECT_PREFIXES'),
  grab('_isInjectMsg'),
  grab('_renderHistoryFlow'),
  grab('_fmtDur'),
  grabVar('_toolLabels'),
  grab('_toolLabel'),
  grab('addUserMsg'),
  grab('addAssistantMsg')
].join(NL);

const factory = new Function('env', [
  'var document = env.document, window = env.window, console = env.console;',
  'var escapeHtml = env.escapeHtml;',
  'var renderMarkdown = env.renderMarkdown, _citeWrapHtml = env._citeWrapHtml;',
  'var initMermaid = env.initMermaid, scrollBottom = env.scrollBottom;',
  'var _registerTurnEl = env._registerTurnEl, _turnSeq = 0;',
  code,
  'return { run: _renderHistoryFlow, box: env.document.getElementById("messages"),',
  '         addAssistantMsg: addAssistantMsg, addUserMsg: addUserMsg };'
].join(NL));

const env = {
  document: documentStub, window: {}, console: console,
  escapeHtml: function (s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); },
  renderMarkdown: function (t) { return String(t || ''); },
  _citeWrapHtml: function (h) { return h; },
  initMermaid: function () {}, scrollBottom: function () {},
  _registerTurnEl: function () {}
};
const api = factory(env);

function resetBox() { messagesBox.children = []; messagesBox._html = ''; }
function bubbles() { return messagesBox.querySelectorAll('.message.assistant'); }
function userBubbles() { return messagesBox.querySelectorAll('.message.user'); }
function copyBtnCount(el) { return (el._html.match(/copy-btn/g) || []).length; }

// ---- 1) 用户报告的场景：同一轮 5 个片段（含空片段）→ 1 个气泡 ----
console.log('1) 同轮 5 片段（用户截图场景）');
resetBox();
const seg = [
  { role: 'user', content: '帮我把 5 处引文缺陷修掉', turn: 1 },
  { role: 'assistant', content: 'Diagnosis is clear — same defect class as n=34.', turn: 1, elapsed: 9, tool_count: 1, tool_names: ['read_file'] },
  { role: 'assistant', content: 'Both builders are source-driven.', turn: 1, elapsed: 53, tool_count: 1, tool_names: ['execute_python'] },
  { role: 'assistant', content: 'Full picture: 5 strict failures.', turn: 1, elapsed: 9, tool_count: 1, tool_names: ['read_file'] },
  { role: 'assistant', content: '(empty)', turn: 1, elapsed: 6, tool_count: 2, tool_names: ['terminal', 'read_file'] },
  { role: 'assistant', content: 'Now writing the fix script.', turn: 1, elapsed: 8, tool_count: 1, tool_names: ['write_file'] }
];
let els = api.run(seg);
let bs = bubbles();
check('同一轮 = 1 个回答气泡（原来会是 5 个）', bs.length === 1, '实际 ' + bs.length);
check('用户气泡 1 个', userBubbles().length === 1);
check('文本按顺序拼接', bs.length === 1 &&
  bs[0]._html.indexOf('Diagnosis is clear') < bs[0]._html.indexOf('Both builders are source-driven') &&
  bs[0]._html.indexOf('Both builders') < bs[0]._html.indexOf('Full picture') &&
  bs[0]._html.indexOf('Full picture') < bs[0]._html.indexOf('Now writing the fix script'));
check('片段之间有段落分隔', bs.length === 1 && /Diagnosis is clear[^<]*\n\nBoth builders/.test(bs[0]._html), JSON.stringify((bs[0]._html || '').slice(0, 120)));
check('只有 1 个复制按钮', bs.length === 1 && copyBtnCount(bs[0]) === 1, bs.length ? copyBtnCount(bs[0]) : 'n/a');
check('工具数按整轮累加 = 6', bs.length === 1 && bs[0]._html.indexOf('🛠 6 次工具调用') >= 0);
check('耗时按整轮累加 = 1:25', bs.length === 1 && bs[0]._html.indexOf('⏱ 1:25') >= 0, (bs[0]._html.match(/⏱[^<·]*/) || [''])[0]);
check('工具名去重合并', bs.length === 1 && (bs[0]._html.match(/工具调用/g) || []).length === 1);
check('空响应哨兵 "(empty)" 不进正文', bs.length === 1 && bs[0]._html.indexOf('(empty)') < 0, (bs[0]._html || '').slice(0, 200));

// ---- 2) msgEls 索引对齐（辩论卡片插入依赖它） ----
console.log('2) msgEls 索引对齐');
check('用户下标 → 用户气泡', els[0] === userBubbles()[0]);
check('被合并的片段都指向同一个气泡元素', els[1] === bs[0] && els[2] === bs[0] && els[3] === bs[0] && els[5] === bs[0]);
check('顺序：气泡在用户消息之后', messagesBox.children[0] === userBubbles()[0] && messagesBox.children[1] === bs[0]);

// ---- 3) 两轮 + 注入消息：轮与轮之间不合并 ----
console.log('3) 两轮不互相合并 + 注入消息不进对话流');
resetBox();
els = api.run([
  { role: 'user', content: '第一问', turn: 1 },
  { role: 'assistant', content: 'A1', turn: 1, tool_count: 1 },
  { role: 'assistant', content: 'A2', turn: 1, tool_count: 1 },
  { role: 'user', content: '[系统唤醒] 自检', turn: 2 },
  { role: 'assistant', content: 'B1', turn: 2, tool_count: 2 },
  { role: 'system', content: 'x' },
  { role: 'user', content: '第二问', turn: 3 },
  { role: 'assistant', content: 'C1', turn: 3, tool_count: 0 }
]);
bs = bubbles();
check('3 轮 = 3 个回答气泡', bs.length === 3, '实际 ' + bs.length);
check('用户气泡只算非注入的 2 个', userBubbles().length === 2, '实际 ' + userBubbles().length);
check('注入消息的槽位没有元素', els[3] === null || els[3] === undefined || els[3].className === '' || (String(els[3].className || '').indexOf('user') < 0 && String(els[3].className || '').indexOf('assistant') < 0), String(els[3] && els[3].className));
check('纯工具轮不生成空气泡', messagesBox.querySelectorAll('.message.assistant').length === 3);

// ---- 4) 整轮无文本（哨兵/空白）→ 不生成空气泡（实时流同样什么都不显示） ----
console.log('4) 纯工具轮不生成空气泡');
resetBox();
els = api.run([
  { role: 'assistant', content: '(empty)', turn: 0, tool_count: 3 },
  { role: 'assistant', content: '', turn: 0, tool_count: 1 },
  { role: 'assistant', content: '   ', turn: 0, tool_count: 1 }
]);
check('无文本 → 0 个气泡', bubbles().length === 0, '实际 ' + bubbles().length);
check('哨兵/空白都不渲染', messagesBox.children.length === 0);

// ---- 5) 真实会话数据（可选 fixture，CI 里没有就跳过） ----
const fxPath = process.env.HISTORY_FIXTURE;
if (fxPath && fs.existsSync(fxPath)) {
  console.log('5) 真实会话数据：' + fxPath);
  const fx = JSON.parse(fs.readFileSync(fxPath, 'utf8').replace(/^\uFEFF/, ''));
  const msgs = fx.messages || [];
  resetBox();
  const els2 = api.run(msgs);
  const assMsgs = msgs.filter(function (m) { return m.role === 'assistant' && !(m.content || '').trim().startsWith('[系统唤醒'); });
  const rendered = bubbles();
  const rounds = new Set(assMsgs.map(function (m) { return m.turn || 0; })).size;
  check('气泡数 = 轮数（不再=片段数）', rendered.length === rounds, '气泡 ' + rendered.length + ' / 轮 ' + rounds + ' / 片段 ' + assMsgs.length);
  check('确实减少（碎片被合并）', rendered.length < assMsgs.length, '气泡 ' + rendered.length + ' vs 片段 ' + assMsgs.length);
  check('每个气泡只有一个复制按钮', rendered.every(function (el) { return copyBtnCount(el) === 1; }));
  check('没有空气泡', rendered.every(function (el) { return String(el._html || '').length > 80; }));
  check('msgEls 与消息数等长', els2.length === msgs.length, els2.length + ' vs ' + msgs.length);
  const nonEmpty = assMsgs.filter(function (m) { return (m.content || '').trim() && String(m.content).trim() !== '(empty)'; });
  check('所有非空片段文本都进了某个气泡', nonEmpty.every(function (m) {
    const t = String(m.content).trim().slice(0, 24);
    return rendered.some(function (el) { return String(el._html || '').indexOf(t) >= 0; });
  }));
} else {
  console.log('5) 跳过真实数据（未提供 HISTORY_FIXTURE）');
}

console.log(NL + pass + ' pass, ' + fail + ' fail');
process.exit(fail ? 1 : 0);