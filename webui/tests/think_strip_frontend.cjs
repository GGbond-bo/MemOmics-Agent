// webui/tests/think_strip_frontend.cjs
// 交互框「最新思考」条 —— 真行为测试（不是字符串断言）。
// 做法：把 index.html 里的前端函数抠出来，在桩 DOM 上跑，验证：
//   默认只显示最新一行 / 同一行不重复触发闪烁 / 长行显示尾部 / markdown 前缀剥离 /
//   正文数字不被误吃 / 收尾变淡 / 点开看得到全文（含换行）。
// 由 webui/tests/test_think_strip_ui.py 调用；输出必须含 "0 fail"。
const fs = require('fs');
const path = require('path');
const HTML = process.env.THINK_INDEX_HTML || path.join(__dirname, '..', 'index.html');
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
// 顶层 var 常量（函数体外）也要抠出来，否则抠出来的函数会 ReferenceError
function grabVar(name) {
  const m = new RegExp('var ' + name + '\\s*=\\s*([^;]+);').exec(src);
  if (!m) throw new Error('var not found: ' + name);
  return 'var ' + name + ' = ' + m[1] + ';\n';
}
const names = ['_thinkLineIn', '_thinkLatestLine', 'updateThinkStrip', 'openThinkModal', 'closeThinkModal'];
let code = '';
for (const n of ['_THINK_PREFIX_RE']) if (src.indexOf('var ' + n) >= 0) code += grabVar(n);
for (const n of names) code += grab(n) + '\n';

// ---- 桩 DOM：只实现这 4 个函数用到的 API ----
let flashCount = 0;
function mkEl(id) {
  const el = {
    id: id, textContent: '', scrollTop: 0, offsetWidth: 1,
    classes: new Set(), listeners: {},
  };
  el.classList = {
    add(c) { el.classes.add(c); if (c === 'ts-flash') flashCount++; },
    remove(c) { el.classes.delete(c); },
    contains(c) { return el.classes.has(c); },
    toggle(c, on) { if (on === undefined) { el.classes.has(c) ? el.classes.delete(c) : el.classes.add(c); } else if (on) el.classes.add(c); else el.classes.delete(c); },
  };
  return el;
}
const els = {
  'think-strip': mkEl('think-strip'),
  'think-strip-text': mkEl('think-strip-text'),
  'think-overlay': mkEl('think-overlay'),
  'think-body': mkEl('think-body'),
  'think-title': mkEl('think-title'),
};
const doc = {
  getElementById: id => els[id] || null,
  createElement: mkEl,
  addEventListener() {},
};

const fn = new Function('document', `
var reasoningText = '';
var agentRunning = false;
var _thinkStripShown = '';
` + code + `
return {
  updateThinkStrip: updateThinkStrip,
  _thinkLatestLine: _thinkLatestLine,
  openThinkModal: openThinkModal,
  closeThinkModal: closeThinkModal,
  setReasoning: function(v) { reasoningText = v; },
  setRunning: function(v) { agentRunning = v; },
  shown: function() { return _thinkStripShown; }
};`);
const api = fn(doc);

let pass = 0, fail = 0;
const check = (label, ok, extra) => {
  console.log((ok ? 'PASS ' : 'FAIL ') + label + (extra ? ' | ' + extra : ''));
  ok ? pass++ : fail++;
};
const strip = els['think-strip'], txt = els['think-strip-text'];
const ov = els['think-overlay'], body = els['think-body'], title = els['think-title'];

// 1) 没有任何思考 → 条子不显示
api.setReasoning('');
api.updateThinkStrip(true);
check('empty-hides-strip', !strip.classes.has('show'), [...strip.classes].join(','));

// 2) 多行思考 → 只显示最后一行（"默认只展示最新的思考"）
api.setReasoning('先看看数据\n读一下 rds\n准备跑差异表达');
api.updateThinkStrip(true);
check('shows-last-line-only', txt.textContent === '准备跑差异表达', JSON.stringify(txt.textContent));
check('strip-visible', strip.classes.has('show'));
check('strip-live-not-done', !strip.classes.has('done'));

