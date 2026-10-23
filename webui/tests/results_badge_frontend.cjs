#!/usr/bin/env node
// 「分析结果栏红色提醒 + 点开之后找新结果」前端行为测试（2026-10-23）
// 用户要求（要点）：① 出图后在「分析结果栏」亮红色提醒；点击后消失，有新结果再出现；
//   只显示当前会话的结果。② 点击之后要能找到「新更新的文件」（图片能看到，文件太多找不到）——
//   所以点开时把这一批新结果冻结成清单，面板里高亮 + 一键「只看本次更新」。
// 做法：把 webui/index.html 里的真实函数抠出来，桩 localStorage/document 跑纯逻辑。
'use strict';
const fs = require('fs');
const path = require('path');
const NL = String.fromCharCode(10);
const HTML_PATH = process.env.PROC_INDEX_HTML || path.join(__dirname, '..', 'index.html');
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
  // 状态变量（_rsBadgeCount / _rsNewKeys / _rsJustNew）也要用真身，别在测试里另起一份
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

const code = [
  grabVar('_rsBadgeCount'), grabVar('_rsNewKeys'), grabVar('_rsJustNew'),
  grab('_rsSeenKey'), grab('_rsSeenGet'), grab('_rsSeenSet'), grab('_rsItemMs'),
  grab('_rsBadgeEnsure'), grab('_rsBadgeRender'), grab('_rsBadgeClear'), grab('_rsBadgeBump'),
  grab('_rsFigKnown'), grab('_rsFigLooksOld'), grab('_rsBadgeNoteNewFigure'),
  grab('_rsBadgeScan'), grab('_rsMergeKeys'),
  grab('_rsJustNewKey'), grab('_rsJustNewLoad'), grab('_rsJustNewSave'),
  grab('_rsJustNewOf'), grab('_rsJustNewHas'), grab('_rsJustNewCount'), grab('_rsJustNewClearItem'),
  grab('_rsNewFilterOn'), grab('_visibleResultItems')
].join(NL);

const factory = new Function('env', [
  'var currentSid = "";',
  'var _showUnreadOnly = false, _showNewOnly = false;',
  'var _lastFigItems = [], _runStartTs = null;',
  'var localStorage = env.localStorage, document = env.document, tf = env.tf;',
  code,
  'return {',
  '  setSid: function (s) { currentSid = s; },',
  '  setNewOnly: function (v) { _showNewOnly = !!v; },',
  '  setUnreadOnly: function (v) { _showUnreadOnly = !!v; },',
  '  ensure: _rsBadgeEnsure, render: _rsBadgeRender, clear: _rsBadgeClear, bump: _rsBadgeBump, scan: _rsBadgeScan,',
  '  seenGet: _rsSeenGet, seenSet: _rsSeenSet, itemMs: _rsItemMs,',
  '  justNewCount: _rsJustNewCount, justNewHas: _rsJustNewHas,',
  '  justKeys: function (s) { return _rsNewKeys[s] || null; },',
  '  visible: _visibleResultItems,',
  '  setFigs: function (v) { _lastFigItems = v || []; },',
  '  setRunStart: function (v) { _runStartTs = v; },',
  '  clearItem: _rsJustNewClearItem,',
  '  noteFig: _rsBadgeNoteNewFigure',
  '};'].join(NL));

function makeLs() {
  return {
    m: {},
    getItem: function (k) { return (k in this.m) ? this.m[k] : null; },
    setItem: function (k, v) { this.m[k] = String(v); }
  };
}
function newEnv(reuseLs) {
  const ls = reuseLs || makeLs();
  const badge = { textContent: '', title: '', style: { display: 'none' },
    removeAttribute: function (n) { if (n === 'title') this.title = ''; } };
  const nav = { _cls: {}, classList: { toggle: function (c, on) { nav._cls[c] = !!on; } } };
  const doc = { getElementById: function (id) {
    return id === 'nav-results-badge' ? badge : (id === 'nav-results' ? nav : null);
  } };
  const e = factory({
    localStorage: ls, document: doc,
    tf: function (key) {
      const a = Array.prototype.slice.call(arguments, 1);
      const d = { rs_badge_new: '有 {0} 个新分析结果，点击查看' };
      return String(d[key] || key).replace(/\{(\d+)\}/g, function (m, i) { return a[+i] != null ? String(a[+i]) : m; });
    }
  });
  return { e: e, ls: ls, badge: badge, nav: nav };
}

