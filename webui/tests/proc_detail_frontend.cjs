#!/usr/bin/env node
// 「关键过程」折叠层 —— 阶段小结文字（2026-10-23 用户口径修订）前端行为测试
// 用户原话（要点）：不要「各种文件」，要看大模型在任务期间的思考阶段性总结
//   —— 比如触发了哪些 skill、有没有调用知识库、环境用的什么、用了什么方法、
//      方法有没有成功、是不是换了方法；全是文字，塞到折叠层里。
// 做法：把 webui/index.html 里的真实 _procBlockHtml 抠出来（index.html 没有构建步骤），
//       用桩 markdown/tf 跑纯字符串渲染。
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

const code = grab('_procBlockHtml');

const factory = new Function('env', [
  'var escapeHtml = env.escapeHtml, renderMarkdown = env.renderMarkdown;',
  'var tf = env.tf, t = env.t;',
  'function T(s) { return s; }   // 真实页面里 T() 走通用翻译层；测试里取身份函数（断言中文口径）',
  code,
  'return { block: _procBlockHtml };'
].join(NL));

const I18N_STUB = {
  proc_block: '📋 关键过程 · {0} 个阶段{1}（点击展开/收起）',
  proc_elapsed: '用时'
};
function _esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
const ENV = {
  escapeHtml: _esc,
  // 真实 renderMarkdown 会转义原始 HTML；桩里同样转义，转义断言才有意义
  renderMarkdown: function (s) { return '<md>' + _esc(s) + '</md>'; },
  tf: function (key) {
    const a = Array.prototype.slice.call(arguments, 1);
    return String(I18N_STUB[key] || key).replace(/\{(\d+)\}/g, function (m, i) { return a[+i] != null ? String(a[+i]) : m; });
  },
  t: function (k) { return I18N_STUB[k] || k; }
};
const e = factory(ENV);

console.log('== A. 结构：外框不变 + 阶段小结 + 编号 ==');
{
  const html = e.block(['先核实云上文件是否存在', '读入表达矩阵并做 QC'], { stats: { steps: 2, elapsed: '1:05' } });
  check('外层还是 details.proc-block（默认折叠的入口不变）', html.indexOf('<details class="proc-block"') === 0);
  check('摘要行 = 阶段数 · 用时', html.indexOf('📋 关键过程 · 2 个阶段 · 用时 1:05（点击展开/收起）') > 0, html.slice(0, 170));
  check('每阶段一段（proc-stage + 编号 + 正文）', (html.match(/proc-stage/g) || []).length === 2
    && (html.match(/proc-no/g) || []).length === 2 && html.indexOf('①') > 0 && html.indexOf('②') > 0);
  check('阶段正文走 markdown 渲染', html.indexOf('<md>先核实云上文件是否存在</md>') > 0
    && html.indexOf('<md>读入表达矩阵并做 QC</md>') > 0);
  check('顺序保持（第 1 段在前）', html.indexOf('先核实') < html.indexOf('读入表达矩阵'));
}

console.log('== B. 全是文字：没有文件/工具/参数结果清单 ==');
{
  const html = e.block(['读了 go-enrichment-visualization 的定稿参数，改用 pheatmap 稀疏矩阵方案', '出图 4 张 × 3 格式，已记录经验'],
    { stats: { steps: 2, elapsed: '' } });
  check('没有工具动作行（proc-act）', html.indexOf('proc-act') < 0);
  check('没有参数/结果折叠块（pre）', html.indexOf('<pre>') < 0);
  check('没有旧的步骤/动作容器残留', html.indexOf('proc-step') < 0 && html.indexOf('proc-acts') < 0);
  check('小结文字原样保留（技能/方法/结果都在文字里）',
    html.indexOf('go-enrichment-visualization') > 0 && html.indexOf('pheatmap') > 0 && html.indexOf('4 张 × 3 格式') > 0);
}

