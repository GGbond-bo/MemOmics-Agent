#!/usr/bin/env node
// 状态条"已 N 秒无新输出"前端行为测试（2026-09-26）
// 需求（用户原话）：MemOmics 有时候会卡住，长时间不输出内容 —— 得让人一眼看出
// 是在跑还是死了。做法：把 webui/index.html 里真实的状态条函数抠出来，在最小
// DOM 桩 + 假时钟 + 假定时器上跑，验证静默计数的显示与刷新。
'use strict';
const fs = require('fs');
const path = require('path');
const NL = String.fromCharCode(10);
const HTML_PATH = process.env.STALL_INDEX_HTML || path.join(__dirname, '..', 'index.html');
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

const code = [
  grab('_fmtDur'), grab('_silentSeconds'), grab('_ensureLiveStatus'),
  grab('updateLiveStatus'), grab('hideLiveStatus'),
  grab('_startLiveStatusTicker'), grab('_stopLiveStatusTicker')
].join(NL);
const actMatch = /var _ACTIVITY_TYPES = \{[^}]*\};/.exec(HTML);
if (!actMatch) { console.log('FAIL 找不到 _ACTIVITY_TYPES'); process.exit(1); }

// ---- 假时钟 / 假 DOM / 假定时器 ----
let NOW = 1000000000000;
const FakeDate = { now: function () { return NOW; } };
const messagesEl = {
  id: 'messages', children: [], firstChild: null,
  insertBefore: function (el) { this.children.unshift(el); this.firstChild = this.children[0]; }
};
const byId = {};
const documentStub = {
  getElementById: function (id) { return id === 'messages' ? messagesEl : (byId[id] || null); },
  createElement: function () {
    const el = { id: '', style: {}, className: '', textContent: '', parentNode: null };
    return el;
  }
};
const intervals = [];
const timeouts = [];
const env = {
  document: documentStub, Date: FakeDate,
  setInterval: function (fn, ms) { const t = { fn: fn, ms: ms, cleared: false }; intervals.push(t); return t; },
  clearInterval: function (t) { if (t) t.cleared = true; },
  setTimeout: function (fn, ms) { const t = { fn: fn, ms: ms }; timeouts.push(t); return t; },
  // new Function 的函数体只能看见全局，看不见本模块的 const —— 用 env 传进去
  getBar: function () { return byId['live-status']; }
};

const factory = new Function('env', [
  'var document = env.document, setInterval = env.setInterval, clearInterval = env.clearInterval;',
  'var Date = env.Date, setTimeout = env.setTimeout;',
  'var agentRunning = false, _runStartTs = null, _lastHeartbeatTs = 0, _lastApiCalls = 0;',
  'var _lastTool = "", _lastStalled = false, _lastTurns = 0, _liveStatusTimer = null;',
  'var _lastActivityTs = 0;',
  actMatch[0],
  code,
  'return {',
  '  update: updateLiveStatus, hide: hideLiveStatus, silent: _silentSeconds,',
  '  start: _startLiveStatusTicker, stop: _stopLiveStatusTicker, fmt: _fmtDur,',
  '  types: _ACTIVITY_TYPES,',
  '  setRun: function (v) { _runStartTs = v; }, setAct: function (v) { _lastActivityTs = v; },',
  '  setRunning: function (v) { agentRunning = v; }, setHeartbeat: function (v) { _lastHeartbeatTs = v; },',
  '  setTool: function (v) { _lastTool = v; },',
  '  bar: function () { return env.getBar(); },',
  '  timer: function () { return _liveStatusTimer; }',
  '};'
].join(NL));
const api = factory(env);
// createElement 出来的元素要能被 getElementById 找到（_ensureLiveStatus 会先查一次）
const realCreate = documentStub.createElement;
documentStub.createElement = function () { const el = realCreate(); byId['live-status'] = el; return el; };

function statusText() { const b = api.bar(); return b ? b.textContent : '(状态条还没建)'; }
function runFor(sec) { api.setRun(NOW - sec * 1000); }