const NOW = Math.floor(Date.now() / 1000);

console.log('== A. 基线：刚打开的会话，老结果不算「新」 ==');
{
  const { e, badge, ls } = newEnv();
  e.setSid('s1');
  e.ensure('s1');
  check('基线已写入（每个会话一份）', ls.getItem('memomics_res_seen_s1') !== null);
  check('没有新结果 → 红点不显示', badge.style.display === 'none');
  e.scan([{ name: 'old.png', mtime_epoch: NOW - 3600 }], []);
  check('老结果不计入', badge.style.display === 'none');
}

console.log('== B. 有新结果 → 亮红点（计数、只增不减） ==');
{
  const { e, badge, nav } = newEnv();
  e.setSid('s1');
  e.seenSet('s1', (NOW - 100) * 1000);
  e.scan([{ name: 'new1.png', mtime_epoch: NOW }], []);
  check('新图 → 计数 1、红点亮起', badge.style.display === '' && badge.textContent === '1', JSON.stringify(badge));
  check('「分析结果」栏同时标红', nav._cls['has-red-badge'] === true);
  check('提示文案带数量', badge.title.indexOf('1') >= 0, badge.title);
  e.scan([], []);
  check('下一轮没新增 → 计数不降（防闪）', badge.textContent === '1');
  e.scan([{ name: 'new1.png', mtime_epoch: NOW }, { name: 'new2.png', mtime_epoch: NOW + 1 }, { name: 'new3.png', mtime_epoch: NOW + 2 }], []);
  check('再来两张 → 计数 3（每次刷新都按完整列表重算）', badge.textContent === '3', badge.textContent);
}

console.log('== C. 点开「分析结果」→ 消失；之后再出新结果 → 再出现 ==');
{
  const { e, badge, nav } = newEnv();
  e.setSid('s1');
  e.seenSet('s1', (NOW - 100) * 1000);
  e.scan([{ name: 'a.png', mtime_epoch: NOW }], []);
  check('先亮着', badge.style.display === '');
  e.clear();
  check('点开后计数清零、红点消失', badge.style.display === 'none' && nav._cls['has-red-badge'] === false);
  e.scan([{ name: 'a.png', mtime_epoch: NOW - 1 }], []);
  check('已经看过的那张不再算新', badge.style.display === 'none');
  e.scan([{ name: 'b.png', mtime_epoch: Math.floor(Date.now() / 1000) + 2 }], []);
  check('又有新结果 → 红点再次出现', badge.style.display === '' && badge.textContent === '1', JSON.stringify(badge));
}

console.log('== D. 只算当前会话（两个会话互不串） ==');
{
  const { e, badge } = newEnv();
  e.setSid('A');
  e.seenSet('A', (NOW - 100) * 1000);
  e.scan([{ name: 'a.png', mtime_epoch: NOW }], []);
  check('会话 A 亮起计数 1', badge.textContent === '1');
  e.setSid('B');
  e.render();
  check('切到会话 B（自己没新结果）→ 不显示 A 的红点', badge.style.display === 'none', JSON.stringify(badge));
  e.ensure('B');
  e.scan([{ name: 'old_b.png', mtime_epoch: NOW - 50 }], []);
  check('B 的老结果也不冒充「新」', badge.style.display === 'none');
  e.bump();
  check('切回前 B 自己出新图 → 只亮 B 的', badge.style.display === '' && badge.textContent === '1');
  e.setSid('A');
  e.render();
  check('切回 A → 显示 A 自己的计数（不是 B 的）', badge.style.display === '' && badge.textContent === '1');
}

