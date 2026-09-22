const fs = require('fs');
const path = require('path');
const HTML = process.env.LIT_INDEX_HTML || path.join(__dirname, '..', 'index.html');
const src = fs.readFileSync(HTML, 'utf8');

function grab(name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('not found: ' + name);
  const open = src.indexOf('{', start);
  let depth = 0;
  for (let j = open; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  throw new Error('unbalanced: ' + name);
}
const names = ['litBiSentenceHtml', 'litBiGoSent', 'litBiSentLabel', 'litBiShowRects', 'litBiClearHl', 'litBiStep'];
let code = '';
for (const n of names) code += grab(n) + '\n';

const made = [];
function mkEl(tag) {
  const el = {
    tagName: tag, children: [], attrs: {}, style: {}, textContent: '', removed: false,
    classes: new Set(),
    setAttribute(k, v) { el.attrs[k] = String(v); },
    getAttribute(k) { return (k in el.attrs) ? el.attrs[k] : null; },
    appendChild(c) { c._parent = el; el.children.push(c); return c; },
    remove() { el.removed = true; if (el._parent) el._parent.children = el._parent.children.filter(x => x !== el); },
    scrollIntoView() {},
    querySelectorAll(sel) { if (sel === '.lit-pdf-hl') return el.children.filter(c => c.classes.has('lit-pdf-hl')); return []; },
  };
  el.classList = { add: c => el.classes.add(c), remove: c => el.classes.delete(c), contains: c => el.classes.has(c) };
  Object.defineProperty(el, 'className', {
    get: () => [...el.classes].join(' '),
    set: v => { el.classes.clear(); String(v).split(/\s+/).filter(Boolean).forEach(c => el.classes.add(c)); },
  });
  made.push(el);
  return el;
}
const pages = {};
for (let p = 0; p < 40; p++) { const e = mkEl('div'); e.attrs.id = 'lit-pdf-page-' + p; pages[p] = e; }
const selected = {};
const doc = {
  createElement: mkEl,
  getElementById(id) {
    const m = /^lit-pdf-page-(\d+)$/.exec(id);
    if (m) return pages[m[1]] || null;
    if (id === 'lit-sent-info') return doc._info = doc._info || mkEl('span');
    return null;
  },
  querySelector(sel) {
    if (sel === '.lit-sent.cur') return Object.values(selected).find(e => e.classes.has('cur')) || null;
    const g = k => { const m = new RegExp(k + '="([^"]+)"').exec(sel); return m && m[1]; };
    const a = g('data-mi'), b = g('data-pj'), c = g('data-si');
    if (a == null || b == null || c == null) return null;
    return selected[a + ',' + b + ',' + c] || null;
  },
  querySelectorAll(sel) {
    if (sel === '.lit-sent.cur') return Object.values(selected).filter(e => e.classes.has('cur'));
    if (sel === '.lit-pdf-hl') return made.filter(e => e.classes.has('lit-pdf-hl') && !e.removed);
    return [];
  },
};
const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const fn = new Function('document', 'escapeHtml', 'setTimeout', 'clearTimeout',
  'var _litBi = null, _litBiHlTimer = null, _litBiSent = null;\n' + code +
  '\nreturn {litBiSentenceHtml, litBiGoSent, litBiStep, litBiShowRects, litBiClearHl,' +
  ' setBi: b => { _litBi = b; }, getSent: () => _litBiSent};');
const api = fn(doc, esc, () => 0, () => {});

const ZH = '主要位于真皮层。值得注意的是，一些CM08亚群。';
const paras = [
  { page: 3, rect: null, pre: [], rects: [],
    zh: ZH, units: [{ p: 3, r: [0.1, 0.2, 0.4, 0.23] }, { p: 3, r: [0.1, 0.23, 0.9, 0.26] }],
    zs: [{ o: [0, 8], u: 0 }, { o: [8, 24], u: 1 }] },
  { page: 4, rect: null, pre: [], rects: [],
    zh: '下一段第一句。', units: [{ p: 4, r: [0.5, 0.6, 0.9, 0.63] }],
    zs: [{ o: [0, 7], u: 0 }] },
];
api.setBi({ modules: [{ paras }], pages: 40 });
let pass = 0, fail = 0;
const check = (label, ok, extra) => { console.log((ok ? 'PASS ' : 'FAIL ') + label + (extra ? ' | ' + extra : '')); ok ? pass++ : fail++; };

const html = api.litBiSentenceHtml(paras[0], 0, 0);
const segs = [...html.matchAll(/<span class="lit-sent[^"]*"[^>]*>([\s\S]*?)<\/span>/g)].map(m => m[1]);
check('slice-restores-translation', segs.join('') === ZH, JSON.stringify(segs.join('')));
check('one-clickable-per-sentence', segs.length === 2, 'n=' + segs.length);

const el1 = mkEl('span'); el1.classes.add('lit-sent'); el1.attrs['data-mi'] = '0'; el1.attrs['data-pj'] = '0'; el1.attrs['data-si'] = '1';
const el0 = mkEl('span'); el0.classes.add('lit-sent'); el0.attrs['data-mi'] = '0'; el0.attrs['data-pj'] = '0'; el0.attrs['data-si'] = '0';
selected['0,0,0'] = el0; selected['0,0,1'] = el1;
api.litBiGoSent(0, 0, 1);
const hls = pages[3].children.filter(c => c.classes.has('lit-pdf-hl'));
check('click-2nd-draws-1-box', hls.length === 1, 'n=' + hls.length);
check('box-pos-equals-units1', !!hls[0] && hls[0].style.top === '23%' && hls[0].style.width === '80%', hls[0] ? JSON.stringify(hls[0].style) : 'none');
check('2nd-selected', el1.classes.has('cur'));
check('1st-not-selected', !el0.classes.has('cur'));

api.litBiGoSent(0, 0, 0);
const hls2 = pages[3].children.filter(c => c.classes.has('lit-pdf-hl'));
check('switch-keeps-one-box', hls2.length === 1, 'n=' + hls2.length);
check('box-pos-equals-units0', !!hls2[0] && hls2[0].style.top === '20%');
check('selection-moved', el0.classes.has('cur') && !el1.classes.has('cur'));

api.litBiGoSent(0, 0, 0);
const leftover = pages[3].children.filter(c => c.classes.has('lit-pdf-hl'));
check('reclick-clears-box', leftover.length === 0);
check('reclick-clears-selection', !el0.classes.has('cur') && !el1.classes.has('cur'));

api.litBiGoSent(0, 0, 1);
api.litBiStep(1);
const st = api.getSent();
check('next-crosses-paragraph', !!st && st[0] === 0 && st[1] === 1 && st[2] === 0, JSON.stringify(st));
check('cross-box-on-page4', pages[4].children.filter(c => c.classes.has('lit-pdf-hl')).length === 1);
api.litBiStep(-1);
const st2 = api.getSent();
check('prev-returns', !!st2 && st2[1] === 0 && st2[2] === 1, JSON.stringify(st2));

paras[0].zs[0].w = 1;
api.litBiGoSent(0, 0, 0);
check('weak-sentence-dashed', pages[3].children.filter(c => c.classes.has('lit-pdf-hl')).some(h => h.classes.has('w')));

const oldP = { page: 5, zh: '老缓存段落。', rect: [0.2, 0.3, 0.8, 0.35], units: [], pre: [], rects: [] };
const oldHtml = api.litBiSentenceHtml(oldP, 0, 0);
check('legacy-payload-still-clickable', oldHtml.indexOf('lit-sent') >= 0 && oldHtml.indexOf('老缓存段落。') >= 0);

console.log('\nTOTAL: ' + pass + ' pass / ' + fail + ' fail');
process.exit(fail ? 1 : 0);
