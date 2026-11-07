/*
 * Offline lifecycle regressions for the 2026-11 session-reliability repair.
 *
 * This runs selected real functions from index.html in a small VM.  It never
 * starts a browser, opens a socket, reaches an LLM, or connects to SSH.
 */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');

function extractFunction(signature) {
  const start = html.indexOf(signature);
  assert.ok(start >= 0, `missing function: ${signature}`);
  const open = html.indexOf('{', start);
  assert.ok(open >= 0, `missing body: ${signature}`);
  let depth = 0;
  let quote = '';
  let lineComment = false;
  let blockComment = false;
  let escaped = false;
  for (let index = open; index < html.length; index++) {
    const char = html[index];
    const next = html[index + 1];
    if (lineComment) {
      if (char === '\n') lineComment = false;
      continue;
    }
    if (blockComment) {
      if (char === '*' && next === '/') { blockComment = false; index++; }
      continue;
    }
    if (quote) {
      if (escaped) { escaped = false; continue; }
      if (char === '\\') { escaped = true; continue; }
      if (char === quote) quote = '';
      continue;
    }
    if (char === '/' && next === '/') { lineComment = true; index++; continue; }
    if (char === '/' && next === '*') { blockComment = true; index++; continue; }
    if (char === '\'' || char === '"' || char === '`') { quote = char; continue; }
    if (char === '{') depth++;
    if (char === '}') {
      depth--;
      if (depth === 0) return html.slice(start, index + 1);
    }
  }
  throw new Error(`unterminated function: ${signature}`);
}

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

class Element {
  constructor(value = '') {
    this.value = value;
    this.textContent = '';
    this.innerHTML = '';
    this.style = {};
    this.disabled = false;
    this.classList = { add() {}, remove() {}, contains: () => false };
  }
}

function baseContext() {
  const elements = new Map();
  for (const id of ['input', 'send', 'stop', 'steer-hint', 'messages', 'results-figures', 'results-list',
    'results-path', 'results-tabs', 'results-sortbar', 'figure-preview-area', 'model-select', 'model-badge',
    'settings-provider-select', 'settings-custom-model', 'settings-model', 'settings-base-url',
    'settings-api-key', 'settings-provider', 'sk-chips', 'sk-pick-btn']) elements.set(id, new Element());
  const context = {
    console,
    JSON,
    Object,
    String,
    Number,
    Array,
    Date,
    Promise,
    Error,
    Set,
    encodeURIComponent,
    clearTimeout: () => {},
    setTimeout: () => 1,
    currentSid: null,
    _switchSeq: 0,
    _sessionTransitioning: false,
    _newSessionPromise: null,
    pendingImages: [],
    _allSessions: [],
    _lastSessionFingerprint: '',
    _currentRunningSid: null,
    agentRunning: false,
    fullText: '', fullSegs: [], _segBreak: false, reasoningText: '', currentAssistantEl: null,
    currentBubble: null, progressTimelineEl: null, progressItems: [], _lastMermaidHash: '',
    _p8: { pinned: [], used: {}, max: 5 },
    _p8Sid: () => context.currentSid || null,
    _goalBar: { sid: '', goal: null, todos: [], revision: 0 },
    _sessionScopedEventTypes: new Set(['error']),
    _ACTIVITY_TYPES: {},
    _viewIsStreamEvent: () => false,
    _viewRunStart: () => {},
    _taskWsLive: false,
    document: {
      getElementById: (id) => elements.get(id) || null,
      querySelector: () => ({ style: {} }),
      querySelectorAll: () => [],
    },
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    T: (value) => value,
    t: (value) => value,
    tf: (value) => value,
    escapeHtml: (value) => String(value == null ? '' : value),
    showToast: (message) => context.toasts.push(String(message)),
    addError: (message) => context.errors.push(String(message)),
    addStatusNotice: (message) => context.notices.push(String(message)),
    addUserMsg: (text) => context.userMessages.push(String(text)),
    setFloatBar: () => {},
    clearPendingImages: () => { context.pendingImages = []; },
    uploadPendingImages: async () => [],
    _ensureSessionRenderCache: (sid) => (context.caches[sid] || (context.caches[sid] = { pendingEvents: [] })),
    _bufferSessionEvent: (cache, message) => cache.pendingEvents.push(message),
    updateSessionListThrottled: () => { context.listRefreshes++; },
    updateSessionList: () => { context.listRefreshes++; },
    renderSessionList: () => { context.renderedLists++; },
    renderTaskList: () => {}, refreshTaskDetail: () => {}, handleWeixinMessage: () => {},
    _splitProcessConclusion: () => {},
    renderSkillChips: () => { context.skillRenders++; },
    renderTodos: (todos) => { context.todosRendered = todos; },
    renderGoalBar: () => {}, refreshOutline: () => { context.outlineRefreshes++; },
    _sortItems: (items) => items,
    _rsNewFilterOn: () => false, _rsJustNewOf: () => ({}), _renderSortBar: () => {},
    _visibleResultItems: (items) => items, _showUnreadOnly: false, _lastFiguresSig: '', _lastFilesSig: '',
    _lastFigItems: [], _lastFigBase: '', _lastFiguresCount: 0, _lastResultItems: [], _lastFilesCount: 0,
    _lastFilesShown: 0, currentPath: { results: '' }, UI_LANG: 'zh', _resultsSort: 'time_desc',
    _rsBadgeRender: () => {}, _rsBadgeScan: () => {}, _resultsTabPick: { sid: '', tab: '' }, resultsTab: 'figures',
    switchResultsTab: () => {}, _rsJustNewHas: () => false, formatSize: () => '', _fileViewBtn: () => '',
    _renderModelChip: () => {}, loadEffortSetting: () => {}, refreshFooterVersion: () => {},
    refreshConnectedModels: async () => {}, loadProviders: async () => {}, loadSessions: () => {},
    allProviders: [], currentModel: {}, models: [],
    toasts: [], errors: [], notices: [], userMessages: [], caches: {}, listRefreshes: 0,
    renderedLists: 0, skillRenders: 0, outlineRefreshes: 0,
  };
  context.window = context;
  context.elements = elements;
  return context;
}