console.log('== E. 文件与目录的细节 ==');
{
  const { e, badge } = newEnv();
  e.setSid('s1');
  e.seenSet('s1', (NOW - 100) * 1000);
  e.scan([], [{ name: 'scripts', is_dir: true, mtime_epoch: NOW }, { name: 'r.rds', mtime: NOW }, { name: 'old.txt', mtime: NOW - 500 }]);
  check('目录不算、数字 mtime 算、旧文件不算', badge.textContent === '1', badge.textContent);
  e.scan([], [{ name: 'r.rds', mtime: NOW }, { name: 'report.docx', mtime: '2099-01-01 00:00:00' }]);
  check('字符串 mtime 也能解析（世纪后）', badge.textContent === '2', badge.textContent);
  check('_rsItemMs：epoch/数字/字符串/空', e.itemMs({ mtime_epoch: 5 }) === 5000
    && e.itemMs({ mtime: 5 }) === 5000 && e.itemMs({ mtime: '2099-01-01 00:00:00' }) > 0 && e.itemMs(null) === 0);
}

console.log('== F. 没有会话时不亮 ==');
{
  const { e, badge } = newEnv();
  e.setSid('');
  e.render();
  check('currentSid 为空 → 隐藏', badge.style.display === 'none');
  const before = badge.textContent;
  e.clear();
  check('清空操作不报错、不写入', badge.style.display === 'none' && badge.textContent === before);
}

console.log('== G. 点开之后找得到：新结果清单被冻结、可高亮/筛选 ==');
{
  const { e, ls } = newEnv();
  e.setSid('s1');
  e.seenSet('s1', (NOW - 100) * 1000);
  e.scan([{ name: 'figA.png', mtime_epoch: NOW }], [{ name: 'table.csv', path: '/r/table.csv', mtime: NOW }]);
  check('扫描时就记下「是哪些」', e.justKeys('s1').files.length === 1 && e.justKeys('s1').figs.length === 1);
  e.clear();
  check('点开瞬间冻结成「本次更新」清单', e.justNewCount() === 2
    && e.justNewHas('s1', 'file', '/r/table.csv') === true && e.justNewHas('s1', 'fig', 'figA.png') === true);
  check('清单已持久化到本机', ls.getItem('memomics_res_justnew_s1') !== null);
  e.clear();
  check('没有新东西时再点一次 → 旧清单不被清掉', e.justNewCount() === 2);
  // 新一批来了：并集累积（先看的不会消失）
  e.scan([{ name: 'figA.png', mtime_epoch: NOW }, { name: 'figB.png', mtime_epoch: Math.floor(Date.now() / 1000) + 5 }], []);
  e.clear();
  check('新一批并入清单（不是覆盖）', e.justNewCount() === 3 && e.justNewHas('s1', 'fig', 'figA.png') && e.justNewHas('s1', 'fig', 'figB.png'));
  // 刷新/重开页面：从本机装载（同一 localStorage，新的页面实例）
  const env2 = newEnv(ls);
  env2.e.setSid('s1');
  check('刷新后清单仍在（从本机装载）', env2.e.justNewCount() === 3 && env2.e.justNewHas('s1', 'file', '/r/table.csv'));
  env2.e.bump('figRealtime.png');
  check('出图事件即时记名（不用等下一次刷新）', env2.e.justKeys('s1').figs.indexOf('figRealtime.png') >= 0);
}

