/* Full-page shared-VM regression: execute every inline script, then click the real Add server button. */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map((match) => match[1]);
assert.equal(scripts.length, 5, 'the current delivered page has five inline scripts');

class ClassList {
  constructor() { this.values = new Set(); }
  add(...values) { values.filter(Boolean).forEach((value) => this.values.add(String(value))); }
  remove(...values) { values.forEach((value) => this.values.delete(String(value))); }
  contains(value) { return this.values.has(String(value)); }
  toggle(value, force) { const on = force === undefined ? !this.contains(value) : !!force; if (on) this.add(value); else this.remove(value); return on; }
}
let permissive = true;
const inert = new Map();
function inertElement(key) { if (!inert.has(key)) inert.set(key, new Element('div')); return inert.get(key); }
class Element {
  constructor(tag = 'div') {
    this.tagName = String(tag).toUpperCase(); this.children = []; this.options = []; this.parentNode = null;
    this.classList = new ClassList(); this.style = { setProperty() {}, removeProperty() {}, getPropertyValue: () => '' }; this.dataset = {}; this.attributes = {}; this.listeners = {};
    this.id = ''; this.value = ''; this.textContent = ''; this.innerHTML = ''; this.title = ''; this.name = ''; this.type = '';
    this.disabled = false; this.checked = false; this.scrollTop = 0; this.scrollHeight = 0; this.clientHeight = 360; this.clientWidth = 800;
  }
  get className() { return [...this.classList.values].join(' '); }
  set className(value) { this.classList.values = new Set(String(value || '').split(/\s+/).filter(Boolean)); }
  get firstChild() { return this.children[0] || null; }
  get firstElementChild() { return this.children[0] || null; }
  appendChild(child) { if (!child) return child; if (child.parentNode) child.parentNode.removeChild(child); child.parentNode = this; this.children.push(child); if (child.tagName === 'OPTION') this.options.push(child); return child; }
  insertBefore(child, before) { if (child.parentNode) child.parentNode.removeChild(child); child.parentNode = this; const index = this.children.indexOf(before); if (index < 0) this.children.push(child); else this.children.splice(index, 0, child); if (child.tagName === 'OPTION') this.options.push(child); return child; }
  removeChild(child) { this.children = this.children.filter((item) => item !== child); this.options = this.options.filter((item) => item !== child); if (child) child.parentNode = null; return child; }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  addEventListener(type, listener) { (this.listeners[type] || (this.listeners[type] = [])).push(listener); }
  removeEventListener(type, listener) { this.listeners[type] = (this.listeners[type] || []).filter((item) => item !== listener); }
  click() { const event = { type: 'click', target: this, currentTarget: this, preventDefault() {}, stopPropagation() {} }; if (typeof this.onclick === 'function') this.onclick(event); (this.listeners.click || []).forEach((listener) => listener.call(this, event)); }
  setAttribute(name, value) { this.attributes[name] = String(value); if (name === 'id') this.id = String(value); if (name === 'class') this.className = String(value); }
  getAttribute(name) { return Object.hasOwn(this.attributes, name) ? this.attributes[name] : null; }
  removeAttribute(name) { delete this.attributes[name]; }
  querySelector() { return permissive ? inertElement('query') : null; }
  querySelectorAll() { return []; }
  closest() { return null; }
  focus() {}
  blur() {}
  scrollIntoView() {}
  scrollTo() {}
  setSelectionRange() {}
  getBoundingClientRect() { return { top: 0, left: 0, bottom: 480, right: 800, width: 800, height: 480 }; }
  getContext() { return { clearRect() {}, fillRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fill() {}, arc() {}, measureText: () => ({ width: 0 }), createLinearGradient: () => ({ addColorStop() {} }) }; }
}
function descendants(root, output = []) { for (const child of root.children || []) { output.push(child); descendants(child, output); } return output; }