async function testSaveModelUsesStableProviderId() {
  const context = baseContext();
  context.elements.get('settings-provider-select').value = 'provider-stable';
  context.elements.get('settings-model').value = 'model-x';
  context.elements.get('settings-provider').value = 'legacy-wrong-provider';
  const calls = [];
  context.fetch = async (url, options = {}) => {
    calls.push({ url, body: options.body ? JSON.parse(options.body) : null });
    if (url === '/api/models/available') return response(200, { models: [{ provider_id: 'provider-stable', model_ready: true }] });
    if (url === '/api/models/switch') return response(200, { current: { model: 'model-x', provider_id: 'provider-stable' } });
    throw new Error(`unexpected ${url}`);
  };
  context.alert = (message) => context.toasts.push(String(message));
  vm.createContext(context);
  vm.runInContext(extractFunction('async function saveModel()'), context);
  await context.saveModel();
  const switchCall = calls.find((call) => call.url === '/api/models/switch');
  assert.deepEqual(switchCall.body, { model: 'model-x', provider_id: 'provider-stable' },
    'global save must use provider_id and omit a blank api_key');
  assert.equal(context.currentModel.model, 'model-x');
}

async function testSendCreateSwitchAndLateEvents() {
  const context = baseContext();
  const sent = [];
  context.ws = { readyState: 1, send: (raw) => sent.push(JSON.parse(raw)) };
  context.newSession = async () => { context.currentSid = 'chat-a'; context._switchSeq = 1; return 'chat-a'; };
  context.switchSession = () => { throw new Error('background update must never switch sessions'); };
  vm.createContext(context);
  const supportStart = html.indexOf('var _chatRequestSeq = 0;');
  const supportEnd = html.indexOf('// === P3', supportStart);
  assert.ok(supportStart >= 0 && supportEnd > supportStart, 'send receipt helpers must remain extractable');
  vm.runInContext(html.slice(supportStart, supportEnd), context, { filename: 'send-receipts.js' });
  vm.runInContext(extractFunction('function handleMessage(msg)'), context, { filename: 'handle-message.js' });

  const input = context.elements.get('input');
  input.value = 'create then send A';
  await context.send(false);
  const chat = sent.find((payload) => payload.type === 'chat');
  assert.equal(chat.session_id, 'chat-a');
  assert.ok(chat.request_id, 'chat sends a request id for server acknowledgement');
  assert.equal(input.value, '', 'accepted browser transport clears the active draft only');

  // The user now moves to B and types a different message.  A late update or
  // acknowledgement must update A's cache/list, never redirect or clear B.
  context.currentSid = 'chat-b';
  context._switchSeq = 2;
  input.value = 'new B draft';
  context._allSessions = [{ id: 'chat-a' }, { id: 'chat-b' }];
  context.handleMessage({ type: 'session_update', session_id: 'chat-a', is_running: true });
  assert.equal(context.currentSid, 'chat-b', 'background session_update must not steal focus');
  assert.equal(input.value, 'new B draft', 'background session_update must preserve another chat draft');
  context.handleMessage({ type: 'chat_accepted', session_id: 'chat-a', request_id: chat.request_id });
  assert.equal(context.currentSid, 'chat-b', 'late chat acknowledgement must not switch sessions');
  assert.equal(input.value, 'new B draft', 'late acknowledgement must not clear B draft');

  context.currentSid = 'chat-a';
  context._switchSeq = 3;
  input.value = 'retry A';
  await context.send(false);
  const failedChat = sent.filter((payload) => payload.type === 'chat').at(-1);
  context.currentSid = 'chat-b';
  context._switchSeq = 4;
  input.value = 'B stays intact';
  context.handleMessage({ type: 'error', session_id: 'chat-a', request_id: failedChat.request_id, content: 'A failed' });
  assert.equal(input.value, 'B stays intact', 'late A error must never overwrite B input');
  assert.equal(context.caches['chat-a'].inputDraft, 'retry A', 'late A error keeps its draft with A');

  context.handleMessage({ type: 'error', scope: 'protocol', content: 'bad frame' });
  assert.equal(context.currentSid, 'chat-b', 'protocol errors must not end or redirect a chat');
  assert.ok(context.toasts.some((message) => message.includes('bad frame')), 'protocol failures must be visible');
}