console.log('== 状态条静默指示 ==');
api.setRunning(true);
runFor(30); api.setAct(NOW - 30 * 1000);
api.update(30, 3, 'debate_analysis', false, 2);
check('跑 30 秒时不报静默', statusText().indexOf('无新输出') < 0, statusText());
check('常规信息仍在（已用/工具调用/当前工具）',
  statusText().indexOf('🔄 运行中') >= 0 && statusText().indexOf('3 次工具调用') >= 0 &&
  statusText().indexOf('当前: debate_analysis') >= 0, statusText());
check('未静默时不算 stalled', (api.bar().className || '').indexOf('stalled') < 0, api.bar().className);

runFor(90); api.setAct(NOW - 90 * 1000);
api.update(90, 3, 'debate_analysis', false, 2);
check('静默 90 秒 → 状态条写「⏳ 已 90 秒无新输出」', statusText().indexOf('⏳ 已 90 秒无新输出') >= 0, statusText());
check('静默 90 秒还不标红（<120s）', (api.bar().className || '').indexOf('stalled') < 0, api.bar().className);

runFor(150); api.setAct(NOW - 150 * 1000);
api.update(150, 3, 'debate_analysis', false, 2);
check('静默 150 秒 → 标红 stalled', (api.bar().className || '').indexOf('stalled') >= 0, api.bar().className);
check('静默秒数跟着时间走', statusText().indexOf('⏳ 已 150 秒无新输出') >= 0, statusText());

// 上一轮留下的旧时间戳：必须以本轮起点为准，否则新一轮一开就显示"静默半小时"
api.setRun(NOW - 20 * 1000); api.setAct(NOW - 3600 * 1000);
check('旧活动时间戳不会污染新的一轮', api.silent() === 20, api.silent());

// 新内容到达 → 归零
api.setAct(NOW);
check('新活动到达后静默归零', api.silent() === 0, api.silent());
api.update(20, 3, 'debate_analysis', false, 2);
check('归零后状态条不再报静默', statusText().indexOf('无新输出') < 0, statusText());

console.log('== 1 秒心跳兜底 ==');
api.start();
check('ticker 已注册', !!api.timer());
check('ticker 间隔是 1000ms（不是 15 秒，否则静默数字自己不走）', intervals[0] && intervals[0].ms === 1000, intervals[0] && intervals[0].ms);
runFor(95); api.setAct(NOW - 95 * 1000); api.setHeartbeat(NOW - 1000);
intervals[0].fn();
check('静默时每秒 tick 都会刷新状态条', statusText().indexOf('⏳ 已 95 秒无新输出') >= 0, statusText());

// 心跳新鲜且不静默 → 不该抢着刷（省 DOM 写入）
api.setRun(NOW - 5 * 1000); api.setAct(NOW - 5 * 1000); api.setHeartbeat(NOW);
api.update(5, 9, 'read_file', false, 1);
const before = statusText();
intervals[0].fn();
check('心跳新鲜且不静默时不刷（不干扰服务端推送的显示）', statusText() === before, statusText());

api.stop();
check('stop 后 ticker 被清掉', intervals[0].cleared === true && api.timer() === null);

console.log('== 活动事件表 ==');
const need = ['delta', 'reasoning', 'thinking', 'tool_start', 'tool_progress', 'progress', 'tool_complete', 'status'];
const missing = need.filter(function (t) { return !api.types[t]; });
check('_ACTIVITY_TYPES 覆盖所有"界面有新内容"的事件', missing.length === 0, '缺: ' + missing.join(','));

console.log('== 收尾 ==');
api.setRunning(false);
api.hide('✅ 已完成');
check('hideLiveStatus 显示完成态', api.bar().className === 'done' && api.bar().textContent === '✅ 已完成', api.bar().textContent);
check('_fmtDur(3725) = 1:02:05', api.fmt(3725) === '1:02:05', api.fmt(3725));

console.log('');
console.log(pass + ' pass / ' + fail + ' fail');
process.exit(fail === 0 ? 0 : 1);
