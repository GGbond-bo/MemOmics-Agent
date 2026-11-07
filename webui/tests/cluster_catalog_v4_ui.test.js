/* Offline V5 catalog-unit regressions. No browser, SSH, model, or real secret is used. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map((match) => match[1]);
const feature = scripts.find((source) => source.includes('MemOmics V5: server / node / user / matched-connection UI'));
assert.ok(feature, 'V5 catalog feature exists');
assert.match(feature, /cluster-catalog-add-server/);
assert.match(feature, /addEventListener\('click'/);
assert.doesNotMatch(feature, /target_password|gateway_password|key_path|use_app_managed_key|route_mode/);
assert.doesNotMatch(feature, /localStorage|sessionStorage/);
assert.doesNotMatch(html, /install_key|装公钥|安装公钥|私钥|key_path|target_password|gateway_password|use_app_managed_key|route_mode|cw-mask|cluster-catalog-tree|cluster-catalog-detail|cluster-server-cards/i, 'whole page has no retired key, wizard, or old catalog surface');
assert.match(html, /应用不会将密码保存到浏览器存储、聊天记录或配置文件/, 'password notice distinguishes application persistence from transient page memory or browser extensions');
for (const id of ['cluster-console', 'cluster-out', 'cc-node', 'nb-mask', 'nb-cells', 'nb-code', 'nb-run-btn']) {
  assert.match(html, new RegExp(`id="${id}"`), `${id} remains for the console or Notebook`);
}

function clone(value) { return JSON.parse(JSON.stringify(value)); }
function response(status, data) { return { ok: status >= 200 && status < 300, status, json: async () => clone(data) }; }
function flush() { return new Promise((resolve) => setImmediate(resolve)); }

class ClassList {
  constructor() { this.values = new Set(); }
  add(...values) { values.filter(Boolean).forEach((value) => this.values.add(String(value))); }
  remove(...values) { values.forEach((value) => this.values.delete(String(value))); }
  contains(value) { return this.values.has(String(value)); }
}
class Element {
  constructor(tag = 'div') {
    this.tagName = String(tag).toUpperCase(); this.children = []; this.options = []; this.parentNode = null;
    this.classList = new ClassList(); this.style = {}; this.dataset = {}; this.listeners = {}; this.attrs = {};
    this.id = ''; this.textContent = ''; this.value = ''; this.title = ''; this.type = ''; this.name = '';
    this.disabled = false; this.checked = false; this.required = false; this._innerHTML = '';
  }
  get className() { return [...this.classList.values].join(' '); }
  set className(value) { this.classList.values = new Set(String(value || '').split(/\s+/).filter(Boolean)); }
  get innerHTML() { return this._innerHTML; }
  set innerHTML(value) { this._innerHTML = String(value); this.children.forEach((child) => { child.parentNode = null; }); this.children = []; this.options = []; }
  get firstChild() { return this.children[0] || null; }
  appendChild(child) { if (child.parentNode) child.parentNode.removeChild(child); child.parentNode = this; this.children.push(child); if (child.tagName === 'OPTION') this.options.push(child); return child; }
  insertBefore(child, before) { if (child.parentNode) child.parentNode.removeChild(child); child.parentNode = this; const index = this.children.indexOf(before); if (index < 0) this.children.push(child); else this.children.splice(index, 0, child); if (child.tagName === 'OPTION') this.options.push(child); return child; }
  removeChild(child) { this.children = this.children.filter((item) => item !== child); this.options = this.options.filter((item) => item !== child); child.parentNode = null; return child; }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  addEventListener(type, listener) { (this.listeners[type] || (this.listeners[type] = [])).push(listener); }
  click() { const event = { target: this, currentTarget: this, preventDefault() {}, stopPropagation() {} }; if (typeof this.onclick === 'function') this.onclick(event); (this.listeners.click || []).forEach((listener) => listener.call(this, event)); }
  setAttribute(name, value) { this.attrs[name] = String(value); if (name === 'id') this.id = String(value); }
  getAttribute(name) { return Object.hasOwn(this.attrs, name) ? this.attrs[name] : null; }
  querySelector() { return null; }
  closest() { return null; }
  focus() {}
  scrollIntoView() {}
}
function descendants(root, output = []) { for (const child of root.children || []) { output.push(child); descendants(child, output); } return output; }
function byClass(root, name) { return descendants(root).filter((item) => item.classList.contains(name)); }
function textOf(root) { return [root, ...descendants(root)].map((item) => item.textContent || '').join(' '); }

const body = new Element('body');
const elements = new Map();
for (const [id, tag] of [
  ['cluster-catalog-add-server', 'button'], ['cluster-catalog-feedback', 'div'], ['cluster-catalog', 'div'], ['v5-server-list', 'div'],
  ['cluster-server-library-note', 'span'], ['cluster-chip', 'span'], ['cluster-node-chip', 'span'], ['cc-node', 'select']
]) { const item = new Element(tag); item.id = id; elements.set(id, item); body.appendChild(item); }
const document = {
  body, documentElement: { lang: 'zh-CN' }, createElement: (tag) => new Element(tag),
  getElementById(id) { return elements.get(id) || descendants(body).find((item) => item.id === id) || null; }
};

const catalog = {
  schema_version: 2,
  servers: [{
    id: 'srv-a', name: 'Faculty cluster', description: 'main', node_count: 2,
    nodes: [
      { id: 'node-login', name: 'login', host: 'login.example.edu', port: 22, is_login: true, is_compute: false, note: '' },
      { id: 'node-compute', name: 'software', host: 'cngb-software-0-1', port: 22, is_login: false, is_compute: true, note: 'software install' }
    ],
    accounts: [
      { id: 'acc-alice', name: 'Alice', user: 'alice', note: 'existing note', credential_state: 'configured' },
      { id: 'acc-bob', name: 'Bob', user: 'bob', credential_state: 'configured' }
    ],
    connections: [
      { id: 'p-alice', profile_id: 'p-alice', node_id: 'node-login', account_id: 'acc-alice', name: 'login · Alice', node: { id: 'node-login', name: 'login', host: 'login.example.edu', port: 22, is_login: true }, account: { id: 'acc-alice', name: 'Alice', user: 'alice', credential_state: 'configured' }, route: { mode: 'direct' }, last_connected_at: '2026-11-06T10:00:00Z' },
      { id: 'p-gateway', profile_id: 'p-gateway', node_id: 'node-login', account_id: 'acc-gateway', name: 'login · Gateway', node: { id: 'node-login', name: 'login', host: 'login.example.edu', port: 22, is_login: true }, account: { id: 'acc-gateway', name: 'Gateway', user: 'gateway', credential_state: 'configured' }, route: { mode: 'direct' }, last_connected_at: '2026-11-06T10:00:00Z' }
    ]
  }],
  unassigned_profiles: [], orphan_links: []
};
const state = { catalog, calls: [], next: 1 };
function findNode(id) { for (const server of state.catalog.servers) { const node = server.nodes.find((item) => item.id === id); if (node) return { server, node }; } return null; }
function findAccount(id) { for (const server of state.catalog.servers) { const account = server.accounts.find((item) => item.id === id); if (account) return { server, account }; } return null; }
function lastCall(check) { return state.calls.filter(check).at(-1); }

const context = {
  console: { info() {}, error() {} }, document, alert() {}, confirm: () => true, currentSid: 'chat-a',
  clusterPrint() {}, clusterRenderResult() {}, clusterNodeChange() {}, clusterFillNodeSelect() {}, clusterRefreshStatus: async () => {},
  _mmGetConsoleAccount: () => null, switchSession() {}, setTimeout() {}, clearTimeout() {}, Promise, Error, Object, String, Number, Array, Set, Date, Math, encodeURIComponent
};
context.window = context;
context.fetch = async (url, options = {}) => {
  const method = String(options.method || 'GET').toUpperCase(); const payload = options.body ? JSON.parse(options.body) : undefined;
  state.calls.push({ url: String(url), method, body: payload });
  if (url === '/api/cluster/catalog' && method === 'GET') return response(200, state.catalog);
  if (url === '/api/cluster/catalog/servers' && method === 'POST') {
    const id = `srv-${state.next++}`; const login = { id: `node-${state.next++}`, name: payload.login_node.name, host: payload.login_node.host, port: payload.login_node.port, is_login: true, is_compute: false };
    const created = { id, name: payload.name, node_count: 1, nodes: [login], accounts: [], connections: [] }; state.catalog.servers.push(created);
    return response(201, { ok: true, server: clone(created), node: clone(login) });
  }
  const accountPost = String(url).match(/^\/api\/cluster\/catalog\/servers\/([^/]+)\/accounts$/);
  if (accountPost && method === 'POST') { const server = state.catalog.servers.find((item) => item.id === accountPost[1]); const { password, ...safe } = payload; const account = { ...safe, id: `acc-${state.next++}`, credential_state: password ? 'configured' : 'missing' }; server.accounts.push(account); return response(201, { ok: true, account: clone(account) }); }
  const accountPatch = String(url).match(/^\/api\/cluster\/catalog\/accounts\/([^/]+)$/);
  if (accountPatch && method === 'PATCH') { const found = findAccount(accountPatch[1]); const { password, ...safe } = payload; Object.assign(found.account, safe); if (password) found.account.credential_state = 'configured'; return response(200, { ok: true, account: clone(found.account) }); }
  const match = String(url).match(/^\/api\/cluster\/catalog\/servers\/([^/]+)\/connections\/match$/);
  if (match && method === 'POST') {
    const server = state.catalog.servers.find((item) => item.id === match[1]); const node = findNode(payload.node_id).node; const account = findAccount(payload.account_id).account;
    const profile = `profile-${state.next++}`; const route = node.is_login ? { mode: 'direct' } : { mode: 'via_login', gateway_profile_id: payload.gateway_profile_id };
    const connection = { id: profile, profile_id: profile, node_id: node.id, account_id: account.id, name: payload.connection.name, node: clone(node), account: clone(account), route, last_connected_at: '2026-11-06T12:00:00Z' };
    server.connections.push(connection); return response(201, { ok: true, stage: 'nodes_probe', code: 'ok', profile_id: profile, connection: clone(connection) });
  }
  return response(200, { ok: true });
};

vm.createContext(context);
vm.runInContext(feature, context, { filename: 'catalog-v5.js' });
async function submit(modal, values) { for (const [key, value] of Object.entries(values)) modal._v4Controls[key].value = String(value); await modal._v4Submit({ preventDefault() {} }); await flush(); await flush(); }

(async () => {
  await context.__memomicsV4Ui.reload(); await flush();
  const add = elements.get('cluster-catalog-add-server');
  assert.ok(add.listeners.click?.length, 'Add server is bound with addEventListener');
  add.click();
  let modal = document.getElementById('v4-catalog-editor');
  assert.ok(modal, 'real button.click opens the create-server dialog');
  assert.equal(modal._v4Controls.login_compute, undefined, 'no server compute-role switch');
  await submit(modal, { name: 'New HPC', login_name: '入口', login_host: 'hpc.example.edu', login_port: 2200 });
  const created = lastCall((call) => call.url === '/api/cluster/catalog/servers' && call.method === 'POST');
  assert.deepEqual(created.body.login_node, { name: '入口', host: 'hpc.example.edu', port: 2200, is_login: true, is_compute: false });

  const list = elements.get('v5-server-list');
  const newServerSummary = byClass(list, 'v5-server-summary').find((item) => /New HPC/.test(textOf(item)));
  assert.equal(newServerSummary.getAttribute('aria-expanded'), 'true', 'new server is automatically expanded after creation');
  assert.ok(newServerSummary.parentNode.classList.contains('selected'), 'new server is visually focused after creation');
  let summary = byClass(list, 'v5-server-summary').find((item) => /Faculty cluster/.test(textOf(item)));
  assert.equal(summary.getAttribute('aria-expanded'), 'false', 'servers are collapsed initially');
  summary.click();
  summary = byClass(list, 'v5-server-summary').find((item) => /Faculty cluster/.test(textOf(item)));
  assert.equal(summary.getAttribute('aria-expanded'), 'true');
  let sections = byClass(summary.parentNode, 'v5-section');
  assert.equal(sections.length, 3, 'expanded server has node, user, and matched-connection sections');
  assert.match(textOf(sections[0]), /节点.*2/s, 'node section displays its count');
  assert.match(textOf(sections[1]), /用户.*2/s, 'user section displays its count');
  assert.match(textOf(sections[2]), /已匹配连接.*2/s, 'connection section displays its count');
  assert.match(textOf(sections[2]), /上次验证成功/, 'a historical last_connected_at is labelled as a past success, not proof that a newly edited password was tested');
  const sectionToggle = byClass(sections[0], 'v5-section-toggle')[0]; sectionToggle.click();
  sections = byClass(byClass(list, 'v5-server-summary').find((item) => /Faculty cluster/.test(textOf(item))).parentNode, 'v5-section');
  assert.equal(byClass(sections[0], 'v5-section-toggle')[0].getAttribute('aria-expanded'), 'true', 'section toggle.click expands and preserves its aria state');

  context.clusterCatalogCreateAccount('srv-a'); modal = document.getElementById('v4-catalog-editor');
  assert.ok(modal._v4Controls.password && modal._v4Controls.password_confirm);
  assert.equal(modal._v4Form.getAttribute('autocomplete'), 'off', 'account form asks browsers not to auto-fill or persist SSH credentials');
  assert.equal(modal._v4Controls.password.getAttribute('autocomplete'), 'off', 'password field asks browsers not to auto-fill or persist SSH credentials');
  assert.equal(modal._v4Controls.password_confirm.getAttribute('autocomplete'), 'off', 'password confirmation field asks browsers not to auto-fill or persist SSH credentials');
  await submit(modal, { user: 'newuser', password: 'fixture-password', password_confirm: 'fixture-password' });
  const createdAccount = lastCall((call) => /\/accounts$/.test(call.url) && call.method === 'POST');
  assert.equal(createdAccount.body.password, 'fixture-password');
  assert.equal(Object.hasOwn(createdAccount.body, 'password_confirm'), false);

  context.clusterCatalogEditAccount('acc-alice'); modal = document.getElementById('v4-catalog-editor');
  await submit(modal, { user: 'alice', note: '', password: '', password_confirm: '' });
  const blankEdit = lastCall((call) => /accounts\/acc-alice$/.test(call.url) && call.method === 'PATCH');
  assert.equal(Object.hasOwn(blankEdit.body, 'password'), false, 'blank edit preserves saved password');
  assert.equal(blankEdit.body.note, '', 'editing an account sends an explicit empty note so an existing note can be cleared');
  assert.deepEqual(Object.keys(blankEdit.body).sort(), ['name', 'note', 'user'], 'blank account edit preserves the complete UI PATCH shape without a password');
  context.clusterCatalogEditAccount('acc-alice'); modal = document.getElementById('v4-catalog-editor');
  const testsBeforePasswordEdit = state.calls.filter((call) => /\/connections\/[^/]+\/test$/.test(call.url)).length;
  await submit(modal, { user: 'alice', password: 'updated-fixture-password', password_confirm: 'updated-fixture-password' });
  const changedEdit = lastCall((call) => /accounts\/acc-alice$/.test(call.url) && call.method === 'PATCH');
  assert.equal(changedEdit.body.password, 'updated-fixture-password', 'nonblank edit sends the encrypted-credential update');
  assert.equal(changedEdit.body.note, '', 'password edits retain the explicit note-clear field from the account dialog');
  assert.deepEqual(Object.keys(changedEdit.body).sort(), ['name', 'note', 'password', 'user'], 'password edit sends the full account dialog contract');
  assert.equal(Object.hasOwn(changedEdit.body, 'password_confirm'), false, 'password confirmation never crosses the API boundary');
  assert.equal(modal._v4Controls.password.value, '', 'password input is cleared immediately after request construction');
  assert.equal(modal._v4Controls.password_confirm.value, '', 'confirmation input is cleared immediately after request construction');
  assert.match(elements.get('cluster-catalog-feedback').textContent, /密码已保存，请测试连接确认/, 'password save visibly asks the user to test the existing connection');
  assert.equal(state.calls.filter((call) => /\/connections\/[^/]+\/test$/.test(call.url)).length, testsBeforePasswordEdit, 'password save does not automatically trigger an SSH connection test');
  const patchCount = state.calls.filter((call) => /accounts\/acc-alice$/.test(call.url) && call.method === 'PATCH').length;
  context.clusterCatalogEditAccount('acc-alice'); modal = document.getElementById('v4-catalog-editor');
  await submit(modal, { user: 'alice', password: 'one', password_confirm: 'two' });
  assert.match(modal._v4Status.textContent, /不一致|match/i, 'password mismatch stays visible in the dialog');
  assert.equal(state.calls.filter((call) => /accounts\/acc-alice$/.test(call.url) && call.method === 'PATCH').length, patchCount, 'password mismatch does not call the API');
  modal._v4Close(true);

  context.clusterCatalogCreateMatch('srv-a', 'node-login', 'acc-alice'); modal = document.getElementById('v4-catalog-editor');
  assert.equal(modal._v4Controls.route_mode, undefined);
  assert.equal(modal._v4Controls.target_password, undefined);
  await submit(modal, { connection_name: 'Alice login' });
  const direct = lastCall((call) => /\/connections\/match$/.test(call.url));
  assert.deepEqual(Object.keys(direct.body).sort(), ['account_id', 'connection', 'node_id']);

  context.clusterCatalogCreateMatch('srv-a', 'node-compute', 'acc-bob'); modal = document.getElementById('v4-catalog-editor');
  assert.notEqual(modal._v4Controls.gateway_profile_id.parentNode.style.display, 'none', 'multiple valid gateway accounts reveal only the narrow gateway chooser');
  modal._v4Controls.gateway_profile_id.value = 'p-alice';
  await submit(modal, { connection_name: 'Bob software' });
  const jumped = lastCall((call) => /\/connections\/match$/.test(call.url));
  assert.deepEqual(Object.keys(jumped.body).sort(), ['account_id', 'connection', 'gateway_profile_id', 'node_id']);
  for (const key of ['password', 'target_password', 'gateway_password', 'key_path', 'route']) assert.equal(Object.hasOwn(jumped.body, key), false);

  const originalCreate = document.createElement;
  document.createElement = (tag) => { if (tag === 'form') throw new Error('controlled build failure'); return originalCreate(tag); };
  add.click(); document.createElement = originalCreate;
  assert.match(elements.get('cluster-catalog-feedback').textContent, /无法打开.*新增服务器|Unable to open.*Add server/);
  console.log('cluster_catalog_v4_ui.test.js: PASS');
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
