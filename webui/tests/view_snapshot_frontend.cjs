#!/usr/bin/env node
// 刷新后"原封不动"恢复交互框：前端行为测试（2026-09-25）
// 需求（用户原话）：刷新之后，交互框里已经展示过的东西要原封不动的保留和展示。
// 做法：把 webui/index.html 里真实的快照/恢复函数抠出来，在最小 DOM 桩 + 假 localStorage
//       + 假 IndexedDB 上跑，验证"存下来的画面 = 恢复出来的画面"（逐字节）。
'use strict';
const fs = require('fs');
const path = require('path');
const NL = String.fromCharCode(10);
const HTML_PATH = process.env.VIEW_INDEX_HTML || path.join(__dirname, '..', 'index.html');
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
  const i = HTML.indexOf('var ' + name + ' =');
  if (i < 0) throw new Error('找不到变量 ' + name);
  return HTML.slice(i, HTML.indexOf(NL, i));
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
  this._html = ''; this._scrollH = 0; this._scrollTop = 0; this.clientHeight = 0;
  this.classList = classListOf(this);
}
function matchesSel(el, sel) {
  const s = String(sel || '').trim();
  if (s.indexOf(' ') > 0) {                      // 支持两级后代选择器（.reasoning-block .reasoning-content）
    const parts = s.split(/\s+/);
    for (let i = 0; i < el.children.length; i++) {
      const c = el.children[i];
      if (matchesSel(c, parts[0]) && c.querySelector(parts.slice(1).join(' '))) return true;
    }
    return false;
  }
  if (s.charAt(0) === '#') return el.id === s.slice(1);
  const parts = s.split('.').filter(Boolean);
  const cls = (el.className || '').split(' ');
  return parts.length > 0 && parts.every(function (p) { return cls.indexOf(p) >= 0; });
}
MiniEl.prototype.querySelector = function (sel) {
  if (String(sel).indexOf(' ') > 0) {            // 两级后代
    const parts = String(sel).split(/\s+/);
    for (let i = 0; i < this.children.length; i++) {
      const c = this.children[i];
      if (matchesSel(c, parts[0])) { const d = c.querySelector(parts.slice(1).join(' ')); if (d) return d; }
    }
    return null;
  }
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
MiniEl.prototype.insertBefore = function (el) { this.children.unshift(el); el.parentNode = this; return el; };
Object.defineProperty(MiniEl.prototype, 'firstChild', { get: function () { return this.children[0] || null; } });
function parseInto(host, html) {
  // 够用的两级解析：顶层元素 + 里面再嵌一层（💭 行就是 details 里套 .reasoning-content）
  const top = /<(details|div|span)([^>]*)>([\s\S]*?)<\/\1>/g;
  let m;
  while ((m = top.exec(html))) {
    const el = new MiniEl(m[1]);
    const cm = /class="([^"]*)"/.exec(m[2] || '');
    el.className = cm ? cm[1] : '';
    el.open = /(^|\s)open(\s|$)/.test(m[2] || '');
    const inner = m[3] || '';
    el.textContent = inner.replace(/<[^>]*>/g, '');
    const innerRe = /<(details|div|span)([^>]*)>([\s\S]*?)<\/\1>/g;
    let im;
    while ((im = innerRe.exec(inner))) {
      const ce = new MiniEl(im[1]);
      const ccm = /class="([^"]*)"/.exec(im[2] || '');
      ce.className = ccm ? ccm[1] : '';
      ce.textContent = (im[3] || '').replace(/<[^>]*>/g, '');
      el.children.push(ce);
    }
    host.children.push(el);
  }
}
Object.defineProperty(MiniEl.prototype, 'innerHTML', {
  get: function () { return this._html; },
  set: function (v) { this._html = String(v); this.children = []; parseInto(this, this._html); }
});

