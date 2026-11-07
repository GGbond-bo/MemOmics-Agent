/* Offline project-dialog regressions for project-scoped multi-chat UI. */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map((match) => match[1]);
const i18nScript = scripts.find((source) => source.includes('界面语言 i18n'));
const feature = scripts.find((source) => source.includes('项目级会话 + 远端目录/控制台目标'));
assert.ok(i18nScript && feature, 'project dialog must remain in the feature script');

class ClassList { add() {} remove() {} toggle() {} contains() { return false; } }
class Element {
  constructor(tag = 'div') { this.tagName = String(tag).toUpperCase(); this.children = []; this.options = []; this.style = {}; this.dataset = {}; this.classList = new ClassList(); this._listeners = {}; this.parentNode = null; this.value = ''; this.textContent = ''; this.innerHTML = ''; this.disabled = false; this.readOnly = false; this.type = ''; this.scrollTop = 0; }
  appendChild(child) { child.parentNode = this; this.children.push(child); if (child.tagName === 'OPTION') this.options.push(child); return child; }
  append(...children) { children.forEach((child) => this.appendChild(child)); }
  insertBefore(child, before) { child.parentNode = this; const at = before ? this.children.indexOf(before) : -1; if (at >= 0) this.children.splice(at, 0, child); else this.children.push(child); return child; }
  remove() { if (this.parentNode) { this.parentNode.children = this.parentNode.children.filter((child) => child !== this); this.parentNode = null; } }
  addEventListener(type, listener) { (this._listeners[type] || (this._listeners[type] = [])).push(listener); }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  focus() {}
  scrollIntoView() {}
}
function descendants(root, result = []) { for (const child of root.children || []) { result.push(child); descendants(child, result); } return result; }
function response(status, body) { return { ok: status >= 200 && status < 300, status, json: async () => body }; }
function flush() { return new Promise((resolve) => setImmediate(resolve)); }