// 3) 同一行再次推送 → 不重复触发闪烁动画（避免每个 token 都动 DOM）
const before = flashCount;
api.updateThinkStrip(true);
check('no-reflash-same-line', flashCount === before, 'flash=' + flashCount);

// 4) 换成新的一行 → 重放一次闪烁（"快速闪过"）
api.setReasoning('先看看数据\n读一下 rds\n调用 DESeq2 做差异分析');
api.updateThinkStrip(true);
check('reflash-on-new-line', flashCount === before + 1, 'flash=' + flashCount);

// 5) markdown 列表前缀 / 序号要被剥掉
check('strip-bullet-prefix', api._thinkLatestLine('- 第一步：读文件') === '第一步：读文件', api._thinkLatestLine('- 第一步：读文件'));
check('strip-number-prefix', api._thinkLatestLine('2. 第二步：跑 QC') === '第二步：跑 QC', api._thinkLatestLine('2. 第二步：跑 QC'));
check('strip-quote-prefix', api._thinkLatestLine('> 引用一句') === '引用一句', api._thinkLatestLine('> 引用一句'));

// 6) 正文数字不能被当序号吃掉（这是最容易写错的地方）
check('keep-leading-number', api._thinkLatestLine('2026 年计划先做 QC') === '2026 年计划先做 QC', api._thinkLatestLine('2026 年计划先做 QC'));

// 7) 空行结尾 → 回溯到最后一个非空行
check('skip-trailing-blank', api._thinkLatestLine('a\n\n   \n') === 'a', api._thinkLatestLine('a\n\n   \n'));

// 8) 长行 → 显示尾部（思考从左往右流出，最新在尾巴），带省略号
const long = 'x'.repeat(300) + 'TAIL';
check('long-line-shows-tail', api._thinkLatestLine(long) === long, 'line-ok');
api.setReasoning(long);
api.updateThinkStrip(true);
check('long-line-truncated-with-ellipsis', txt.textContent.length === 161 && txt.textContent[0] === '…' && txt.textContent.endsWith('TAIL'), 'len=' + txt.textContent.length);

// 9) 收尾（agent 停了）→ 变淡但仍显示、仍可点
api.setRunning(false);
api.updateThinkStrip();
check('done-dimmed-still-visible', strip.classes.has('done') && strip.classes.has('show'));

// 10) 点击 → 浮层显示全文（多行完整保留，不是只有末行）
const full = '第一段推理\n第二段推理\n第三段结论';
api.setReasoning(full);
api.updateThinkStrip(true);
api.openThinkModal();
check('modal-opens', ov.classes.has('show'));
check('modal-has-full-text', body.textContent === full, JSON.stringify(body.textContent));
check('modal-keeps-newlines', body.textContent.split('\n').length === 3);
check('modal-title-has-length', /\d+ 字/.test(title.textContent), title.textContent);
check('modal-from-top', body.scrollTop === 0);
check('modal-not-empty-class', !body.classes.has('think-empty'));

// 11) 关掉
api.closeThinkModal();
check('modal-closes', !ov.classes.has('show'));

// 12) 没有思考时点开 → 有话说，不是空白框
api.setReasoning('');
api.openThinkModal();
check('modal-empty-hint', body.textContent.indexOf('还没有思考') >= 0 && body.classes.has('think-empty'), body.textContent);

// 13) 新一轮开始时由调用方收起（reasoningText 被清空）
api.closeThinkModal();
api.setReasoning('');
api.updateThinkStrip(false);
check('new-turn-hides-strip', !strip.classes.has('show'));

// 14) 真实量级：一条长思考累到 20 万字时，仍然只显示最后一行，且不吃 CPU
const big = ('梳理思路第 N 步，检查一下输入文件是否存在\n').repeat(6000) + '最终结论：直接跑差异分析';
check('big-input-correct', api._thinkLatestLine(big) === '最终结论：直接跑差异分析', 'len=' + big.length);
const t0 = Date.now();
for (let i = 0; i < 2000; i++) api._thinkLatestLine(big);
const dt = Date.now() - t0;
check('big-input-fast', dt < 400, '2000 次 × ' + big.length + ' 字 = ' + dt + 'ms');
console.log('----');
console.log(pass + ' pass, ' + fail + ' fail');
process.exit(fail ? 1 : 0);