// ---- 假 localStorage / 假 IndexedDB ----
function makeLocalStorage() {
  const m = new Map();
  return {
    _m: m,
    get length() { return m.size; },
    key: function (i) { return Array.from(m.keys())[i]; },
    getItem: function (k) { return m.has(k) ? m.get(k) : null; },
    setItem: function (k, v) { m.set(String(k), String(v)); },
    removeItem: function (k) { m.delete(k); }
  };
}
function makeFakeIDB() {
  const store = new Map();
  function fireLater(fn) { setTimeout(fn, 0); }
  const db = {
    objectStoreNames: { contains: function () { return true; } },
    transaction: function () {
      const tx = { error: null, oncomplete: null, onerror: null, onabort: null };
      tx.objectStore = function () {
        return {
          put: function (rec) { store.set(rec.sid, JSON.parse(JSON.stringify(rec))); fireLater(function () { tx.oncomplete && tx.oncomplete(); }); return {}; },
          get: function (sid) { const r = { result: store.get(sid) }; fireLater(function () { r.onsuccess && r.onsuccess(); }); return r; },
          getAll: function () { const r = { result: Array.from(store.values()) }; fireLater(function () { r.onsuccess && r.onsuccess(); }); return r; },
          delete: function (sid) { store.delete(sid); fireLater(function () { tx.oncomplete && tx.oncomplete(); }); return {}; }
        };
      };
      return tx;
    }
  };
  return {
    _store: store,
    open: function () {
      const r = { result: db };
      fireLater(function () { r.onupgradeneeded && r.onupgradeneeded(); r.onsuccess && r.onsuccess(); });
      return r;
    }
  };
}

const localStorageStub = makeLocalStorage();
const indexedDBStub = makeFakeIDB();
const messagesBox = new MiniEl('div');
messagesBox.id = 'messages';
const documentStub = {
  createElement: function (tag) { return new MiniEl(tag); },
  getElementById: function (id) { return id === 'messages' ? messagesBox : null; },
  addEventListener: function () {}
};

const code = [
  grabVar('_VIEW_DB'),          // 这一行里还带 _VIEW_DB_VER / _VIEW_STORE
  grabVar('_VIEW_KEEP'), grabVar('_VIEW_TTL_MS'), grabVar('_VIEW_HOT_KEY'), grabVar('_VIEW_HOT_MAX'),
  grabVar('_VIEW_STREAM_TYPES'),
  grabVar('_viewDbPromise'),    // 这一行里还带 _viewWriteTimer / _viewRunTimer / _viewLastLen
  grab('_afterViewReady'), grab('_viewDbOpen'), grab('_viewDbPut'), grab('_viewDbGet'), grab('_viewDbAll'),
  grab('_viewDbDelete'), grab('_viewEvict'), grab('_viewIsStreamEvent'), grab('_viewSafeItems'),
  grab('_viewShrink'), grab('_viewRecord'), grab('_persistViewSnapshot'), grab('_persistViewSoon'),
  grab('_viewRunStart'), grab('_persistViewHot'), grab('_viewHotRead'), grab('_loadViewSnapshot'),
  grab('_viewApplyToCache'), grab('_restorePersistedView'), grab('_dropViewSnapshot'),
  grab('_settleRestoredView'), grab('_insertMoreMsgsHint'), grab('_ensureSessionRenderCache'),
  grab('_snapshotCurrentSession'),
  grab('_rbMetaText'), grab('_restoreSessionSnapshot')
].join(NL);