console.log('== C. 折叠行为（默认口径保持） ==');
{
  check('短过程（≤2 段且 ≤200 字）默认展开',
    e.block(['短', '也短'], { stats: { steps: 2, elapsed: '' } }).indexOf('<details class="proc-block" open>') === 0);
  check('3 段 → 默认折叠',
    e.block(['一', '二', '三'], { stats: { steps: 3, elapsed: '' } }).indexOf('<details class="proc-block">') === 0);
  check('长过程（>200 字）默认折叠',
    e.block(['x'.repeat(300), 'y'], { stats: { steps: 2, elapsed: '' } }).indexOf('<details class="proc-block">') === 0);
  check('没有用时时不带「用时」', e.block(['一', '二'], { stats: { steps: 2, elapsed: '' } })
    .indexOf('📋 关键过程 · 2 个阶段（点击展开/收起）') > 0);
}

console.log('== D. 边界：阶段很多 / 转义 ==');
{
  const segs = [];
  for (let i = 0; i < 25; i++) segs.push('阶段' + (i + 1));
  const html = e.block(segs, { stats: { steps: 25, elapsed: '' } });
  check('超过 20 段后编号降级为 (21)', html.indexOf('(21)') > 0 && html.indexOf('阶段21') > 0);
  check('25 段都有对应编号位', (html.match(/proc-no/g) || []).length === 25);
  const esc = e.block(['<script>alert(1)</script> 方法：Wilcoxon'], { stats: { steps: 1, elapsed: '' } });
  check('正文 HTML 转义', esc.indexOf('<script>') < 0 && esc.indexOf('&lt;script&gt;') > 0);
}

console.log('== J. 收尾折叠（complete 路径）：阶段小结必须进折叠层 ==');
{
  const foldCode = [grab('_procBlockHtml'), grab('_splitProcessConclusion')].join(NL);
  const foldFactory = new Function('env', [
    'var currentBubble = { innerHTML: "SENTINEL" }, currentAssistantEl = {};',
    'var fullSegs = [], fullText = "";',
    'var escapeHtml = env.escapeHtml, renderMarkdown = env.renderMarkdown, tf = env.tf, t = env.t;',
    'function T(s) { return s; }',
    'function _procElapsedShort() { return "0:12"; }',
    'function _citeWrapHtml(s) { return s; }',
    'function initMermaid() {}',
    foldCode,
    'return { run: _splitProcessConclusion, set: function (fs, ft) { fullSegs = fs; fullText = ft; },',
    '  html: function () { return currentBubble.innerHTML; }, reset: function () { currentBubble.innerHTML = "SENTINEL"; } };'
  ].join(NL))(ENV);
  const s1 = '① ' + '甲'.repeat(140), s2 = '② ' + '乙'.repeat(140), concl = '结论段。';
  // (a) 整稿 == 分段拼接（常规路径）
  foldFactory.set([s1, s2, concl], s1 + s2 + concl);
  foldFactory.run();
  const h1 = foldFactory.html();
  check('整稿一致 → 阶段小结进折叠块（默认折叠）',
    h1.indexOf('<details class="proc-block">') === 0 && h1.indexOf('① ') > 0 && h1.indexOf('<details class="proc-block" open>') < 0);
  check('结论留在折叠块之外', h1.indexOf(concl) > h1.indexOf('</details>'));
  // (b) complete 带更长的整稿（服务端补全的收尾不进分段）→ 以前会不折，现在照样折且不丢内容
  foldFactory.set([s1, s2, concl], s1 + s2 + concl + '\n\n补充收尾。');
  foldFactory.run();
  const h2 = foldFactory.html();
  check('整稿更长（含补充收尾）→ 仍然折叠', h2.indexOf('<details class="proc-block">') === 0);
  check('补充收尾并进结论（不丢内容）', h2.indexOf('补充收尾。') > h2.indexOf('</details>'));
  // (c) 整稿与分段完全对不上 → 不动（保内容完整）
  foldFactory.reset();
  foldFactory.set([s1, s2], '完全不同的整稿');
  foldFactory.run();
  check('两级都对不上 → 保持原样（不冒险丢内容）', foldFactory.html() === 'SENTINEL');
}

console.log(NL + '----');
console.log(pass + ' pass, ' + fail + ' fail');
process.exit(fail ? 1 : 0);