async function testLateAsyncResponsesAreDropped() {
  const context = baseContext();
  let resolveSkills;
  let resolveTodos;
  let resolveFigures;
  context.currentSid = 'chat-a';
  context._switchSeq = 7;
  context.fetch = (url) => {
    if (url.endsWith('/skills')) return new Promise((resolve) => { resolveSkills = resolve; });
    if (url.endsWith('/todos/chat-a')) return new Promise((resolve) => { resolveTodos = resolve; });
    if (url.includes('/results/chat-a/figures')) return new Promise((resolve) => { resolveFigures = resolve; });
    throw new Error(`unexpected ${url}`);
  };
  vm.createContext(context);
  vm.runInContext(extractFunction('async function loadPinnedSkills(sid)'), context);
  vm.runInContext(extractFunction('async function refreshTodos()'), context);
  vm.runInContext(extractFunction('async function loadFigures()'), context);
  const skillsPending = context.loadPinnedSkills('chat-a');
  const todosPending = context.refreshTodos();
  const figuresPending = context.loadFigures();
  context.currentSid = 'chat-b';
  context._switchSeq = 8;
  resolveSkills(response(200, { pinned: [{ name: 'from-a' }], used: {} }));
  resolveTodos(response(200, { todos: [{ text: 'from-a' }], revision: 4 }));
  resolveFigures(response(200, { figures: [{ name: 'from-a.png' }] }));
  await Promise.all([skillsPending, todosPending, figuresPending]);
  assert.deepEqual(context._p8.pinned, [], 'late A skills must not overwrite B skills');
  assert.equal(context.todosRendered, undefined, 'late A todos must not render into B');
  assert.equal(context._lastFiguresCount, 0, 'late A figures must not replace B results');
}

(async () => {
  // Source-level guards prevent a future edit from bringing back the known
  // race even if its simulated branch is not taken in this small VM.
  assert.match(html, /_mmSessionListRevision/, 'session list mutations need a revision guard');
  assert.match(html, /listRevision !== _mmSessionListRevision/, 'stale list GET must be discarded');
  assert.match(html, /chat_accepted/, 'server receipt must be handled');
  assert.match(html, /scope === 'protocol'/, 'unscoped protocol errors need their own path');
  assert.match(html, /provider_id: pid/, 'global model save must send provider_id');
  await testSaveModelUsesStableProviderId();
  await testSendCreateSwitchAndLateEvents();
  await testLateAsyncResponsesAreDropped();
  console.log('session_lifecycle_v2.test.js: PASS');
})().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