// Keep the English dynamic-label audit: new project dialog strings must not
// strand an English user in Chinese.
const i18nContext = { console, URLSearchParams, location: { search: '?lang=en' }, localStorage: { getItem: () => null, setItem: () => {} }, document: { body: new Element('body'), documentElement: { lang: '' }, addEventListener: () => {}, getElementById: () => null, querySelectorAll: () => [] } };
i18nContext.window = i18nContext; vm.createContext(i18nContext); vm.runInContext(i18nScript, i18nContext);
for (const text of [...new Set([...feature.matchAll(/T\(\s*'([^']*)'\s*\)/g)].map((match) => match[1]).filter((text) => /[\u4e00-\u9fff]/.test(text)))]) {
  assert.doesNotMatch(i18nContext.T(text), /[\u4e00-\u9fff]/, `missing English dynamic translation: ${text}`);
}

const elements = new Map();
for (const id of ['session-list', 'session-search', 'cluster-catalog', 'cluster-catalog-tree', 'cluster-catalog-detail', 'cluster-server-cards', 'cluster-server-library-note', 'cc-node']) elements.set(id, new Element(id === 'cc-node' ? 'select' : 'div'));
const body = new Element('body');
const state = {
  calls: [], pickQueue: [], projectSaveQueue: [], failNextProjectSave: false, nextProject: 3, lastNewSessionProjectId: null,
  projects: [{ id: 'p1', name: '已有项目', description: 'desc', workdir: 'D:/old', updated_at: '2026-11-05', session_count: 1 }, { id: 'p-empty', name: '空项目', description: '', workdir: '', updated_at: '2026-11-05', session_count: 0 }],
  sessions: [{ id: 'chat-1', title: '分析会话', created: '2026-11-05', last_active: '2026-11-05', msg_count: 1, project_id: 'p1' }, { id: 'chat-2', title: '另一会话', created: '2026-11-05', last_active: '2026-11-05', msg_count: 1, project_id: 'p1' }]
};
const context = {
  console, JSON, Object, String, Number, Array, Date, Promise, Error, Set, RegExp, encodeURIComponent, AbortController, setTimeout, clearTimeout,
  localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  document: { body, activeElement: null, getElementById: (id) => elements.get(id) || descendants(body).find((item) => item.id === id) || null, createElement: (tag) => new Element(tag) },
  T: (text) => String(text), t: (text) => String(text), escapeHtml: (text) => String(text == null ? '' : text), alert: () => {}, confirm: () => true, prompt: () => '0',
  currentSid: 'chat-1', _allSessions: [], _loadSessionsCtl: null, _hasEverLoaded: false, _consecutiveEmpty: 0, _lastSessionFingerprint: '', _batchMode: false, _selectedSessions: {}, _newSessionPromise: null, _sessionTransitioning: false, _autoScroll: true, agentRunning: false,
  _clusterCfg: { enabled: true, nodes: [] }, clusterNodeChange: () => {}, clusterFillNodeSelect: () => {}, clusterRefreshStatus: async () => {}, clusterRenderResult: () => {}, clusterPrint: () => {}, nbInit: () => {},
  renderSessionList: () => {}, newSession: (projectId) => { state.lastNewSessionProjectId = projectId; }, loadSessions: () => {}, switchSession(sid) { context.currentSid = sid; }, _ensureSessionRenderCache: () => ({}), addError: () => {},
};
context.window = context;
context.fetch = async (url, options = {}) => {
  const method = String(options.method || 'GET').toUpperCase(); const payload = options.body ? JSON.parse(options.body) : {};
  state.calls.push({ url: String(url), method, body: payload });
  if (url === '/api/projects' && method === 'GET') return response(200, { projects: state.projects });
  if (url === '/api/sessions' && method === 'GET') return response(200, { sessions: state.sessions });
  if (url === '/api/sessions/new' && method === 'POST') return response(201, { id: 'chat-created', title: '新会话', project_id: payload.project_id || null });
  if (url === '/api/cluster/catalog' && method === 'GET') return response(200, { schema_version: 1, binding_target: 'account_profile', servers: [], unassigned_profiles: [], orphan_links: [] });
  if (url === '/api/cluster/servers' && method === 'GET') return response(200, { servers: [], legacy_single_server: false });
  if (url === '/api/fs/pick' && method === 'POST') {
    const next = state.pickQueue.shift();
    if (next && next.promise) return next.promise;
    return response(200, next || { ok: false, cancelled: true, paths: [] });
  }
  if (url === '/api/projects' && method === 'POST') {
    const queued = state.projectSaveQueue.shift();
    if (queued && queued.promise) return queued.promise;
    if (state.failNextProjectSave) return response(500, { error: 'save rejected' });
    const project = { id: `p${state.nextProject++}`, ...payload, updated_at: '2026-11-05', session_count: 0 }; state.projects.push(project); return response(201, { ok: true, project });
  }
  if (String(url).startsWith('/api/projects/') && method === 'PATCH') {
    if (state.failNextProjectSave) return response(500, { error: 'save rejected' });
    const project = state.projects.find((item) => String(url).endsWith(`/${item.id}`)); Object.assign(project, payload); return response(200, { ok: true, project });
  }
  throw new Error(`unexpected ${method} ${url}`);
};
vm.createContext(context); vm.runInContext(feature, context, { filename: 'project-console-feature.js' });

async function submitProject(modal, values = {}) {
  for (const [key, value] of Object.entries(values)) modal._projectControls[key].value = String(value);
  await modal._projectSubmit({ preventDefault() {} }); await flush();
}

(async () => {
  await context.loadSessions(); await flush();
  assert.match(elements.get('session-list').innerHTML, /已有项目/, 'project grouping remains visible');
  assert.match(elements.get('session-list').innerHTML, /空项目/, 'empty projects remain available for a first conversation');

  // Folder selection is system-picker-only: read-only input, real mode:dir,
  // and the picked path is included in the normal project API payload.
  const create = await context.projectCreate();
  assert.equal(create._projectControls.workdir.readOnly, true, 'project directory cannot be typed manually');
  state.pickQueue.push({ ok: true, cancelled: false, paths: ['D:/chosen/project'] });
  await create._projectControls.choose.onclick();
  assert.equal(create._projectControls.workdir.value, 'D:/chosen/project');
  const pick = state.calls.find((call) => call.url === '/api/fs/pick');
  assert.deepEqual(pick.body, { mode: 'dir', multiple: false, title: '选择项目目录' }, 'project picker uses the existing directory-picker contract');
  await submitProject(create, { name: '新项目', description: 'optional note' });
  const created = state.calls.find((call) => call.url === '/api/projects' && call.method === 'POST');
  assert.deepEqual(created.body, { name: '新项目', description: 'optional note', workdir: 'D:/chosen/project' }, 'create persists the selected optional directory only as project metadata');

  // A directory is optional; clearing it does not block a valid project save.
  const emptyDir = await context.projectCreate();
  emptyDir._projectControls.workdir.value = 'D:/will-clear'; emptyDir._projectControls.clear.onclick();
  await submitProject(emptyDir, { name: '无目录项目', description: '' });
  const emptyCreated = state.calls.filter((call) => call.url === '/api/projects' && call.method === 'POST').at(-1);
  assert.equal(emptyCreated.body.workdir, '', 'project directory may be intentionally empty');

  // A save owns its dialog until the response settles.  Cancel, Escape,
  // backdrop clicks, and a second opener cannot replace the draft; an old
  // create response also must not steal a chat/project chosen while waiting.
  context.switchSession('chat-1');
  const saving = await context.projectCreate();
  saving._projectControls.name.value = '延迟保存项目';
  let resolveDelayedSave;
  state.projectSaveQueue.push({ promise: new Promise((resolve) => { resolveDelayedSave = resolve; }) });
  const delayedSave = saving._projectSubmit({ preventDefault() {} });
  await flush();
  assert.equal(saving._projectBusy, true, 'a submitted project dialog enters a busy state');
  for (const control of Object.values(saving._projectControls)) assert.equal(control.disabled, true, 'all project editor controls are locked while saving');
  saving._projectControls.cancel.onclick();
  (saving._listeners.keydown || [])[0]({ key: 'Escape', preventDefault() {} });
  (saving._listeners.click || [])[0]({ target: saving });
  assert.ok(saving.parentNode, 'close affordances cannot dismiss an in-flight project save');
  const attemptedReopen = await context.projectCreate();
  assert.strictEqual(attemptedReopen, saving, 'a new project opener reuses rather than replaces the busy dialog');
  context.switchSession('chat-2');
  resolveDelayedSave(response(201, { ok: true, project: { id: 'p-late', name: '延迟保存项目', description: '', workdir: '', updated_at: '2026-11-05', session_count: 0 } }));
  await delayedSave; await flush();
  assert.equal(saving.parentNode, null, 'the successful in-flight request may close only its own dialog');
  context.projectNewSession(); await flush();
  const afterDelayedNewSession = state.calls.filter((call) => call.url === '/api/sessions/new' && call.method === 'POST').at(-1);
  assert.deepEqual(afterDelayedNewSession.body, { project_id: 'p1' }, 'a delayed project create never steals the project selected after submission');

  // Native-dialog cancellation never overwrites the existing edit value.
  const edit = await context.projectEdit('p1');
  state.pickQueue.push({ ok: false, cancelled: true, paths: [] });
  await edit._projectControls.choose.onclick();
  assert.equal(edit._projectControls.workdir.value, 'D:/old', 'picker cancellation preserves the existing selected directory');
  edit._projectControls.cancel.onclick();

  // A late response from an old dialog cannot populate a newly opened dialog.
  let resolveLate;
  const old = await context.projectCreate();
  state.pickQueue.push({ promise: new Promise((resolve) => { resolveLate = resolve; }) });
  const latePick = old._projectControls.choose.onclick();
  old._projectControls.cancel.onclick();
  const fresh = await context.projectCreate();
  fresh._projectControls.workdir.value = 'D:/fresh';
  resolveLate(response(200, { ok: true, cancelled: false, paths: ['D:/late-wrong'] }));
  await latePick; await flush();
  assert.equal(fresh._projectControls.workdir.value, 'D:/fresh', 'late picker response must not write into a reopened dialog');
  fresh._projectControls.cancel.onclick();

  // Validation and server failure leave the same dialog/data available for correction.
  const failed = await context.projectCreate();
  await submitProject(failed, { name: '' });
  assert.ok(failed.parentNode, 'empty name keeps the project dialog open');
  state.failNextProjectSave = true;
  await submitProject(failed, { name: '保留草稿', description: 'do not lose me' });
  assert.ok(failed.parentNode, 'failed save keeps the dialog open');
  assert.equal(failed._projectControls.name.value, '保留草稿', 'failed save preserves name draft');
  assert.equal(failed._projectControls.description.value, 'do not lose me', 'failed save preserves optional description draft');
  assert.equal(failed._projectControls.save.disabled, false, 'failed save restores the button');
  state.failNextProjectSave = false;
  (failed._listeners.keydown || [])[0]({ key: 'Escape', preventDefault() {} });
  assert.equal(failed.parentNode, null, 'Escape closes the project dialog');

  console.log('project_sessions_ui.test.js: PASS');
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