const factory = new Function('env', [
  'var document = env.document, localStorage = env.localStorage, indexedDB = env.indexedDB;',
  'var window = env.window, setTimeout = env.setTimeout, clearTimeout = env.clearTimeout, console = env.console;',
  'var currentSid = null, fullText = "", reasoningText = "", progressItems = [];',
  'var agentRunning = false, _currentRunningSid = null, currentAssistantEl = null, currentBubble = null;',
  'var progressTimelineEl = null, _sessionProgressCache = {}, _switchSeq = 0;',
  'var _viewWriteTimer = null, _viewRunTimer = null;',
  'var initMermaid = env.initMermaid, finalizeProgressTimeline = env.finalizeProgressTimeline;',
  code,
  'return {',
  '  api: { afterViewReady: _afterViewReady, safeItems: _viewSafeItems, shrink: _viewShrink, record: _viewRecord,',
  '         persistHot: _persistViewHot, persistSoon: _persistViewSoon, persist: _persistViewSnapshot,',
  '         hotRead: _viewHotRead, load: _loadViewSnapshot, apply: _viewApplyToCache, restorePersist: _restorePersistedView,',
  '         drop: _dropViewSnapshot, settle: _settleRestoredView, moreHint: _insertMoreMsgsHint,',
  '         restoreSnap: _restoreSessionSnapshot, isStream: _viewIsStreamEvent, runStart: _viewRunStart,',
  '         evict: _viewEvict, dbGet: _viewDbGet, ensureCache: _ensureSessionRenderCache,',
  '         snapshot: _snapshotCurrentSession, isRunning: function () { return agentRunning; } },',
  '  setSid: function (s) { currentSid = s; },',
  '  getCache: function () { return _sessionProgressCache[currentSid]; },',
  '  cacheOf: function (s) { return _sessionProgressCache[s]; },',
  '  setRunning: function (r) { agentRunning = r; },',
  '  setText: function (t, r) { fullText = t; reasoningText = r; },',
  '  getReasoning: function () { return reasoningText; },',
  '  setItems: function (it) { progressItems = it; },',
  '  setSeq: function (n) { _switchSeq = n; },',
  '  getSeq: function () { return _switchSeq; },',
  '  setTimer: function (v) { _viewWriteTimer = v; },',
  '  getRunTimer: function () { return _viewRunTimer; },',
  '  setRunTimer: function (v) { _viewRunTimer = v; }',
  '};'
].join(NL));

const messages = messagesBox;
// 假定时器：把回调收起来，测试里手动触发（5 秒落盘、2.5 秒节流这类）
const timers = [];
const env = { document: documentStub, localStorage: localStorageStub, indexedDB: indexedDBStub, window: {}, console: console,
  setTimeout: function (fn, ms) { const t = { fn: fn, ms: ms }; timers.push(t); return t; },
  clearTimeout: function (t) { const i = timers.indexOf(t); if (i >= 0) timers.splice(i, 1); },
  initMermaid: function () {}, finalizeProgressTimeline: function () {} };
