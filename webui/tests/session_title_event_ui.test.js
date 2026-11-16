/* Offline regression for stale automatic session-title websocket events. */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');

function extractFunction(signature) {
  const start = html.indexOf(signature);
  assert.ok(start >= 0, `missing ${signature}`);
  const open = html.indexOf('{', start);
  let depth = 0; let quote = ''; let escaped = false; let line = false; let block = false;
  for (let i = open; i < html.length; i++) {
    const ch = html[i]; const next = html[i + 1];
    if (line) { if (ch === '\n') line = false; continue; }
    if (block) { if (ch === '*' && next === '/') { block = false; i++; } continue; }
    if (quote) {
      if (escaped) { escaped = false; continue; }
      if (ch === '\\') { escaped = true; continue; }
      if (ch === quote) quote = '';
      continue;
    }
    if (ch === '/' && next === '/') { line = true; i++; continue; }
    if (ch === '/' && next === '*') { block = true; i++; continue; }
    if (ch === '\'' || ch === '"' || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth++;
    if (ch === '}' && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`unterminated ${signature}`);
}

const context = { Object, String, console, _manualSessionTitleIds: Object.create(null) };
context.window = context;
vm.createContext(context);
vm.runInContext(extractFunction('function _acceptIncomingSessionTitle(sid, source, title)'), context, { filename: 'title-event-guard.js' });

context._manualSessionTitleIds['chat-a'] = '用户指定的名称';
assert.equal(context._acceptIncomingSessionTitle('chat-a', 'auto', '旧自动名'), false,
  'a delayed automatic title cannot overwrite a confirmed manual rename');
assert.equal(context._acceptIncomingSessionTitle('chat-a', '', '旧未标记名'), false,
  'an old unmarked server event is treated as automatic while a manual title is held');
assert.equal(context._manualSessionTitleIds['chat-a'], '用户指定的名称', 'rejected events leave the manual title intact');
assert.equal(context._acceptIncomingSessionTitle('chat-a', 'manual', '另一个手动名称'), true,
  'a later authoritative manual title remains acceptable');
assert.equal(context._manualSessionTitleIds['chat-a'], '另一个手动名称', 'manual events update the local title guard');
assert.equal(context._acceptIncomingSessionTitle('chat-b', 'auto', '自动摘要'), true,
  'ordinary automatic naming remains available for sessions without a manual rename');

assert.match(html, /_manualSessionTitleIds\[String\(sid\)\] = res\.d\.title/, 'successful rename records a local manual title before later websocket events');
assert.match(html, /if \(!_acceptIncomingSessionTitle\(titleSid, titleSource, msg\.title\)\) return;/,
  'session-title websocket path consults the stale-event guard');

console.log('session_title_event_ui.test.js: PASS');
