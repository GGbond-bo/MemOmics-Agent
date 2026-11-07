/* Offline UI guard tests for server-authoritative empty-session reuse. */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const signature = 'window.newSession = async function newSession(projectId) {';
const start = html.indexOf(signature);
assert.ok(start >= 0, 'project-aware newSession override must exist');
function extractBalanced(startAt) {
  const open = html.indexOf('{', startAt); let depth = 0; let quote = ''; let escaped = false; let line = false; let block = false;
  for (let i = open; i < html.length; i++) {
    const ch = html[i]; const next = html[i + 1];
    if (line) { if (ch === '\n') line = false; continue; }
    if (block) { if (ch === '*' && next === '/') { block = false; i++; } continue; }
    if (quote) { if (escaped) { escaped = false; continue; } if (ch === '\\') { escaped = true; continue; } if (ch === quote) quote = ''; continue; }
    if (ch === '/' && next === '/') { line = true; i++; continue; }
    if (ch === '/' && next === '*') { block = true; i++; continue; }
    if (ch === '\'' || ch === '"' || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth++;
    if (ch === '}' && --depth === 0) return html.slice(startAt, i + 1) + ';';
  }
  throw new Error('unterminated newSession override');
}
const source = extractBalanced(start);
assert.match(source, /_newSessionPromise/, 'concurrent new-session actions share one browser request');
assert.match(source, /_mmSetNewSessionPromiseProjectId\(projectKey\)/, 'the browser records the project key for the current request');
assert.match(html, /function _mmSetNewSessionPromiseProjectId\(value\)/, 'the full project feature supplies a standalone-harness fallback for the compatibility key');
assert.match(source, /_mmNewSessionRequests\.get\(projectKey\)/, 'same-project deduplication is keyed by the normalized project rather than globally');
assert.match(source, /await previousTail/, 'different projects wait for the earlier UI transition and then send their own POST');
assert.match(source, /created\.reused/, 'UI consumes the server reuse receipt without guessing from missing history fields');
assert.match(source, /requestSwitchSeq/, 'a delayed response keeps the sid/sequence navigation defense');

function response(status, body) { return { ok: status >= 200 && status < 300, status, json: async () => body }; }
function flush() { return new Promise((resolve) => setImmediate(resolve)); }
function makeContext(sessions, currentSid) {
  const send = { disabled: false };
  const context = {
    console, JSON, Object, String, Number, Array, Promise, Error, Set, Map,
    currentSid, _switchSeq: 7, _autoScroll: false, _newSessionPromise: null, _newSessionPromiseProjectId: null, _sessionTransitioning: false,
    agentRunning: false, _allSessions: sessions.map((item) => ({ ...item })), _mmPendingProjectId: null, _mmActiveProjectId: null,
    _mmNewSessionRequests: new Map(), _mmNewSessionTail: Promise.resolve(), _mmNewSessionIntent: 0,
    mutations: 0, rendered: 0, switches: [], errors: [], calls: [],
    document: { getElementById: (id) => id === 'send' ? send : null },
    T: (value) => value, t: (value) => value, addError: (message) => context.errors.push(String(message)),
    _mmSetNewSessionPromiseProjectId: (value) => { context._newSessionPromiseProjectId = value; },
    _ensureSessionRenderCache: () => ({}), _mmSessionListMutated: () => { context.mutations++; },
    renderSessionList: () => { context.rendered++; },
    switchSession(sid) { context.currentSid = sid; context._switchSeq++; context.switches.push(sid); },
    _mmCurrentProjectId() { const current = context._allSessions.find((item) => item.id === context.currentSid); return current && current.project_id ? String(current.project_id) : null; }
  };
  context.window = context;
  return context;
}
function install(context, handler) {
  context.fetch = async (url, options = {}) => { context.calls.push({ url, options, body: options.body ? JSON.parse(options.body) : undefined }); return handler(url, options); };
  vm.createContext(context); vm.runInContext(source, context, { filename: 'new-session-v4-ui.js' });
}

(async () => {
  // The UI always asks the server. A returned same-project empty candidate is
  // reused exactly once rather than producing another client-side placeholder.
  const reused = makeContext([
    { id: 'empty-p1', project_id: 'p1', msg_count: 0, is_running: false },
    { id: 'empty-p2', project_id: 'p2', msg_count: 0, is_running: false }
  ], 'empty-p1');
  install(reused, async () => response(200, { id: 'empty-p1', title: 'Empty P1', project_id: 'p1', reused: true }));
  const reusedId = await reused.newSession('p1');
  assert.equal(reusedId, 'empty-p1');
  assert.deepEqual(reused.calls[0].body, { project_id: 'p1' }, 'same-project reuse still goes through the authoritative POST contract');
  assert.deepEqual(reused.switches, ['empty-p1'], 'reuse navigates to the actual returned empty session');
  assert.equal(reused._allSessions.filter((item) => item.id === 'empty-p1').length, 1, 'reuse does not duplicate the existing session row');

  // An empty session in another project cannot be selected locally. The server
  // returns a distinct P1 session and that is the only one the UI displays.
  const crossProject = makeContext([
    { id: 'empty-p2', project_id: 'p2', msg_count: 0, is_running: false },
    { id: 'missing-count-p1', project_id: 'p1', is_running: false }
  ], 'empty-p2');
  install(crossProject, async () => response(201, { id: 'new-p1', title: 'New P1', project_id: 'p1', reused: false }));
  await crossProject.newSession('p1');
  assert.deepEqual(crossProject.switches, ['new-p1'], 'cross-project empty session is never reused');
  assert.equal(crossProject._allSessions.find((item) => item.id === 'new-p1').project_id, 'p1');
  assert.equal(crossProject._allSessions.some((item) => item.id === 'missing-count-p1' && item.id === crossProject.currentSid), false, 'missing msg_count is never treated as client-proven empty');

  // A first-question session cannot be reused even if an old server list also
  // contains an empty row. The client has no local fast path that can mistake
  // history for an empty session.
  const afterQuestion = makeContext([
    { id: 'asked-p1', project_id: 'p1', msg_count: 1, is_running: false },
    { id: 'old-empty-p1', project_id: 'p1', msg_count: 0, is_running: false }
  ], 'asked-p1');
  install(afterQuestion, async () => response(201, { id: 'new-after-question', title: 'New after question', project_id: 'p1', reused: false }));
  await afterQuestion.newSession('p1');
  assert.deepEqual(afterQuestion.switches, ['new-after-question'], 'after first user message, server-created session wins over any stale local candidate');
  assert.equal(afterQuestion.calls.length, 1, 'the UI does not short-circuit server atomic empty-session logic');

  // Concurrent clicks share the same promise/request and accept the server's
  // single reused id. No client race creates a second visible blank session.
  const busy = makeContext([{ id: 'empty-p1', project_id: 'p1', msg_count: 0, is_running: false }], 'empty-p1');
  let resolveBusy;
  install(busy, () => new Promise((resolve) => { resolveBusy = resolve; }));
  const first = busy.newSession('p1'); const second = busy.newSession('p1');
  await flush();
  assert.equal(busy.calls.length, 1, 'busy new-session clicks issue one POST only');
  resolveBusy(response(200, { id: 'empty-p1', title: 'Empty P1', project_id: 'p1', reused: true }));
  assert.deepEqual(await Promise.all([first, second]), ['empty-p1', 'empty-p1'], 'all concurrent callers receive the same server reuse receipt');

  // Concurrent creates for different projects must never receive the other
  // project's promise or payload. They are serialized only at the UI
  // transition boundary: after A settles, B sends its own authoritative POST
  // and the later B intent becomes the active project/session.
  const crossBusy = makeContext([{ id: 'chat-root', project_id: null, msg_count: 1, is_running: false }], 'chat-root');
  let resolveProjectA; let resolveProjectB;
  install(crossBusy, (_url, options) => {
    const projectId = options.body && JSON.parse(options.body).project_id;
    if (projectId === 'p-a') return new Promise((resolve) => { resolveProjectA = resolve; });
    if (projectId === 'p-b') return new Promise((resolve) => { resolveProjectB = resolve; });
    throw new Error(`unexpected project ${projectId}`);
  });
  const createA = crossBusy.newSession('  p-a  ');
  const createB = crossBusy.newSession('p-b');
  await flush();
  assert.equal(crossBusy.calls.length, 1, 'a second project waits for the first UI transition instead of borrowing its request');
  assert.deepEqual(crossBusy.calls[0].body, { project_id: 'p-a' }, 'project IDs are normalized before the request/key are chosen');
  resolveProjectA(response(201, { id: 'new-a', title: 'A', project_id: 'p-a', reused: false }));
  await flush();
  assert.equal(crossBusy.calls.length, 2, 'the queued second project emits its own POST after the first settles');
  assert.deepEqual(crossBusy.calls[1].body, { project_id: 'p-b' }, 'the second request retains its own project ID');
  resolveProjectB(response(201, { id: 'new-b', title: 'B', project_id: 'p-b', reused: false }));
  assert.deepEqual(await Promise.all([createA, createB]), ['new-a', 'new-b'], 'different-project concurrent callers receive their own server session IDs');
  assert.deepEqual(crossBusy.switches, ['new-b'], 'the later project intent wins focus without letting the earlier response steal it');
  assert.equal(crossBusy._mmActiveProjectId, 'p-b', 'the active project follows the latest project create, not the first response');

  // A user who navigates away during a delayed request is not pulled back by
  // that response; the resulting row remains in its project for later use.
  const stale = makeContext([{ id: 'chat-a', project_id: 'p1', msg_count: 1, is_running: false }, { id: 'chat-b', project_id: 'p2', msg_count: 1, is_running: false }], 'chat-a');
  let resolveStale;
  install(stale, () => new Promise((resolve) => { resolveStale = resolve; }));
  const pending = stale.newSession('p1'); await flush(); stale.switchSession('chat-b');
  resolveStale(response(201, { id: 'new-p1-late', title: 'Late P1', project_id: 'p1', reused: false }));
  await pending;
  assert.equal(stale.currentSid, 'chat-b', 'late new/reuse result honors current sid/sequence guard');
  assert.ok(stale._allSessions.some((item) => item.id === 'new-p1-late'), 'late result is retained in its project list without stealing focus');

  console.log('session_empty_reuse_v4_ui.test.js: PASS');
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