console.log('== H. 「最新文件 N」标记条 + 看过一个减一 ==');
{
  const { e, ls } = newEnv();
  e.setSid('s1');
  e.seenSet('s1', (NOW - 100) * 1000);
  e.scan([{ name: 'new.png', mtime_epoch: NOW }], [{ name: 'x.csv', path: '/r/x.csv', mtime: NOW }]);
  e.clear();
  check('标记条数字 = 清单里还没看过的新结果（2）', e.justNewCount() === 2);
  const items = [
    { name: 'x.csv', path: '/r/x.csv', is_dir: false },
    { name: 'old.csv', path: '/r/old.csv', is_dir: false, viewed: true },
    { name: 'sub', path: '/r/sub', is_dir: true }
  ];
  e.setNewOnly(false);
  check('关闭时全部可见', e.visible(items).length === 3);
  e.setNewOnly(true);
  const vis = e.visible(items);
  check('只看最新文件：目录保留 + 新文件保留 + 老文件滤掉',
    vis.length === 2 && vis[0].name === 'x.csv' && vis[1].is_dir === true, JSON.stringify(vis.map(function (f) { return f.name; })));
  e.setUnreadOnly(true);
  check('与「只看未查看」可叠加（新文件没看过 → 仍在）', e.visible(items).length === 2);
  // 看过一个 → 数字减一，且该项红色标识消失
  check('看过文件 → 数字 2→1，NEW 消失', e.clearItem('file', '/r/x.csv') === true && e.justNewCount() === 1
    && e.justNewHas('s1', 'file', '/r/x.csv') === false);
  check('看过图片 → 数字 1→0（全看完）', e.clearItem('fig', 'new.png') === true && e.justNewCount() === 0);
  check('没看过/不存在的东西不受影响（幂等）', e.clearItem('fig', 'new.png') === false && e.clearItem('file', '/r/nope.csv') === false);
  const rawB = JSON.parse(ls.getItem('memomics_res_justnew_s1'));
  check('减完的清单落本机（刷新后不复活）', rawB.files.length === 0 && rawB.figs.length === 0);
  check('全部看完后筛选取空 → 列表自动回正常', e.visible(items).length === 2 || e.visible(items).length === 3);
  const { e: e2 } = newEnv();
  e2.setSid('sX');
  e2.setNewOnly(true);
  check('没有最新文件时筛选取空 → 不误伤列表', e2.visible(items).length === 3);
}

console.log('== I. 假新图拦截：刚发问不该亮（服务器重扫老图 / 回放重发历史事件） ==');
{
  const { e, badge } = newEnv();
  const hms = function (ms) {
    const d = new Date(ms);
    return [d.getHours(), d.getMinutes(), d.getSeconds()].map(function (n) { return String(n).length < 2 ? '0' + n : String(n); }).join(':');
  };
  e.setSid('s1');
  e.seenSet('s1', (NOW - 1000) * 1000);
  e.setFigs([{ name: 'old.png' }]);   // 结果面板里已有的图 = 老图
  e.setRunStart(Date.now());
  check('列表里已有的图不点亮（服务器每轮会重扫它们）',
    e.noteFig({ name: 'old.png', mtime: hms(Date.now()) }, false) === false && badge.style.display === 'none');
  check('回放事件不点亮（切会话/重连会重发历史 new_figure）',
    e.noteFig({ name: 'fromReplay.png', mtime: hms(Date.now()) }, true) === false && badge.style.display === 'none');
  check('时间明显早于本轮开始 → 不点亮',
    e.noteFig({ name: 'ancient.png', mtime: hms(Date.now() - 10 * 60 * 1000) }, false) === false && badge.style.display === 'none');
  check('真的新图（本轮产物）→ 点亮并记名',
    e.noteFig({ name: 'fresh.png', mtime: hms(Date.now()) }, false) === true
    && badge.style.display === '' && badge.textContent === '1', JSON.stringify(badge));
  check('同一张再来一次 → 不重复计数', e.noteFig({ name: 'fresh.png', mtime: hms(Date.now()) }, false) === false && badge.textContent === '1');
  e.clear();
  check('点开之后同名的图不再重复点亮', e.noteFig({ name: 'fresh.png', mtime: hms(Date.now()) }, false) === false && badge.style.display === 'none');
  // 没有本轮开始时间（任务已完成/未知）时退回「列表成员」判定，不误杀
  e.setRunStart(null);
  check('拿不到本轮开始时间 → 依靠列表成员判断（不误杀新图）',
    e.noteFig({ name: 'late.png', mtime: hms(Date.now()) }, false) === true);
}

console.log(NL + '----');
console.log(pass + ' pass, ' + fail + ' fail');
process.exit(fail ? 1 : 0);