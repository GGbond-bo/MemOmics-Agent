/* Offline regressions for the left-side, user-question conversation rail. */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const railStart = html.indexOf('// === 会话问题导航');
const railEnd = html.indexOf('// === 待办 ===', railStart);
assert.ok(railStart >= 0 && railEnd > railStart, 'conversation rail source must stay isolated before the todo module');
const railSource = html.slice(railStart, railEnd);

assert.match(html, /class="chat-history-shell"[\s\S]*?<nav id="turn-nav"[\s\S]*?<div class="chat-messages" id="messages">/, 'the rail sits beside—not inside—the unchanged messages scroll container');
assert.doesNotMatch(html, /id="outline-list"|id="outline-count"/, 'the old right-side outline DOM is removed');
assert.match(html, /@media \(max-width:760px\) \{ #turn-nav \{ display:none; \}/, 'narrow layouts hide the rail instead of covering message text');
assert.match(html, /#turn-nav \{[^}]*align-items:center[^}]*justify-content:center/, 'a short rail stays vertically centered beside the message viewport');
assert.match(html, /#turn-nav-list \{[^}]*max-height:100%[^}]*overflow-y:auto/, 'a long rail naturally overflows within its own scrollable list');
assert.match(html, /#turn-nav-list \{[^}]*min-height:0[^}]*flex-shrink:0/, 'an oversized rail starts from a reachable top edge instead of negative centering');
assert.match(html, /\.turn-nav-tick \{[^}]*font-size:0/, 'visual ticks do not permanently display outline numbers');
assert.match(html, /\.turn-nav-tick:hover, \.turn-nav-tick:focus-visible, \.turn-nav-tick\.active \{[^}]*width:22px/, 'hover, keyboard focus, and active ticks lengthen like short Codex-style marks');
assert.match(html, /\.turn-nav-tick:focus-visible::after/, 'keyboard focus expands the same summary available on hover');
assert.match(html, /\.turn-nav-tick\.active\.streaming/, 'only the current tick receives the restrained streaming feedback class');
assert.match(html, /@media \(prefers-reduced-motion:reduce\)/, 'reduced-motion users can disable rail and flash animation');
assert.match(html, /function _restoreSessionSnapshot[\s\S]*?_outlineDirty/, 'snapshot restore explicitly rebuilds the rail');
assert.match(html, /function loadAllMessages[\s\S]*?_outlineDirty/, 'full-history rendering explicitly rebuilds the rail');
assert.match(html, /innerHTML = '';[\s\S]*?_resetConversationRail\(sid\)/, 'session switches reset rail state when message DOM is cleared');

class ClassList {
  constructor(owner) { this.owner = owner; this.values = new Set(); }
  add(...names) { names.filter(Boolean).forEach((name) => this.values.add(name)); }
  remove(...names) { names.forEach((name) => this.values.delete(name)); }
  contains(name) { return this.values.has(name); }
  toggle(name, on) { if (on === undefined ? !this.contains(name) : on) this.add(name); else this.remove(name); return this.contains(name); }
  toString() { return [...this.values].join(' '); }
}

function descendants(root, output = []) {
  for (const child of root.children || []) { output.push(child); descendants(child, output); }
  return output;
}

function matches(node, selector) {
  if (!node || !node.tagName) return false;
  const attr = selector.match(/\[([\w-]+)(?:="([^"]*)")?\]/);
  const beforeAttr = selector.replace(/\[[^\]]+\]/g, '');
  const id = beforeAttr.match(/#([\w-]+)/);
  const classes = [...beforeAttr.matchAll(/\.([\w-]+)/g)].map((match) => match[1]);
  if (id && node.id !== id[1]) return false;
  if (classes.some((name) => !node.classList.contains(name))) return false;
  if (attr) {
    const value = node.getAttribute(attr[1]);
    if (value == null || (attr[2] !== undefined && value !== attr[2])) return false;
  }
  return true;
}

class Element {
  constructor(tag = 'div') {
    this.tagName = String(tag).toUpperCase(); this.children = []; this.parentNode = null;
    this.classList = new ClassList(this); this.attributes = new Map(); this._listeners = {};
    this._innerHTML = ''; this.textContent = ''; this.title = ''; this.id = ''; this.type = '';
    this.style = {}; this.scrollTop = 0; this.clientHeight = 160; this.offsetTop = 0; this.offsetWidth = 1;
    this._rect = { top: 0, bottom: 30 }; this.scrolled = 0;
  }
  get className() { return this.classList.toString(); }
  set className(value) { this.classList.values = new Set(String(value || '').split(/\s+/).filter(Boolean)); }
  get innerHTML() { return this._innerHTML; }
  set innerHTML(value) { this._innerHTML = String(value); this.children = []; }
  get childNodes() { return this.children; }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  insertBefore(child, before) { child.parentNode = this; const at = this.children.indexOf(before); if (at >= 0) this.children.splice(at, 0, child); else this.children.push(child); return child; }
  remove() { if (this.parentNode) { this.parentNode.children = this.parentNode.children.filter((child) => child !== this); this.parentNode = null; } }
  setAttribute(name, value) { this.attributes.set(String(name), String(value)); if (name === 'id') this.id = String(value); }
  getAttribute(name) { if (name === 'id') return this.id || null; return this.attributes.has(name) ? this.attributes.get(name) : null; }
  querySelectorAll(selector) { return descendants(this).filter((node) => matches(node, selector)); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  addEventListener(type, handler) { (this._listeners[type] || (this._listeners[type] = [])).push(handler); }
  getBoundingClientRect() { return this._rect; }
  scrollIntoView(options) { this.scrolled++; this.scrollOptions = options; }
}

const body = new Element('body');
const shell = new Element('div'); shell.className = 'chat-history-shell';
const nav = new Element('nav'); nav.id = 'turn-nav';
const rail = new Element('div'); rail.id = 'turn-nav-list';
const messages = new Element('div'); messages.id = 'messages'; messages.className = 'chat-messages';
nav.appendChild(rail); shell.appendChild(nav); shell.appendChild(messages); body.appendChild(shell);

const timers = new Map(); let nextTimer = 1;
const frames = []; let gotoBottomRefreshes = 0; const loadCalls = [];
const document = {
  body, documentElement: { lang: 'zh-CN' },
  createElement: (tag) => new Element(tag),
  getElementById: (id) => [body, ...descendants(body)].find((node) => node.id === id) || null,
  querySelector: (selector) => body.querySelector(selector),
};
const context = {
  console, Math, String, Number, Array, Object, parseInt, isNaN,
  document, currentSid: 'chat-a', _autoScroll: true,
  setTimeout(callback) { const id = nextTimer++; timers.set(id, callback); return id; },
  clearTimeout(id) { timers.delete(id); },
  _refreshGotoBottom: () => { gotoBottomRefreshes++; },
  loadAllMessages: (sid) => loadCalls.push(sid),
};
context.window = context;
context.window.requestAnimationFrame = (callback) => { frames.push(callback); return frames.length; };
vm.createContext(context);
vm.runInContext(railSource, context, { filename: 'conversation-rail.js' });

function flushTimers() {
  const jobs = [...timers.values()]; timers.clear(); jobs.forEach((job) => job());
}
function runFrames() { const jobs = frames.splice(0); jobs.forEach((job) => job()); }
function message(role, turn, text) {
  const row = new Element('div'); row.className = `message ${role}`; row.setAttribute('data-turn', String(turn));
  const bubble = new Element('div'); bubble.className = 'bubble'; bubble.appendChild({ nodeType: 3, textContent: text, parentNode: bubble });
  row.appendChild(bubble); return row;
}

// Only user questions create ticks.  Assistant/tool-like rows sharing the turn
// stay navigable as conversation content but never become false questions.
const user1 = message('user', 1, '第一问：<script>不应执行</script>');
const assistant1 = message('assistant', 1, '回答一');
const tool1 = message('tool', 1, 'tool output');
const user2 = message('user', 2, '第二问：如何继续？');
messages.appendChild(user1); messages.appendChild(assistant1); messages.appendChild(tool1); messages.appendChild(user2);
context._registerTurnEl(user1, 1, 'user');
context._registerTurnEl(assistant1, 1, 'assistant');
context._registerTurnEl(user2, 2, 'user');
flushTimers();
let ticks = rail.querySelectorAll('.turn-nav-tick');
assert.equal(ticks.length, 2, 'one tick is rendered for each user question only');
assert.equal(ticks[0].textContent, '', 'the visual rail is a short mark, while title/ARIA retain the question number');
assert.match(ticks[0].title, /第1问：第一问：<script>/, 'hover title contains the real question summary as text');
assert.match(ticks[0].getAttribute('aria-label'), /第1问：/, 'screen readers retain the numbered question summary');
assert.equal(ticks[0].getAttribute('data-summary'), '第一问：<script>不应执行</script>', 'summary is held in a DOM attribute rather than interpolated HTML');

ticks[1].onclick();
assert.equal(user2.scrolled, 1, 'clicking a tick reuses turn jump navigation');
assert.equal(context._autoScroll, false, 'turn jump disables automatic bottom-following');
assert.equal(gotoBottomRefreshes, 1, 'turn jump refreshes the existing return-to-bottom control');
user2.classList.remove('turn-flash');
context.window.matchMedia = () => ({ matches: true });
ticks[1].onclick();
assert.equal(user2.scrollOptions.behavior, 'auto', 'reduced-motion navigation does not smooth-scroll');
assert.equal(user2.classList.contains('turn-flash'), false, 'reduced-motion navigation does not start the flash animation');
delete context.window.matchMedia;

// A scroll burst owns one rAF.  While a long assistant answer fills the
// viewport between Q1 and Q2, active state stays on the latest question that
// has crossed the viewport threshold; only after Q2 crosses does it advance.
user1._rect = { top: -40, bottom: -1 }; assistant1._rect = { top: -5, bottom: 500 }; user2._rect = { top: 520, bottom: 570 }; messages._rect = { top: 0, bottom: 300 };
for (let i = 0; i < 4; i++) (messages._listeners.scroll || [])[0]();
assert.equal(frames.length, 1, 'scroll bursts schedule one animation-frame sync');
runFrames();
assert.equal(context._activeTurn, 1, 'a long answer between questions keeps Q1 active instead of jumping ahead to Q2');
user2._rect = { top: 5, bottom: 55 };
(messages._listeners.scroll || [])[0](); runFrames();
assert.equal(context._activeTurn, 2, 'active state advances when Q2 itself crosses the viewport threshold');
assert.ok(rail.querySelectorAll('.turn-nav-tick').find((tick) => tick.getAttribute('data-turn') === '2').classList.contains('active'), 'crossed turn gets the active tick style');
context._setConversationRailStreaming(true, 'chat-a');
const activeStreamingTick = rail.querySelectorAll('.turn-nav-tick').find((tick) => tick.getAttribute('data-turn') === '2');
assert.equal(activeStreamingTick.classList.contains('streaming'), true, 'an active stream animates only the current question tick');
assert.equal(activeStreamingTick.getAttribute('aria-busy'), 'true', 'streaming state is exposed without adding permanent visual labels');
context._setConversationRailStreaming(false, 'chat-a');
assert.equal(activeStreamingTick.classList.contains('streaming'), false, 'terminal stream state clears the current tick feedback');

context._registerTurnEl(message('user', 3, 'late A'), 3, 'user');
context.currentSid = 'chat-b';
context._resetConversationRail('chat-b');
flushTimers();
assert.equal(rail.querySelectorAll('.turn-nav-tick').length, 0, 'switching sid clears the old rail before any late dirty callback');

// Snapshot/history restoration is represented by replacing messages DOM, then
// rebuilding from its original data-turn values without reordering them.
messages.innerHTML = '';
const restored = message('user', 9, 'B 的历史问题'); messages.appendChild(restored);
context._outlineDirty(); flushTimers();
ticks = rail.querySelectorAll('.turn-nav-tick');
assert.deepEqual(ticks.map((tick) => tick.getAttribute('data-turn')), ['9'], 'restored history rebuilds the rail from existing turn numbers');
assert.equal(context._turnSeq, 9, 'restored turn numbering seeds the next live user question');

const user10 = message('user', 10, 'B 的新问题'); const streamedAssistant = message('assistant', 10, 'stream delta');
messages.appendChild(user10); messages.appendChild(streamedAssistant);
context._registerTurnEl(user10, 10, 'user');
context._registerTurnEl(streamedAssistant, 10, 'assistant');
flushTimers();
assert.deepEqual(rail.querySelectorAll('.turn-nav-tick').map((tick) => tick.getAttribute('data-turn')), ['9', '10'], 'an assistant stream does not duplicate a user-question tick');

const moreHint = new Element('div'); moreHint.className = 'more-msgs-hint'; messages.insertBefore(moreHint, messages.children[0]);
context.refreshOutline();
const more = rail.querySelector('.turn-nav-more');
assert.ok(more, 'a truncated history exposes a top load-earlier marker');
more.onclick();
assert.deepEqual(loadCalls, ['chat-b'], 'load-earlier marker requests all messages only for the visible sid');
assert.equal(rail.querySelectorAll('.turn-nav-tick').length, 2, 'pagination marker never invents ticks for unrendered messages');

// A long history stays a list of compact marks rather than turning into a
// permanently numbered sidebar.  CSS owns its local scrolling/centering; the
// DOM remains one accessible tick per question.
for (let turn = 11; turn <= 72; turn++) {
  const row = message('user', turn, `历史问题 ${turn}`);
  messages.appendChild(row); context._registerTurnEl(row, turn, 'user');
}
flushTimers();
assert.equal(rail.querySelectorAll('.turn-nav-tick').length, 64, 'many questions retain compact one-per-question navigation marks');
assert.equal(rail.querySelectorAll('.turn-nav-tick').at(-1).textContent, '', 'large rail entries continue to suppress permanent visual numbers');

console.log('conversation_rail_ui.test.js: PASS');
