/* Offline regressions for session-scoped mutations and reliable deletion. */
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

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}
function flush() { return new Promise((resolve) => setImmediate(resolve)); }

function goalContext() {
  const context = {
    console: { log: console.log, error: () => {} }, JSON, Object, String, Number, Array, Promise, Error, Set, encodeURIComponent,
    currentSid: 'chat-a', _switchSeq: 1,
    _goalBar: { sid: 'chat-a', goal: { objective: 'A goal' }, todos: [{ id: 'a-todo' }], revision: 0, collapsed: false, editing: false },
    document: { getElementById: () => null },
    T: (text) => String(text), confirm: () => true,
    restoreGoalTextEl: () => {}, renderGoalBar: () => { context.renders++; },
    renderTodos: (todos) => { context._goalBar.todos = Array.isArray(todos) ? todos : []; context.renders++; },
    applyGoalPayload: (payload) => {
      if ('goal' in payload) context._goalBar.goal = payload.goal || null;
      if (Array.isArray(payload.todos)) context._goalBar.todos = payload.todos;
      context.renders++;
    },
    addError: (message) => context.errors.push(String(message)),
    errors: [], renders: 0,
  };
  context.window = context;
  return context;
}

async function testLateGoalAndTodoResponsesAreDropped() {
  const context = goalContext();
  let resolveSave;
  context.fetch = (url) => {
    assert.match(String(url), /chat-a\/(goal|todos)/, 'mutation must capture A before a switch');
    return new Promise((resolve) => { resolveSave = resolve; });
  };
  vm.createContext(context);
  const helperStart = html.indexOf('function _goalBarResetForSession');
  const helperEnd = html.indexOf('function _goalStatusLabel', helperStart);
  assert.ok(helperStart >= 0 && helperEnd > helperStart, 'goal mutation guard must be present');
  vm.runInContext(html.slice(helperStart, helperEnd), context, { filename: 'goal-guard.js' });
  vm.runInContext(extractFunction('async function saveGoal(text)'), context);
  vm.runInContext(extractFunction('async function clearGoal()'), context);
  vm.runInContext(extractFunction('async function clearTodos()'), context);

  const saving = context.saveGoal('new A objective');
  context.currentSid = 'chat-b'; context._switchSeq = 2;
  context._goalBar = { sid: 'chat-b', goal: { objective: 'B goal' }, todos: [{ id: 'b-todo' }], revision: 7, collapsed: false };
  resolveSave(response(200, { ok: true, goal: { objective: 'new A objective' }, todos: [] }));
  await saving;
  assert.equal(context._goalBar.goal.objective, 'B goal', 'late save response must not overwrite B goal');
  assert.deepEqual(context._goalBar.todos, [{ id: 'b-todo' }], 'late save response must not clear B todos');

  // A late failure also must not add an error bubble to B.
  context.currentSid = 'chat-a'; context._switchSeq = 3; context._goalBar = { sid: 'chat-a', goal: { objective: 'A goal' }, todos: [{ id: 'a-todo' }] };
  const failedSave = context.saveGoal('will fail');
  context.currentSid = 'chat-b'; context._switchSeq = 4; context._goalBar = { sid: 'chat-b', goal: { objective: 'B remains' }, todos: [{ id: 'b-remains' }] };
  resolveSave(response(500, { error: 'server refused' }));
  await failedSave;
  assert.equal(context.errors.length, 0, 'late A failure must not render an error in B');

  context.currentSid = 'chat-a'; context._switchSeq = 5; context._goalBar = { sid: 'chat-a', goal: { objective: 'A goal' }, todos: [{ id: 'a-todo' }] };
  const clearing = context.clearTodos();
  context.currentSid = 'chat-b'; context._switchSeq = 6; context._goalBar = { sid: 'chat-b', goal: { objective: 'B goal' }, todos: [{ id: 'b-todo' }] };
  resolveSave(response(200, { ok: true, todos: [] }));
  await clearing;
  assert.deepEqual(context._goalBar.todos, [{ id: 'b-todo' }], 'late clearTodos response must not clear B todos');

  // A has an active goal, then the user switches to B.  A B-scoped websocket
  // update may arrive before B's history/todos HTTP request; it must start
  // from a B-owned bar instead of mixing in A's goal.
  context.currentSid = 'chat-a'; context._switchSeq = 7;
  context._goalBar = { sid: 'chat-a', goal: { objective: 'A visible goal' }, todos: [{ id: 'a-visible' }], revision: 2, collapsed: true };
  context.currentSid = 'chat-b'; context._switchSeq = 8;
  context._goalBarResetForSession('chat-b');
  context._goalApplyPayloadForSession('chat-b', { session_id: 'chat-b', goal: { objective: 'B websocket goal' } });
  context._goalRenderTodosForSession('chat-b', [{ id: 'b-websocket' }]);
  assert.equal(context._goalBar.sid, 'chat-b', 'switch resets the goal bar ownership before B websocket state arrives');
  assert.equal(context._goalBar.goal.objective, 'B websocket goal', 'B websocket goal replaces the reset state, never A state');
  assert.deepEqual(context._goalBar.todos, [{ id: 'b-websocket' }], 'B websocket todos belong to B only');

  assert.match(html, /currentSid = sid;[\s\S]{0,420}_goalBarResetForSession\(sid\)/,
    'switchSession must reset goal-bar ownership immediately after switching');
  assert.match(html, /'todos_update', 'goal_update'/, 'goal updates must use the session-scoped websocket gate');
  assert.match(html, /_goalRenderTodosForSession\(msg\.session_id, msg\.todos\)/, 'websocket todos must ensure the current bar belongs to their session');
  assert.match(html, /_goalApplyPayloadForSession\(msg\.session_id, msg\)/, 'websocket goals must ensure the current bar belongs to their session');
}