const body = new Element('body');
const known = new Map();
for (const [id, tag] of [
  ['cluster-console', 'div'], ['cluster-cfg', 'div'], ['cluster-catalog-add-server', 'button'], ['cluster-catalog-feedback', 'div'],
  ['cluster-catalog', 'div'], ['v5-server-list', 'div'], ['cluster-server-library-note', 'span'], ['cluster-chip', 'span'],
  ['cluster-node-chip', 'span'], ['cc-node', 'select'], ['cluster-out', 'div'], ['cluster-cmd', 'textarea'], ['cluster-mode', 'select'], ['cluster-run-btn', 'button'], ['cluster-hint', 'div']
]) { const element = new Element(tag); element.id = id; known.set(id, element); body.appendChild(element); }
const document = {
  body, documentElement: new Element('html'), readyState: 'loading', createElement: (tag) => new Element(tag),
  createTextNode: (text) => { const node = new Element('#text'); node.textContent = String(text); return node; },
  getElementById(id) { return known.get(id) || descendants(body).find((item) => item.id === id) || (permissive ? inertElement(`id:${id}`) : null); },
  querySelector() { return permissive ? inertElement('document-query') : null; }, querySelectorAll() { return []; },
  getElementsByTagName() { return []; }, getElementsByClassName() { return []; }, addEventListener() {}, removeEventListener() {}, execCommand: () => true
};
document.documentElement.lang = 'zh-CN';

const catalog = {
  schema_version: 2,
  servers: [{ id: 'srv-click', name: 'Click test server', node_count: 1, nodes: [{ id: 'node-login', name: 'login', host: 'login.example.edu', port: 22, is_login: true, is_compute: false }], accounts: [], connections: [] }],
  unassigned_profiles: [], orphan_links: []
};
function response(status, data) { return { ok: status >= 200 && status < 300, status, json: async () => JSON.parse(JSON.stringify(data)), text: async () => JSON.stringify(data) }; }
const context = {
  console: { log() {}, info() {}, warn() {}, error() {} }, document, navigator: { language: 'zh-CN', clipboard: { writeText: async () => {} } },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  location: { href: 'http://127.0.0.1:18999/', pathname: '/', reload() {} }, history: { pushState() {}, replaceState() {} },
  alert() {}, confirm: () => true, prompt: () => null, addEventListener() {}, removeEventListener() {},
  setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {}, requestAnimationFrame: () => 1, cancelAnimationFrame() {},
  MutationObserver: class { observe() {} disconnect() {} }, ResizeObserver: class { observe() {} disconnect() {} }, IntersectionObserver: class { observe() {} disconnect() {} },
  WebSocket: class { close() {} send() {} }, EventSource: class { close() {} }, matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  URL, URLSearchParams, AbortController, TextEncoder, TextDecoder, Buffer, currentSid: 'shared-vm-chat'
};
context.window = context; context.globalThis = context;
context.fetch = async (url, options = {}) => {
  if (url === '/api/cluster/catalog') return response(200, catalog);
  return response(200, { ok: true, sessions: [], projects: [], servers: [], nodes: [], config: {}, result: {} });
};

(async () => {
  vm.createContext(context);
  for (let index = 0; index < scripts.length; index += 1) {
    if (index === scripts.length - 1) permissive = false;
    try { vm.runInContext(scripts[index], context, { filename: `full-page.inline.${index + 1}.js` }); }
    catch (error) { throw new Error(`inline script ${index + 1} failed in the shared VM: ${error.stack || error.message}`); }
  }
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  const add = known.get('cluster-catalog-add-server');
  assert.ok(add.listeners.click?.length, 'the real page button has an addEventListener binding after all scripts load');
  add.click();
  const modal = document.getElementById('v4-catalog-editor');
  assert.ok(modal && modal._v4Controls && modal._v4Controls.login_host, 'real button.click opens the V5 server dialog after every inline script ran in order');
  console.log(`cluster_catalog_v5_fullpage_click.test.js: PASS (${scripts.length} inline scripts, shared VM, actual button.click)`);
})().catch((error) => { console.error(error.stack || error); process.exitCode = 1; });