function fire(ms) { const hit = timers.filter(t => t.ms === ms); hit.forEach(t => { const i = timers.indexOf(t); if (i >= 0) timers.splice(i, 1); t.fn(); }); return hit.length; }
const S = factory(env);
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  console.log('== A. items 里混进不能序列化的东西，不能把整份快照弄丢 ==');
  {
    const circular = { step: 'a' }; circular.self = circular;
    const items = [{ step: 'ok', status: 'done', detail: '普通项' }, circular, { step: 'big', blob: 'x'.repeat(9000) }];
    const safe = S.api.safeItems(items);
    check('普通项保留', safe.length === 1 && safe[0].step === 'ok', JSON.stringify(safe.map(i => i.step)));
    check('环形引用的项被丢掉', safe.every(i => i.step !== 'a'));
    check('超大项被丢掉', safe.every(i => i.step !== 'big'));
    const rec = { v: 1, sid: 's1', ts: 1, html: '<div>画面</div>', items: [circular], reasoningText: 'x' };
    const shrunk = S.api.shrink(rec);
    check('_viewShrink 能给出可序列化的降级版', !!shrunk && JSON.stringify(shrunk).length > 0);
    check('降级只丢 items，画面 HTML 保留', shrunk.html === rec.html && shrunk.items.length === 0, JSON.stringify(shrunk.items));
  }

  console.log('== B. 记录内容 ==');
  {
    S.setSid('sess-A');
    check('没有快照时不产出记录', S.api.record('sess-A') === null);
    messages.innerHTML = '<div class="message user">你好</div><div class="message assistant">在的</div>';
    messages.scrollTop = 120;
    S.setText('回答正文', '思考全文');
    S.setItems([{ step: 'p', status: 'done' }]);
    S.api.snapshot();
    const rec = S.api.record('sess-A');
    check('记录里带画面 HTML', rec && rec.html === messages.innerHTML);
    check('记录里带消息条数', rec.msgCount === 2, rec.msgCount);
    check('running 不进记录（在不在跑由服务器说了算）', rec.running === undefined && rec.streamingAssistant === false);
    check('记录可 JSON 序列化', (function () { try { JSON.stringify(rec); return true; } catch (e) { return false; } })());
  }

  console.log('== C. 落盘与读回（逐字节）==');
  {
    const html = '<div class="message assistant"><div class="bubble">很长的一段回答' + '答'.repeat(500) + '</div></div>';
    messages.innerHTML = html;
    S.setSid('sess-B');
    messages.scrollTop = 33;
    S.api.snapshot();
    S.api.persistHot('sess-B');
    const key = 'memomics_view_hot_sess-B';
    check('localStorage 里写了热备', !!localStorageStub.getItem(key));
    const back = S.api.hotRead('sess-B');
    check('读回来的画面和存进去的逐字节一致', back && back.html === html, back ? back.html.length + ' vs ' + html.length : 'null');
    check('滚动位置也存了', back.scrollTop === 33, back.scrollTop);
    localStorageStub.setItem(key, '{坏 JSON');
    check('坏 JSON 不会抛异常', S.api.hotRead('sess-B') === null);
    const expired = JSON.parse(localStorageStub.getItem('memomics_view_hot_sess-A') || 'null');
    localStorageStub.setItem('memomics_view_hot_sess-C', JSON.stringify({ v: 1, sid: 'sess-C', ts: Date.now() - 8 * 24 * 3600 * 1000, html: '<div>x</div>' }));
    check('过期（7 天）的热备被丢掉', S.api.hotRead('sess-C') === null && !localStorageStub.getItem('memomics_view_hot_sess-C'));
    // 超大画面：热备写不下 → 转走 IDB
    const huge = '<div>' + 'x'.repeat(3100000) + '</div>';
    S.setSid('sess-D');
    messages.innerHTML = huge;
    S.api.snapshot();
    S.api.persistHot('sess-D');
    check('超大画面不写热备（避免撑爆 localStorage 配额）', localStorageStub.getItem('memomics_view_hot_sess-D') === null);
    await sleep(30);
    const fromDb = await S.api.dbGet('sess-D');
    check('超大画面改走 IndexedDB', !!fromDb && fromDb.html === huge, fromDb ? fromDb.html.length : 'null');
  }

  console.log('== D. 恢复：存下来的画面 = 恢复出来的画面 ==');
  {
    const html = '<details class="reasoning-block" open><summary><span class="rb-text">思考</span></summary><div class="reasoning-content">' + '思'.repeat(300) + '</div></details>'
      + '<div class="message assistant"><div class="bubble">结论</div></div>';
    S.setSid('sess-E');
    S.setText('结论', '思'.repeat(300));
    messages.innerHTML = html;
    messages.scrollTop = 7;
    S.api.snapshot();
    const c = S.api.ensureCache('sess-E');
    messages.innerHTML = '<div class="message user">别的东西</div>';
    S.api.restoreSnap(c);
    check('恢复后画面与快照逐字节一致', messages.innerHTML === html, messages.innerHTML.length + ' vs ' + html.length);
    check('恢复后思考全文可用', S.getReasoning().length === 300, S.getReasoning().length);
    check('恢复后滚动位置还原', messages.scrollTop === 7, messages.scrollTop);
    check('自检标记 byteEqual = true', env.window.__memomicsViewRestore && env.window.__memomicsViewRestore.byteEqual === true,
      JSON.stringify(env.window.__memomicsViewRestore && env.window.__memomicsViewRestore.byteEqual));
    // 记录里没带思考全文 → 从还原出来的 💭 行里取
    const c2 = S.api.ensureCache('sess-F');
    c2.hasSnapshot = true; c2.messageHtml = html; c2.reasoningText = ''; c2.items = [];
    S.setSid('sess-F');
    S.setText('', '');
    S.api.restoreSnap(c2);
    check('记录没带思考全文时，从 💭 行里补上', S.getReasoning().length === 300, S.getReasoning().length);
    check('💭 行的展开状态跟着画面一起还原（open 还在）', messages.querySelector('.reasoning-block').open === true);
  }

  console.log('== E. 等不等 IndexedDB：顺序要对 ==');
  {
    let ran = false;
    const v = S.api.afterViewReady(null, function () { ran = true; return 'sync'; });
    check('没有在等的时候同步执行', ran === true && v === 'sync', v);
    let ran2 = false;
    const p = S.api.afterViewReady(Promise.resolve(1), function () { ran2 = true; return 'async'; });
    check('在等的时候先不执行', ran2 === false);
    const v2 = await p;
    check('等到了才执行，且返回值透传', ran2 === true && v2 === 'async', v2);
    let ran3 = false;
    await S.api.afterViewReady(Promise.reject(new Error('boom')), function () { ran3 = true; return 'fallback'; });
    check('等待失败也要继续（不能白屏）', ran3 === true);
  }

  console.log('== F. 谁新用谁 ==');
  {
    S.setSid('sess-G');
    // 先写热备（A 画面），隔几毫秒再写 IDB（B 画面）→ IDB 更新
    messages.innerHTML = '<div class="message">A 画面</div>';
    S.api.snapshot(); S.api.persistHot('sess-G');
    await sleep(15);
    messages.innerHTML = '<div class="message">B 画面</div>';
    S.api.snapshot(); S.api.persist('sess-G');
    await sleep(30);
    const r1 = await S.api.load('sess-G');
    check('IDB 比热备新 → 用 IDB', r1 && r1.html === '<div class="message">B 画面</div>', r1 && r1.html);
    S.setSeq(5);
    S.api.ensureCache('sess-G').fromPersist = true;   // 模拟：刚切进来，画面只可能来自磁盘
    const applied = await S.api.restorePersist('sess-G', 5);
    check('恢复成功', applied === true);
    check('恢复的是最新的那份', messages.innerHTML === '<div class="message">B 画面</div>', messages.innerHTML);
    const again = await S.api.restorePersist('sess-G', 5);
    check('同一份不会重复恢复', again === false);
    // 反过来：IDB 旧、热备新 → 用热备（只动热备，DOM 保持 B 画面不动）
    localStorageStub.setItem('memomics_view_hot_sess-G',
      JSON.stringify({ v: 1, sid: 'sess-G', ts: Date.now(), html: '<div class="message">C 画面</div>', msgCount: 1, items: [] }));
    const r2 = await S.api.load('sess-G');
    check('热备比 IDB 新 → 用热备', r2 && r2.html === '<div class="message">C 画面</div>', r2 && r2.html);
    // 已经恢复过更新的画面 → 旧的不能再盖回来
    const older = S.api.ensureCache('sess-G');
    older.viewTs = Date.now() + 9999;
    const r3 = await S.api.restorePersist('sess-G', 5);
    check('比已恢复的更旧 → 不覆盖', r3 === false && messages.innerHTML === '<div class="message">B 画面</div>', messages.innerHTML);
    check('已经恢复过的画面还在（没被清空）', messages.innerHTML.length > 0);
    const liveCache = S.api.ensureCache('sess-H');
    liveCache.hasSnapshot = true; liveCache.fromPersist = false;
    S.setSid('sess-H');
    check('同页面已有实时快照 → 不动它', (await S.api.restorePersist('sess-H', 5)) === false);
    S.setSid('sess-I');
    check('会话已经切走 → 不恢复', (await S.api.restorePersist('sess-G', 5)) === false);
  }

  console.log('== G. 清理与收尾 ==');
  {
    S.setSid('sess-J');
    localStorageStub.setItem('memomics_view_hot_sess-J', JSON.stringify({ v: 1, sid: 'sess-J', ts: Date.now(), html: '<div>x</div>' }));
    await S.api.persist({ v: 1, sid: 'sess-J', ts: Date.now(), html: '<div>x</div>', items: [] });
    await S.api.drop('sess-J');
    check('删除会话时热备一起清掉', localStorageStub.getItem('memomics_view_hot_sess-J') === null);
    check('删除会话时 IDB 一起清掉', (await S.api.dbGet('sess-J')) === null);
    messages.innerHTML = '<details class="reasoning-block running"><summary><span class="rb-meta">展开</span></summary><div class="reasoning-content">x</div></details>'
      + '<div class="tool-block running"><div class="tool-head">🔧 t</div></div>';
    S.setText('', 'x');
    S.api.settle();
    check('恢复后的画面不再假装"运行中"（思考行）', messages.querySelectorAll('.reasoning-block.running').length === 0);
    check('恢复后的画面不再假装"运行中"（工具块）', messages.querySelectorAll('.tool-block.running').length === 0);
    check('收尾后刷新了字数提示', messages.querySelector('.rb-meta').textContent === '展开 · 1 字', messages.querySelector('.rb-meta').textContent);
    messages.innerHTML = '<div class="message assistant"><div class="bubble">最新</div></div>';
    S.api.moreHint('sess-K', 300, 100);
    check('"显示全部"入口插在最上面', messages.firstChild.className === 'more-msgs-hint', messages.firstChild.className);
    check('入口文案带总数和当前条数', messages.firstChild.innerHTML.indexOf('显示全部 300 条消息') > 0 && messages.firstChild.innerHTML.indexOf('最近 100 条') > 0,
      messages.firstChild.innerHTML);
    messages.innerHTML = '';
    S.api.moreHint('sess-K', 0, 100);
    check('只显示最近 100 条时文案退回"加载更早的消息"', messages.firstChild.innerHTML.indexOf('加载更早的消息') > 0, messages.firstChild.innerHTML);
  }

  console.log('== H. 运行中落盘节流 ==');
  {
    check('delta/reasoning/tool_start 算运行中事件', S.api.isStream('delta') && S.api.isStream('reasoning') && S.api.isStream('tool_start'));
    check('complete/error 不算', !S.api.isStream('complete') && !S.api.isStream('error') && !S.api.isStream('todos'));
    S.setSid('sess-G');
    timers.length = 0;
    S.setRunning(true);
    S.setRunTimer(null);
    S.api.runStart(); S.api.runStart(); S.api.runStart();
    check('重复触发只排一个 5 秒定时器', timers.filter(t => t.ms === 5000).length === 1, timers.length);
    messages.innerHTML = '<div class="message assistant">跑到一半</div>';
    S.api.ensureCache('sess-G').messageHtml = '<div>旧画面</div>';
    fire(5000);
    check('到点把当前画面落盘', S.api.ensureCache('sess-G').messageHtml === messages.innerHTML, S.api.ensureCache('sess-G').messageHtml);
    check('还在跑就继续排下一个', timers.filter(t => t.ms === 5000).length === 1);
    S.setRunning(false);
    messages.innerHTML = '<div class="message assistant">已经跑完</div>';
    fire(5000);
    check('跑完了就不再落盘', S.api.ensureCache('sess-G').messageHtml !== messages.innerHTML);
    check('跑完了定时器收工', timers.filter(t => t.ms === 5000).length === 0);
    // 2.5 秒节流：攒一次写一次
    timers.length = 0;
    S.setTimer(null);
    S.api.persistSoon('sess-G'); S.api.persistSoon('sess-G');
    check('流式期间只排一个 2.5 秒落盘', timers.filter(t => t.ms === 2500).length === 1, timers.length);
    fire(2500);
    await sleep(30);
    const dbg = await S.api.dbGet('sess-G');
    check('到点写进 IndexedDB（写的是最近一次快照的画面）',
      !!dbg && dbg.html === S.api.ensureCache('sess-G').messageHtml, dbg && dbg.html);
    check('写进 IndexedDB 的记录可读回（带条数）', !!dbg && dbg.msgCount >= 0, dbg && dbg.msgCount);
  }

  console.log('----');
  console.log(pass + ' pass, ' + fail + ' fail');
  process.exit(fail === 0 ? 0 : 1);
}
main().catch(function (e) { console.log('harness error: ' + (e && e.stack || e)); process.exit(2); });