function deleteContext() {
  const elements = new Map();
  for (const id of ['batch-delete-btn', 'messages', 'chat-title']) elements.set(id, { style: {}, disabled: false, textContent: '', innerHTML: '' });
  const context = {
    console: { log: console.log, error: () => {} }, JSON, Object, String, Number, Array, Promise, Error, Set, encodeURIComponent,
    currentSid: 'chat-a', _allSessions: [{ id: 'chat-a' }, { id: 'chat-b' }], _selectedSessions: {}, _batchMode: true,
    _lastSessionFingerprint: '', _sessionDeleteRequests: undefined,
    document: { getElementById: (id) => elements.get(id) || null },
    localStorage: { removeItem: () => {} },
    window: null,
    _p8: { pinned: [], used: {} },
    renderSkillChips: () => {}, _dropViewSnapshot: (sid) => context.dropped.push(sid),
    renderSessionList: () => { context.rendered++; }, loadSessions: () => { context.loads++; },
    switchSession: (sid) => { context.switches.push(sid); context.currentSid = sid; }, showNewSessionWelcome: () => {},
    toggleBatchMode: () => { context.toggledBatch++; }, updateBatchCount: () => { context.updatedBatch++; },
    confirm: () => true, alert: (message) => context.alerts.push(String(message)),
    dropped: [], rendered: 0, loads: 0, switches: [], alerts: [], toggledBatch: 0, updatedBatch: 0, mutations: 0,
  };
  context.window = context;
  context.window._mmSessionListMutated = () => { context.mutations++; };
  return context;
}

function installDeletionFunctions(context) {
  const start = html.indexOf('var _sessionDeleteRequests = {};');
  const end = html.indexOf('var _lastSessionFingerprint =', start);
  assert.ok(start >= 0 && end > start, 'deletion reliability helpers must be present');
  vm.createContext(context);
  vm.runInContext(html.slice(start, end), context, { filename: 'delete-helpers.js' });
  vm.runInContext(extractFunction('function deleteSession(sid)'), context, { filename: 'delete-one.js' });
}

async function testDeleteOnlyMutatesAfterAcceptedResponse() {
  const failed = deleteContext();
  failed.fetch = async () => response(409, { ok: false, error: 'still running' });
  installDeletionFunctions(failed);
  failed.deleteSession('chat-a');
  await flush(); await flush();
  assert.deepEqual(failed._allSessions.map((session) => session.id), ['chat-a', 'chat-b'], 'failed single delete must retain its row');
  assert.equal(failed.currentSid, 'chat-a', 'failed single delete must retain the current chat');
  assert.equal(failed.mutations, 0, 'failed single delete must not invalidate the list as if it succeeded');
  assert.ok(failed.alerts.some((message) => message.includes('删除会话失败')), 'failed single delete must be visible');

  const late = deleteContext();
  let resolveDelete;
  late.fetch = () => new Promise((resolve) => { resolveDelete = resolve; });
  installDeletionFunctions(late);
  late.deleteSession('chat-a');
  late.currentSid = 'chat-b';
  resolveDelete(response(200, { ok: true }));
  await flush(); await flush();
  assert.deepEqual(late._allSessions.map((session) => session.id), ['chat-b'], 'accepted late delete removes only the deleted A row');
  assert.equal(late.currentSid, 'chat-b', 'late A delete result must not redirect the user away from B');
  assert.deepEqual(late.switches, [], 'late A delete result must not switch sessions');

  const batch = deleteContext();
  batch._selectedSessions = { 'chat-a': true, 'chat-b': true };
  batch.fetch = async (url) => String(url).endsWith('/chat-a') ? response(200, { ok: true }) : response(500, { ok: false, error: 'retained' });
  installDeletionFunctions(batch);
  batch.batchDeleteSelected();
  await flush(); await flush();
  assert.deepEqual(batch._allSessions.map((session) => session.id), ['chat-b'], 'batch delete removes only accepted rows');
  assert.deepEqual(Object.keys(batch._selectedSessions), ['chat-b'], 'failed batch row remains selected for retry');
  assert.equal(batch.loads, 1, 'a successful batch mutation refreshes the canonical list once');
  assert.equal(batch.toggledBatch, 0, 'partial failure keeps batch mode instead of discarding the retry selection');
  assert.ok(batch.alerts.some((message) => message.includes('未删除')), 'partial batch failure is visible');
}

(async () => {
  await testLateGoalAndTodoResponsesAreDropped();
  await testDeleteOnlyMutatesAfterAcceptedResponse();
  console.log('session_mutation_guards_v2.test.js: PASS');
})().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
