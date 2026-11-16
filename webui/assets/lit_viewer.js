/* MemOmics 内置 PDF 阅读器 + 批注 + 滑动翻译（文献库 2.0，2026-11-12）
 *
 * 依赖：/assets/vendor/pdfjs/pdf.min.js（pdf.js 3.11.174，Apache-2.0）
 * 数据：GET/POST /api/lit/marks（papers/.annotations/<stem>.json）
 *       POST /api/lit/translate（片段翻译，进程内缓存）
 * 渲染：本机 Edge 的 pdf.js canvas 会挂起 → 正文用服务端 PyMuPDF 出图
 *       （/api/papers/page），pdf.js 只负责文本层/页码/文本块。
 * 交互：连续上下滚动（IntersectionObserver 懒加载）+ 划词批注 + 整页译文面板。
 */
(function () {
  'use strict';

  var PALETTE = { yellow: '#fcd34d', green: '#86efac', blue: '#7dd3fc', pink: '#f9a8d4', purple: '#d8b4fe' };
  var COLOR_ORDER = ['yellow', 'green', 'blue', 'pink', 'purple'];

  var S = {
    host: null, path: '', title: '',
    doc: null, total: 0, scale: 1, fit: 'width',
    marks: [], revision: 0, stale: false,
    shells: {}, loaded: {}, textReady: {}, blocks: {}, blockMeta: {}, trans: {}, transOn: false, transOff: {}, transing: {}, genTrans: 0,
    current: 1, io: null, sidebar: true, menu: null, pop: null,
    cleanup: [], gen: 0, baseW: 612, baseH: 792
  };

  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }
  function toast(msg, bad) {
    var t = el('div', 'lv-toast', msg);
    t.style.background = bad ? '#b91c1c' : '#166534';
    document.body.appendChild(t);
    setTimeout(function () { t.style.opacity = '0'; }, 1800);
    setTimeout(function () { try { t.remove(); } catch (e) {} }, 2400);
  }

  function ensureStyle() {
    if (document.getElementById('lit-viewer-style')) return;
    var css = [
      '.lv-root{display:flex;flex-direction:column;height:100%;min-height:420px;background:var(--panel,#fff);color:var(--text,#111);}',
      '.lv-bar{display:flex;align-items:center;gap:6px;padding:5px 8px;border-bottom:1px solid var(--border,#ddd);flex-wrap:wrap;font-size:12px;}',
      '.lv-bar button{border:1px solid var(--border,#ddd);background:var(--panel,#fff);color:var(--text,#111);border-radius:5px;padding:2px 8px;cursor:pointer;font-size:12px;line-height:18px;}',
      '.lv-bar button:hover{border-color:var(--primary,#2d8659);color:var(--primary,#2d8659);}',
      '.lv-bar button.on{background:var(--primary,#2d8659);color:#fff;border-color:transparent;}',
      '.lv-bar .lv-pg{width:46px;text-align:center;border:1px solid var(--border,#ddd);border-radius:4px;padding:1px 2px;font-size:12px;background:var(--panel,#fff);color:var(--text,#111);}',
      '.lv-bar .lv-sp{flex:1;}',
      '.lv-main{display:flex;flex:1;min-height:0;}',
      '.lv-stage{flex:1;overflow:auto;background:#eceff3;padding:10px 0;text-align:center;scroll-behavior:auto;}',
      '.lv-pages{display:flex;flex-direction:column;align-items:center;gap:14px;padding-bottom:24px;}',
      '.lv-shell{position:relative;margin:0 auto;}',
      '.lv-page{position:relative;background:#fff;box-shadow:0 1px 6px rgba(0,0,0,.18);}',
      '.lv-page img.lv-img{display:block;user-select:none;-webkit-user-drag:none;}',
      '.lv-ph{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#9aa3ad;font-size:12px;background:#f7f8fa;}',
      '.lv-hl{position:absolute;inset:0;pointer-events:none;}',
      '.lv-hl .lv-mark{position:absolute;pointer-events:auto;cursor:pointer;border-radius:2px;mix-blend-mode:multiply;opacity:.42;}',
      '.lv-hl .lv-mark.flash{outline:2px solid #ef4444;outline-offset:1px;}',
      '.lv-txt{position:absolute;inset:0;overflow:hidden;line-height:1;opacity:1;}',
      '.lv-txt>span,.lv-txt>br{color:transparent;position:absolute;white-space:pre;cursor:text;transform-origin:0% 0%;}',
      '.lv-txt>span.lv-no-select{user-select:none;pointer-events:none;}',
      '.lv-txt ::selection{background:rgba(59,130,246,.38);color:transparent;}',
      '.lv-body{display:flex;gap:12px;align-items:flex-start;justify-content:center;}',
      '.lv-col{position:relative;width:min(430px,40vw);min-height:120px;background:#fbfaf6;border:1px solid #e6e0cf;border-radius:8px;padding:26px 8px 8px;font-size:12px;line-height:1.55;color:#222;overflow:auto;box-sizing:border-box;}',
      '.lv-col.hide{display:none;}',
      '.lv-col .col-head{position:sticky;top:0;left:0;right:0;margin:-26px -8px 6px;padding:5px 8px;background:#f5f1e4;border-bottom:1px solid #e6e0cf;font-size:12px;color:#8a6d3b;display:flex;align-items:center;gap:8px;z-index:2;}',
      '.lv-col .col-head .sp{flex:1;}',
      '.lv-col .col-head button{border:0;background:transparent;color:#8a6d3b;cursor:pointer;font-size:12px;}',
      '.lv-col .blk{position:absolute;left:8px;right:8px;}',
      '.lv-col .blk .idx{color:#b0a58a;font-size:10px;margin-right:4px;}',
      '.lv-col .blk .txt{color:#222;}',
      '.lv-col .spin{color:#999;}',
      '.lv-tr{margin:8px auto 0;max-width:100%;text-align:left;background:#fbfaf6;border:1px solid #e6e0cf;border-radius:8px;padding:10px 14px;font-size:13px;line-height:1.7;color:#222;}',
      '.lv-tr h5{margin:0 0 6px;font-size:12px;color:#8a6d3b;font-weight:600;display:flex;gap:8px;align-items:center;}',
      '.lv-tr h5 .ptr{font-weight:400;color:#aaa;}',
      '.lv-tr p{margin:0 0 7px;}',
      '.lv-tr p .idx{color:#b0a58a;font-size:11px;margin-right:6px;}',
      '.lv-tr .spin{color:#999;font-size:12px;}',
      '.lv-side{width:290px;border-left:1px solid var(--border,#ddd);display:flex;flex-direction:column;min-height:0;}',
      '.lv-side.hide{display:none;}',
      '.lv-side h4{margin:0;padding:7px 10px;font-size:12px;border-bottom:1px solid var(--border,#ddd);}',
      '.lv-list{flex:1;overflow:auto;padding:4px 0;}',
      '.lv-item{padding:6px 10px;border-bottom:1px dashed var(--border,#eee);cursor:pointer;font-size:12px;line-height:1.45;}',
      '.lv-item:hover{background:rgba(45,134,89,.07);}',
      '.lv-item .q{color:var(--text,#111);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}',
      '.lv-item .c{color:#b45309;margin-top:2px;}',
      '.lv-item .m{color:var(--text-light,#888);font-size:11px;display:flex;gap:6px;align-items:center;}',
      '.lv-dot{width:9px;height:9px;border-radius:50%;display:inline-block;}',
      '.lv-menu{position:fixed;z-index:9999;background:var(--panel,#fff);border:1px solid var(--border,#ddd);border-radius:8px;box-shadow:0 6px 22px rgba(0,0,0,.22);padding:5px;display:flex;gap:4px;align-items:center;}',
      '.lv-menu button{border:0;background:transparent;cursor:pointer;font-size:12px;padding:3px 6px;border-radius:5px;color:var(--text,#111);}',
      '.lv-menu button:hover{background:rgba(0,0,0,.06);}',
      '.lv-menu .sw{width:16px;height:16px;border-radius:4px;border:1px solid rgba(0,0,0,.15);cursor:pointer;}',
      '.lv-pop{position:fixed;z-index:10000;width:300px;max-height:360px;overflow:auto;background:var(--panel,#fff);border:1px solid var(--border,#ddd);border-radius:8px;box-shadow:0 8px 26px rgba(0,0,0,.25);padding:8px;font-size:12px;}',
      '.lv-pop .orig{color:#777;max-height:60px;overflow:auto;margin-bottom:5px;}',
      '.lv-pop textarea{width:100%;height:66px;box-sizing:border-box;border:1px solid var(--border,#ddd);border-radius:5px;padding:5px;font:12px/1.4 inherit;resize:vertical;background:var(--panel,#fff);color:var(--text,#111);}',
      '.lv-pop .tr{background:#fbfaf6;border:1px solid #e6e0cf;border-radius:6px;padding:6px 8px;line-height:1.7;margin:4px 0;}',
      '.lv-pop .row{display:flex;gap:6px;align-items:center;margin-top:6px;}',
      '.lv-pop .row .sp{flex:1;}',
      '.lv-pop-head{display:flex;align-items:center;gap:8px;margin:-2px 0 6px;font-weight:600;color:var(--text,#111);}',
      '.lv-pop-head .sp{flex:1;}',
      '.lv-pop .lv-pop-close{border:0;background:transparent;color:#777;font-size:15px;line-height:18px;padding:0 3px;cursor:pointer;}',
      '.lv-pop .lv-pop-close:hover{color:#b91c1c;background:rgba(0,0,0,.06);}',
      '.lv-pop button{border:1px solid var(--border,#ddd);background:var(--panel,#fff);border-radius:5px;padding:3px 8px;cursor:pointer;font-size:12px;}',
      '.lv-pop button.pri{background:var(--primary,#2d8659);color:#fff;border-color:transparent;}',
      '.lv-toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:10001;background:#166534;color:#fff;padding:7px 14px;border-radius:6px;font-size:12px;opacity:.96;transition:opacity .4s;}',
      '.lv-empty{padding:26px;color:#888;font-size:13px;text-align:center;}'
    ].join('\n');
    var st = el('style'); st.id = 'lit-viewer-style'; st.textContent = css;
    document.head.appendChild(st);
  }

  function loadLib(cb) {
    if (window.pdfjsLib) return cb(null);
    var s = document.createElement('script');
    s.src = '/assets/vendor/pdfjs/pdf.min.js';
    s.onload = function () {
      if (window.pdfjsLib) {
        try { window.pdfjsLib.GlobalWorkerOptions.workerSrc = '/assets/vendor/pdfjs/pdf.worker.min.js'; } catch (e) {}
        cb(null);
      } else cb(new Error('pdf.js 未就绪'));
    };
    s.onerror = function () { cb(new Error('pdf.js 加载失败')); };
    document.head.appendChild(s);
  }

  function apiMarks(path) {
    return fetch('/api/lit/marks?path=' + encodeURIComponent(path), { cache: 'no-store' }).then(function (r) { return r.json(); });
  }
  function apiWrite(payload) {
    return fetch('/api/lit/marks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      .then(function (r) { return r.json().then(function (d) { d.__status = r.status; return d; }); });
  }
  function apiTranslate(texts) {
    return fetch('/api/lit/translate', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texts: texts, to: 'zh' }) })
      .then(function (r) { return r.json(); });
  }

  function buildShell() {
    var host = S.host;
    host.innerHTML = '';
    var root = el('div', 'lv-root');
    var bar = el('div', 'lv-bar');
    var prev = el('button', '', '◀');
    var next = el('button', '', '▶');
    var pg = el('input', 'lv-pg'); pg.type = 'text'; pg.value = '1';
    var total = el('span', '', '/ 0');
    var zoomOut = el('button', '', '−');
    var zoomVal = el('span', '', '100%');
    var zoomIn = el('button', '', '+');
    var fit = el('button', '', '适宽');
    var tr = el('button', '', '🌐 译文');
    tr.title = '滑动翻译：开启后每页下方显示中文译文（按段落对齐）';
    var side = el('button', '', '📝 批注');
    var sys = el('a', '', '系统阅读器');
    sys.href = '/api/papers?path=' + encodeURIComponent(S.path);
    sys.target = '_blank';
    sys.style.cssText = 'font-size:12px;color:var(--primary,#2d8659);text-decoration:none;padding:2px 6px;border:1px solid var(--border,#ddd);border-radius:5px;';
    var sp = el('span', 'lv-sp');

    [prev, next, pg, total, zoomOut, zoomVal, zoomIn, fit, sp, tr, side, sys].forEach(function (x) { bar.appendChild(x); });

    var main = el('div', 'lv-main');
    var stage = el('div', 'lv-stage');
    var pagesBox = el('div', 'lv-pages');
    stage.appendChild(pagesBox);
    var sidePanel = el('div', 'lv-side');
    var sideHead = el('h4', '', '批注');
    var sideList = el('div', 'lv-list');
    sidePanel.appendChild(sideHead); sidePanel.appendChild(sideList);
    main.appendChild(stage); main.appendChild(sidePanel);
    root.appendChild(bar); root.appendChild(main);
    host.appendChild(root);

    S.ui = { root: root, bar: bar, stage: stage, pages: pagesBox, side: sidePanel, sideHead: sideHead,
             sideList: sideList, pg: pg, total: total, zoomVal: zoomVal, prev: prev, next: next, tr: tr };

    prev.onclick = function () { goto(S.current - 1); };
    next.onclick = function () { goto(S.current + 1); };
    pg.onchange = function () { var n = parseInt(pg.value, 10); if (n) goto(n); };
    zoomOut.onclick = function () { setScale(S.scale / 1.2); };
    zoomIn.onclick = function () { setScale(S.scale * 1.2); };
    fit.onclick = function () { S.fit = 'width'; fitWidth(); };
    tr.onclick = function () { setTrans(!S.transOn); };
    side.onclick = function () { S.sidebar = !S.sidebar; sidePanel.classList.toggle('hide', !S.sidebar); };
    return root;
  }

  function makeShell(n) {
    var sh = el('div', 'lv-shell');
    sh.setAttribute('data-page', String(n));
    var body = el('div', 'lv-body');
    var page = el('div', 'lv-page');
    var img = el('img', 'lv-img'); img.alt = 'page ' + n; img.draggable = false;
    var ph = el('div', 'lv-ph', '第 ' + n + ' 页加载中…');
    var hl = el('div', 'lv-hl');
    var txt = el('div', 'lv-txt');
    page.appendChild(img); page.appendChild(ph); page.appendChild(hl); page.appendChild(txt);
    var col = el('div', 'lv-col hide');
    var colHead = el('div', 'col-head');
    colHead.innerHTML = '<span>🌐 第 ' + n + ' 页译文</span><span class="sp"></span><button type="button" title="关闭本页译文">✕</button>';
    var blocks = el('div', 'col-blocks');
    col.appendChild(colHead); col.appendChild(blocks);
    body.appendChild(page); body.appendChild(col);
    sh.appendChild(body);
    S.ui.pages.appendChild(sh);
    S.shells[n] = { shell: sh, body: body, page: page, img: img, ph: ph, hl: hl, txt: txt,
                    col: col, colHead: colHead, blocks: blocks };
    colHead.querySelector('button').onclick = function () {
      col.classList.add('hide');
      S.transOff[n] = true;
    };
    return S.shells[n];
  }

  function dims(n, base) {
    var w = Math.max(120, Math.round(base.width * S.scale));
    var h = Math.max(160, Math.round(base.height * S.scale));
    var sh = S.shells[n]; if (!sh) return;
    sh.page.style.width = w + 'px'; sh.page.style.height = h + 'px';
    sh.shell.style.width = 'auto';
    if (sh.txt) { sh.txt.style.width = w + 'px'; sh.txt.style.height = h + 'px'; }
    if (sh.img && sh.img.style.width) { sh.img.style.width = w + 'px'; sh.img.style.height = h + 'px'; }
    return { w: w, h: h };
  }

  function dpiForScale() {
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    return Math.max(80, Math.min(300, Math.round(72 * S.scale * dpr)));
  }

  function ensureLoaded(n) {
    var sh = S.shells[n];
    if (!sh || sh.loading || sh.loaded) return Promise.resolve(sh && sh.loaded);
    sh.loading = true;
    return S.doc.getPage(n).then(function (page) {
      var base = page.getViewport({ scale: 1 });
      if (n === 1) { S.baseW = base.width; S.baseH = base.height; }
      var d = dims(n, base);
      sh.base = base;
      var url = '/api/papers/page?path=' + encodeURIComponent(S.path) + '&page=' + (n - 1) +
                '&dpi=' + dpiForScale() + '&v=' + dpiForScale();
      return new Promise(function (resolve) {
        sh.img.onload = function () { resolve(true); };
        sh.img.onerror = function () { resolve(false); };
        sh.img.style.width = d.w + 'px';
        sh.img.style.height = d.h + 'px';
        sh.img.src = url;
      }).then(function (ok) {
        sh.loading = false;
        if (!ok) { sh.ph.textContent = '第 ' + n + ' 页图片加载失败'; return false; }
        sh.loaded = true;
        sh.ph.style.display = 'none';
        renderHighlights(n);
        return ensureText(n).then(function () {
          if (S.transOn && Math.abs(n - S.current) <= 2) ensureTrans(n);
          return true;
        });
      });
    }).catch(function (e) {
      sh.loading = false;
      sh.ph.textContent = '第 ' + n + ' 页加载失败';
      try { console.warn('[LitViewer] page load failed', n, e && e.message); } catch (e2) {}
      return false;
    });
  }

  function _markNonTextSpans(container) {
    // <br> 只是排版分隔符，却会在原生 Range 中产生零宽竖条；直接移除。
    Array.prototype.forEach.call(container.querySelectorAll('br'), function (br) { br.remove(); });
    // 页边竖排/旋转文字不参与原生选择（否则会跨正文行产生竖向选区）。
    Array.prototype.forEach.call(container.querySelectorAll('span'), function (sp) {
      var r = sp.getBoundingClientRect();
      var rotated = false;
      try {
        var tr = getComputedStyle(sp).transform;
        if (tr && tr !== 'none') {
          var m = tr.match(/matrix\(([^)]+)\)/);
          if (m) {
            var v = m[1].split(',').map(Number);
            rotated = v.length >= 4 && (Math.abs(v[1]) > 0.2 || Math.abs(v[2]) > 0.2);
          }
        }
      } catch (e) {}
      if (rotated || (r.height > 42 && r.height > r.width * 1.35)) sp.classList.add('lv-no-select');
    });
  }

  function renderText(page, vp, container) {
    container.innerHTML = '';
    container.style.width = Math.floor(vp.width) + 'px';
    container.style.height = Math.floor(vp.height) + 'px';
    if (!window.pdfjsLib || !pdfjsLib.renderTextLayer) return Promise.resolve();
    function run(opts) {
      try { var t = pdfjsLib.renderTextLayer(opts); return (t && t.promise) ? t.promise : Promise.resolve(); }
      catch (e) { return Promise.reject(e); }
    }
    return page.getTextContent().then(function (tc) {
      return run({ textContentSource: tc, container: container, viewport: vp, textDivs: [] })
        .catch(function () {
          return run({ textContent: tc, container: container, viewport: vp, textDivs: [] })
            .catch(function () {});
        })
        .then(function () { _markNonTextSpans(container); });
    }).catch(function () { return Promise.resolve(); });
  }

  function ensureText(n) {
    var sh = S.shells[n];
    if (!sh || !sh.loaded || sh.textReady || !sh.base) return Promise.resolve();
    return S.doc.getPage(n).then(function (page) {
      var cssW = sh.page.clientWidth || (sh.base.width * S.scale);
      var vp = page.getViewport({ scale: cssW / sh.base.width });
      return renderText(page, vp, sh.txt).then(function () { sh.textReady = true; sh.lines = null; });
    }).catch(function () {});
  }

  function blocksOf(n) {
    if (S.blocks[n]) return Promise.resolve(S.blockMeta[n] || []);
    return S.doc.getPage(n).then(function (page) {
      return page.getTextContent().then(function (tc) {
        var baseH = (S.shells[n] && S.shells[n].base) ? S.shells[n].base.height : S.baseH;
        var rows = [];
        (tc.items || []).forEach(function (it) {
          var str = String(it.str || '').trim();
          if (!str) return;
          var y = Math.round((it.transform ? it.transform[5] : 0) / 3);
          var x = it.transform ? it.transform[4] : 0;
          rows.push({ y: y, x: x, s: str, yy: it.transform ? it.transform[5] : 0 });
        });
        var groups = {};
        rows.forEach(function (r) { (groups[r.y] = groups[r.y] || []).push(r); });
        var out = [];
        Object.keys(groups).map(Number).sort(function (a, b) { return b - a; }).forEach(function (y) {
          var items = groups[y].sort(function (a, b) { return a.x - b.x; });
          var text = items.map(function (i) { return i.s; }).join(' ').replace(/\s+/g, ' ').trim();
          // 去掉行号前缀（手稿常见 "14 Dev Cell..."）与太短的页眉/页码/作者行
          text = text.replace(/^\d{1,3}\s+/, '').trim();
          if (text.length >= 25 && /[A-Za-z]{3}/.test(text)) {
            var top = 1 - (items[0].yy / baseH);
            out.push({ text: text, top: Math.max(0, Math.min(1, top)) });
          }
        });
        out = out.slice(0, 24);
        S.blockMeta[n] = out;
        S.blocks[n] = out.map(function (b) { return b.text; });
        return out;
      });
    }).catch(function () { return []; });
  }

  function ensureTrans(n) {
    var sh = S.shells[n];
    if (!S.transOn || !sh || !sh.loaded || S.transOff[n]) return;
    if (S.trans[n] || S.transing[n]) { renderTrans(n); return; }
    var gen = S.genTrans;
    S.transing[n] = true;
    sh.col.classList.remove('hide');
    sh.col.style.height = (sh.page.clientHeight || 600) + 'px';
    sh.blocks.innerHTML = '<div class="spin" style="padding:6px">翻译中…</div>';
    blocksOf(n).then(function (blocks) {
      if (gen !== S.genTrans) { S.transing[n] = false; return; }
      if (!blocks.length) {
        S.transing[n] = false;
        sh.blocks.innerHTML = '<div class="spin" style="padding:6px">本页没有可提取的文字（可能是扫描件）</div>';
        return;
      }
      return apiTranslate(blocks.map(function (b) { return b.text; })).then(function (d) {
        S.transing[n] = false;
        if (gen !== S.genTrans) return;
        if (!d || !d.ok) { sh.blocks.innerHTML = '<div class="spin" style="padding:6px">翻译失败：' + esc((d && d.error) || '') + '</div>'; return; }
        S.trans[n] = d.translations || [];
        renderTrans(n);
      });
    }).catch(function (e) {
      S.transing[n] = false;
      if (gen === S.genTrans) sh.blocks.innerHTML = '<div class="spin" style="padding:6px">翻译失败：' + esc(e && e.message || e) + '</div>';
    });
  }

  function renderTrans(n) {
    var sh = S.shells[n]; if (!sh) return;
    var arr = S.trans[n] || [];
    var meta = S.blockMeta[n] || [];
    if (S.transOff[n]) { sh.col.classList.add('hide'); return; }
    sh.col.classList.remove('hide');
    sh.col.style.height = (sh.page.clientHeight || 600) + 'px';
    sh.blocks.innerHTML = '';
    var H = sh.page.clientHeight || 600;
    var prevBottom = 4;
    var shown = 0;
    arr.forEach(function (t, i) {
      if (!String(t || '').trim()) return;   // 空译文（模型漏段）不占位
      var top = ((meta[i] && meta[i].top) || 0) * H + 22;
      if (top < prevBottom + 2) top = prevBottom + 2;
      var d = el('div', 'blk');
      d.innerHTML = '<span class="idx">¶' + (i + 1) + '</span><span class="txt">' + esc(t) + '</span>';
      d.style.top = Math.round(top) + 'px';
      sh.blocks.appendChild(d);
      prevBottom = top + (d.offsetHeight || 18);
      shown++;
    });
    if (!shown) sh.blocks.innerHTML = '<div class="spin" style="padding:6px">本页译文为空（可点 ✕ 关闭，或稍后重试）</div>';
  }

  function hideAllTrans() {
    Object.keys(S.shells).forEach(function (n) {
      var sh = S.shells[n];
      if (sh && sh.col) sh.col.classList.add('hide');
    });
  }

  function showTransPanels() {
    Object.keys(S.shells).forEach(function (n) {
      var sh = S.shells[n];
      if (sh && sh.col && !S.transOff[n] && S.trans[n]) sh.col.classList.remove('hide');
    });
  }

  function setTrans(on) {
    S.transOn = !!on;
    S.genTrans++;
    if (S.ui && S.ui.tr) {
      S.ui.tr.classList.toggle('on', S.transOn);
      S.ui.tr.textContent = S.transOn ? '🌐 译文 ✓' : '🌐 译文';
      S.ui.tr.title = S.transOn ? '点击关闭译文（Esc 也可）' : '滑动翻译：开启后原文右侧按段落位置显示译文';
    }
    if (!S.transOn) {
      S.transing = {};
      hideAllTrans();
      toast('已关闭译文');
      if (S.doc) fitWidth();
      return;
    }
    S.transOff = {};
    if (S.doc) {
      fitWidth().then(function () {
        [S.current - 1, S.current, S.current + 1].forEach(function (n) {
          if (n >= 1 && n <= S.total) ensureTrans(n);
        });
      });
    }
    toast('滑动翻译：已开启（右侧按段落对齐）');
  }

  function renderHighlights(n) {
    var sh = S.shells[n]; if (!sh) return;
    sh.hl.innerHTML = '';
    S.marks.filter(function (m) { return Number(m.page) === Number(n); }).forEach(function (m) {
      var color = PALETTE[m.color] || PALETTE.yellow;
      (m.rects || []).forEach(function (r) {
        var d = el('div', 'lv-mark');
        d.style.left = (r.x * 100) + '%';
        d.style.top = (r.y * 100) + '%';
        d.style.width = (r.w * 100) + '%';
        d.style.height = (r.h * 100) + '%';
        d.style.background = color;
        d.title = (m.comment || m.quote || '').slice(0, 300);
        d.onclick = function (ev) { ev.stopPropagation(); openMarkPop(m, ev); };
        sh.hl.appendChild(d);
      });
    });
  }

  function renderSidebar() {
    if (!S.ui) return;
    var head = S.ui.sideHead, list = S.ui.sideList;
    head.textContent = '批注（' + S.marks.length + '）' + (S.stale ? ' · 原文已变更' : '');
    list.innerHTML = '';
    if (!S.marks.length) {
      list.appendChild(el('div', 'lv-empty', '还没有批注。选中正文文字即可高亮或写批注。'));
      return;
    }
    S.marks.slice().sort(function (a, b) { return (a.page - b.page) || String(a.created).localeCompare(String(b.created)); })
      .forEach(function (m) {
        var it = el('div', 'lv-item');
        it.appendChild(el('div', 'q', m.quote || '（区域批注）'));
        if (m.comment) it.appendChild(el('div', 'c', m.comment));
        var meta = el('div', 'm');
        var dot = el('span', 'lv-dot'); dot.style.background = PALETTE[m.color] || PALETTE.yellow;
        meta.appendChild(dot);
        meta.appendChild(el('span', '', 'p.' + m.page));
        var del = el('button', '', '删除');
        del.style.cssText = 'margin-left:auto;border:0;background:transparent;color:#b91c1c;cursor:pointer;font-size:11px;';
        del.onclick = function (ev) { ev.stopPropagation(); removeMark(m); };
        meta.appendChild(del);
        it.appendChild(meta);
        it.onclick = function () { jumpToMark(m); };
        list.appendChild(it);
      });
  }

  function jumpToMark(m) {
    goto(Number(m.page)).then(function () {
      setTimeout(function () {
        var sh = S.shells[Number(m.page)];
        if (!sh) return;
        Array.prototype.forEach.call(sh.hl.querySelectorAll('.lv-mark'), function (node) {
          node.classList.add('flash');
          setTimeout(function () { node.classList.remove('flash'); }, 1600);
        });
      }, 120);
    });
  }

  function fitWidth() {
    if (!S.doc || !S.ui) return Promise.resolve();
    return S.doc.getPage(1).then(function (page) {
      var base = page.getViewport({ scale: 1 });
      var col = S.transOn ? (Math.min(430, Math.max(260, Math.round(S.ui.stage.clientWidth * 0.42))) + 12) : 0;
      var avail = Math.max(240, S.ui.stage.clientWidth - 36 - col);
      var sc = Math.max(0.3, Math.min(4, avail / base.width));
      return applyScale(sc);
    });
  }

  function setScale(v) {
    S.fit = 'custom';
    return applyScale(Math.max(0.3, Math.min(4, v)));
  }

  function applyScale(sc) {
    S.scale = sc;
    S.ui.zoomVal.textContent = Math.round(sc * 100) + '%';
    var jobs = [];
    Object.keys(S.shells).forEach(function (k) {
      var n = Number(k), sh = S.shells[k];
      if (sh.base) dims(n, sh.base);
      if (sh.loaded) {
        // 重新按新 dpi 取图 + 重建文本层
        sh.loaded = false; sh.textReady = false;
        if (sh.trEl) { try { sh.trEl.remove(); } catch (e) {} sh.trEl = null; }
        jobs.push(ensureLoaded(n));
      }
    });
    return Promise.all(jobs);
  }

  function goto(n) {
    if (!S.total) return Promise.resolve();
    n = Math.max(1, Math.min(S.total, parseInt(n, 10) || 1));
    S.current = n;
    S.ui.pg.value = String(n);
    var sh = S.shells[n];
    if (sh) S.ui.stage.scrollTop = Math.max(0, sh.shell.offsetTop - 6);
    return ensureLoaded(n).then(function () { if (S.transOn) ensureTrans(n); });
  }

  /* ---------- 选区 ---------- */
  function pageOfNode(node) {
    while (node && node !== document.body) {
      if (node.classList && node.classList.contains('lv-shell')) return Number(node.getAttribute('data-page'));
      node = node.parentNode;
    }
    return 0;
  }

  function _mergeSelectionRows(raw) {
    // 同一逻辑行可能因 pdf.js 的 span 切分返回多个矩形；按行中心聚合并取并集。
    var rows = [];
    raw.sort(function (a, b) { return (a.y - b.y) || (a.x - b.x); });
    raw.forEach(function (r) {
      var cy = r.y + r.h / 2;
      var hit = null;
      for (var i = 0; i < rows.length; i++) {
        var q = rows[i], qy = q.y + q.h / 2;
        if (Math.abs(cy - qy) <= Math.min(r.h, q.h) * 0.7) { hit = q; break; }
      }
      if (!hit) rows.push({ x: r.x, y: r.y, w: r.w, h: r.h });
      else {
        var nx = Math.min(hit.x, r.x), ny = Math.min(hit.y, r.y);
        var ex = Math.max(hit.x + hit.w, r.x + r.w), ey = Math.max(hit.y + hit.h, r.y + r.h);
        hit.x = nx; hit.y = ny; hit.w = ex - nx; hit.h = ey - ny;
      }
    });
    return rows;
  }

  function _rangeRectsForTextNode(node, range, imgRect) {
    var value = node.nodeValue || '';
    if (!value.trim()) return [];
    try { if (!range.intersectsNode(node)) return []; } catch (e) { return []; }
    var start = (node === range.startContainer) ? range.startOffset : 0;
    var end = (node === range.endContainer) ? range.endOffset : value.length;
    // 选区首尾空白不参与覆盖（pdf.js 常把行尾空格算进文本节点）。
    var chosen = value.slice(start, end);
    start += (chosen.match(/^\s*/) || [''])[0].length;
    end -= (chosen.match(/\s*$/) || [''])[0].length;
    if (end <= start) return [];
    var sub = node.ownerDocument.createRange();
    sub.setStart(node, start); sub.setEnd(node, end);
    // 对单个文本节点取矩形，避免整段 Range 在绝对定位 span 之间产生竖向跨区域。
    var rect = sub.getBoundingClientRect();
    if (rect.width < 1.5 || rect.height < 1.5) return [];
    // 高度/纵坐标以文字所在 span 为准，避免 Range 行盒比文字本身高 4–7px。
    var host = node.parentElement && node.parentElement.getBoundingClientRect
      ? node.parentElement.getBoundingClientRect() : rect;
    var yRect = (host && host.height >= 1.5) ? host : rect;
    var x = (rect.left - imgRect.left) / imgRect.width;
    var y = (yRect.top - imgRect.top) / imgRect.height;
    var w = rect.width / imgRect.width, h = yRect.height / imgRect.height;
    if (x + w < 0 || y + h < 0 || x > 1 || y > 1) return [];
    var nx = Math.max(0, x), ny = Math.max(0, y);
    return [{ x: nx, y: ny, w: Math.min(w, 1 - nx), h: Math.min(h, 1 - ny) }];
  }

  function selectionInfo() {
    var sel = window.getSelection && window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
    var range = sel.getRangeAt(0);
    var startEl = range.startContainer.nodeType === 3 ? range.startContainer.parentNode : range.startContainer;
    var n = pageOfNode(startEl);
    if (!n) return null;
    var sh = S.shells[n];
    if (!sh || !sh.txt.contains(range.commonAncestorContainer)) return null;
    var text = String(sel.toString() || '').replace(/\s+/g, ' ').trim();
    if (text.length < 2) return null;
    var imgRect = sh.img.getBoundingClientRect();
    if (!imgRect.width || !imgRect.height) return null;

    // 逐文本节点计算，而不是直接消费 range.getClientRects()。后者会把
    // 绝对定位 span 之间的空白/跨页区域也算进去，就是用户看到的竖条和重影。
    var raw = [];
    var texts = [];
    var walker = document.createTreeWalker(sh.txt, NodeFilter.SHOW_TEXT);
    var node;
    while ((node = walker.nextNode())) {
      var part = _rangeRectsForTextNode(node, range, imgRect);
      if (part.length) {
        raw.push.apply(raw, part);
        var value = node.nodeValue || '';
        var s0 = (node === range.startContainer) ? range.startOffset : 0;
        var e0 = (node === range.endContainer) ? range.endOffset : value.length;
        var picked = value.slice(s0, e0).trim();
        if (picked) texts.push(picked);
      }
    }
    if (texts.length) text = texts.join(' ').replace(/\s+/g, ' ').trim();
    if (!raw.length) return null;
    var merged = _mergeSelectionRows(raw);
    var last = merged[merged.length - 1];
    var x = imgRect.left + (last.x + last.w) * imgRect.width;
    var y = imgRect.top + (last.y + last.h) * imgRect.height;
    return { text: text.slice(0, 2000), rects: merged.slice(0, 60), x: x, y: y, page: n };
  }

  function hideMenu() { if (S.menu) { try { S.menu.remove(); } catch (e) {} S.menu = null; } }
  function hidePop() {
    if (S.pop) { try { S.pop.remove(); } catch (e) {} S.pop = null; }
  }

  function popCloseButton() {
    var b = el('button', 'lv-pop-close', '✕');
    b.type = 'button';
    b.title = '关闭';
    b.setAttribute('aria-label', '关闭');
    b.onmousedown = function (ev) { ev.preventDefault(); ev.stopPropagation(); };
    b.onclick = function (ev) {
      ev.preventDefault(); ev.stopPropagation();
      S.skipNextUp = true;
      hidePop();
    };
    return b;
  }

  function showMenu(info) {
    hideMenu();
    var m = el('div', 'lv-menu');
    COLOR_ORDER.forEach(function (c) {
      var sw = el('div', 'sw');
      sw.style.background = PALETTE[c];
      sw.title = '高亮（' + c + '）';
      sw.onmousedown = function (ev) { ev.preventDefault(); };
      sw.onclick = function () { saveMark({ kind: 'highlight', color: c, quote: info.text, rects: info.rects, page: info.page, comment: '' }); hideMenu(); };
      m.appendChild(sw);
    });
    var note = el('button', '', '💬 批注');
    note.onmousedown = function (ev) { ev.preventDefault(); };
    note.onclick = function () { hideMenu(); openMarkPop({ kind: 'note', color: 'yellow', quote: info.text, rects: info.rects, page: info.page, comment: '' }, null, true); };
    m.appendChild(note);
    var tr = el('button', '', '🌐 译');
    tr.onmousedown = function (ev) { ev.preventDefault(); };
    tr.onclick = function () { hideMenu(); translateSelection(info); };
    m.appendChild(tr);
    var copy = el('button', '', '📋 复制');
    copy.onmousedown = function (ev) { ev.preventDefault(); };
    copy.onclick = function () { try { navigator.clipboard.writeText(info.text); toast('已复制'); } catch (e) { toast('复制失败', true); } hideMenu(); };
    m.appendChild(copy);
    var chat = el('button', '', '💬 加入对话');
    chat.onmousedown = function (ev) { ev.preventDefault(); };
    chat.onclick = function () { pushToChat(info.text, info.page); hideMenu(); };
    m.appendChild(chat);

    document.body.appendChild(m);
    m.style.left = Math.min(window.innerWidth - m.offsetWidth - 8, Math.max(8, info.x - m.offsetWidth / 2)) + 'px';
    m.style.top = Math.min(window.innerHeight - m.offsetHeight - 8, info.y + 8) + 'px';
    S.menu = m;
  }

  function centerPop(pop) {
    var hostBox = document.getElementById('lit-summary-box');
    var hb = hostBox && hostBox.getBoundingClientRect ? hostBox.getBoundingClientRect() : null;
    var cx = hb && hb.width > 0 ? hb.left + hb.width / 2 : window.innerWidth / 2;
    var cy = hb && hb.height > 0 ? hb.top + hb.height / 2 : window.innerHeight / 2;
    pop.style.left = Math.max(8, Math.min(window.innerWidth - pop.offsetWidth - 8, cx - pop.offsetWidth / 2)) + 'px';
    pop.style.top = Math.max(8, Math.min(window.innerHeight - pop.offsetHeight - 8, cy - pop.offsetHeight / 2)) + 'px';
  }

  function translateSelection(info) {
    ensureStyle();
    hidePop();
    var pop = el('div', 'lv-pop');
    var head = el('div', 'lv-pop-head');
    head.appendChild(el('span', '', '🌐 译文'));
    head.appendChild(el('span', 'sp'));
    head.appendChild(popCloseButton());
    pop.appendChild(head);
    var orig = el('div', 'orig', info.text.slice(0, 300));
    var trBox = el('div', 'tr', '翻译中…');
    pop.appendChild(orig); pop.appendChild(trBox);
    document.body.appendChild(pop);
    // 译文小窗默认在文献详情弹窗内居中；仍可用标题栏拖动。
    centerPop(pop);
    S.pop = pop;
    makePopDraggable(pop, head);
    apiTranslate([info.text]).then(function (d) {
      if (S.pop !== pop) return;
      if (!d || !d.ok) { trBox.textContent = '翻译失败：' + ((d && d.error) || ''); return; }
      trBox.textContent = (d.translations || [''])[0] || '（空）';
      var row = el('div', 'row');
      var copy = el('button', '', '复制译文');
      copy.onclick = function () { try { navigator.clipboard.writeText(trBox.textContent); toast('已复制'); } catch (e) {} };
      var chat = el('button', 'pri', '加入对话');
      chat.onclick = function () { pushToChat(trBox.textContent + '（原文 p.' + info.page + '）', info.page); hidePop(); };
      row.appendChild(el('span', 'sp')); row.appendChild(copy); row.appendChild(chat);
      pop.appendChild(row);
      centerPop(pop);
    }).catch(function (e) {
      if (S.pop === pop) trBox.textContent = '翻译失败：' + (e && e.message || e);
    });
  }

  function openMarkPop(mark, ev, isNew) {
    ensureStyle();
    hidePop(); hideMenu();
    var pop = el('div', 'lv-pop');
    var head = el('div', 'lv-pop-head');
    head.appendChild(el('span', '', isNew ? '💬 新建批注' : '💬 批注'));
    head.appendChild(el('span', 'sp'));
    head.appendChild(popCloseButton());
    pop.appendChild(head);
    pop.appendChild(el('div', 'orig', '「' + String(mark.quote || '').slice(0, 120) + '」'));
    var ta = el('textarea');
    ta.placeholder = '写批注…（可留空，只做高亮）';
    ta.value = mark.comment || '';
    pop.appendChild(ta);
    var row = el('div', 'row');
    COLOR_ORDER.forEach(function (c) {
      var sw = el('div', 'sw');
      sw.style.cssText = 'width:15px;height:15px;border-radius:4px;border:1px solid rgba(0,0,0,.15);cursor:pointer;background:' + PALETTE[c];
      sw.onclick = function () {
        if (isNew) { mark.color = c; return; }
        apiWrite({ path: S.path, action: 'update', id: mark.id, patch: { color: c }, revision: S.revision }).then(afterWrite);
      };
      row.appendChild(sw);
    });
    row.appendChild(el('span', 'sp'));
    var save = el('button', 'pri', '保存');
    save.onclick = function () {
      if (isNew) {
        saveMark({ kind: 'note', color: mark.color || 'yellow', quote: mark.quote, rects: mark.rects, page: mark.page, comment: ta.value });
        hidePop();
      } else {
        apiWrite({ path: S.path, action: 'update', id: mark.id, patch: { comment: ta.value }, revision: S.revision })
          .then(function (d) { afterWrite(d); hidePop(); });
      }
    };
    row.appendChild(save);
    if (!isNew) {
      var del = el('button', '', '删除');
      del.onclick = function () { removeMark(mark); hidePop(); };
      row.appendChild(del);
    }
    pop.appendChild(row);
    document.body.appendChild(pop);
    var x = ev && ev.clientX || (window.innerWidth / 2);
    var y = ev && ev.clientY || (window.innerHeight / 2);
    pop.style.left = Math.min(window.innerWidth - 310, Math.max(8, x - 60)) + 'px';
    pop.style.top = Math.min(window.innerHeight - 240, Math.max(8, y + 8)) + 'px';
    S.pop = pop;
    makePopDraggable(pop, head);
    setTimeout(function () { try { ta.focus(); } catch (e) {} }, 30);
  }

  function saveMark(mark) {
    if (S.saving) return;
    S.saving = true;
    // 客户端幂等 id：即使一次点击被浏览器派发两次，服务端也按同 id 去重，不会画重影。
    if (!mark.id) {
      mark.id = 'mk_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
    }
    apiWrite({ path: S.path, action: 'add', mark: mark, revision: S.revision }).then(function (d) {
      S.saving = false;
      if (!d.ok) { toast(d.error || '保存失败', true); return; }
      S.revision = d.revision;
      var existing = S.marks.findIndex(function (x) { return x.id === d.mark.id; });
      if (existing >= 0) S.marks[existing] = d.mark; else S.marks.push(d.mark);
        try { var sel = window.getSelection(); if (sel) sel.removeAllRanges(); } catch (e) {}
      renderHighlights(d.mark.page);
      renderSidebar();
      toast('已保存');
    }).catch(function (e) {
      S.saving = false;
      toast('保存失败：' + (e && e.message || e), true);
    });
  }
  function removeMark(m) {
    apiWrite({ path: S.path, action: 'delete', id: m.id, revision: S.revision }).then(function (d) {
      if (!d.ok) { toast(d.error || '删除失败', true); return; }
      S.revision = d.revision;
      S.marks = S.marks.filter(function (x) { return x.id !== m.id; });
      renderHighlights(m.page); renderSidebar();
      toast('已删除');
    });
  }
  function afterWrite(d) {
    if (!d || !d.ok) { toast((d && d.error) || '保存失败', true); return; }
    S.revision = d.revision;
    if (d.mark) {
      S.marks = S.marks.map(function (x) { return x.id === d.mark.id ? d.mark : x; });
      renderHighlights(d.mark.page); renderSidebar();
    }
    toast('已保存');
  }

  function pushToChat(text, page) {
    var input = document.getElementById('input');
    if (!input) { toast('找不到输入框', true); return; }
    var snip = '「' + text + '」（p.' + page + '）\n';
    input.value = (input.value ? input.value.replace(/\s*$/, '\n') : '') + snip;
    input.focus();
    try { input.setSelectionRange(input.value.length, input.value.length); } catch (e) {}
    toast('已加入输入框');
  }

  /* ---------- 生命周期 ---------- */
  function makePopDraggable(pop, head) {
    head.style.cursor = 'move';
    head.addEventListener('mousedown', function (ev) {
      if (ev.button !== 0 || ev.target.closest('button,textarea,input,a')) return;
      var r = pop.getBoundingClientRect();
      S.popDrag = { pop: pop, dx: ev.clientX - r.left, dy: ev.clientY - r.top };
      ev.preventDefault();
      ev.stopPropagation();
    });
  }

  function bindGlobal() {
    function onDown(ev) {
      if (!S.ui) return;
      if (S.menu && S.menu.contains(ev.target)) return;
      if (S.pop && S.pop.contains(ev.target)) return;
      hideMenu();
      if (S.pop) hidePop();
      S.currentSelection = null;
    }
    function onMove(ev) {
      if (!S.popDrag) return;
      var d = S.popDrag;
      d.pop.style.left = Math.max(4, Math.min(window.innerWidth - d.pop.offsetWidth - 4, ev.clientX - d.dx)) + 'px';
      d.pop.style.top = Math.max(4, Math.min(window.innerHeight - d.pop.offsetHeight - 4, ev.clientY - d.dy)) + 'px';
      ev.preventDefault();
    }
    function onUp(ev) {
      if (!S.ui) return;
      if (S.popDrag) { S.popDrag = null; return; }
      if (S.skipNextUp) { S.skipNextUp = false; return; }
      if (S.menu && S.menu.contains(ev.target)) return;
      if (S.pop && S.pop.contains(ev.target)) return;
      // 原生选择：和交互框正文完全同一套浏览器行为，不画自定义蓝色覆盖层。
      setTimeout(function () {
        var info = selectionInfo();
        if (info) showMenu(info); else hideMenu();
      }, 10);
    }
    function onKey(e) {
      if (e.key === 'Escape') {
        var hadPopup = !!(S.menu || S.pop);
        S.popDrag = null; S.currentSelection = null;
        hideMenu(); hidePop();
        if (!hadPopup && S.transOn) setTrans(false);
      }
    }
    var resizeTimer = null;
    function onResize() {
      if (S.fit !== 'width') return;
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () { fitWidth(); }, 200);
    }
    document.addEventListener('mousedown', onDown, true);
    document.addEventListener('mousemove', onMove, true);
    document.addEventListener('mouseup', onUp, true);
    document.addEventListener('keydown', onKey, true);
    window.addEventListener('resize', onResize);
    S.cleanup.push(function () { document.removeEventListener('mousedown', onDown, true); });
    S.cleanup.push(function () { document.removeEventListener('mousemove', onMove, true); });
    S.cleanup.push(function () { document.removeEventListener('mouseup', onUp, true); });
    S.cleanup.push(function () { document.removeEventListener('keydown', onKey, true); });
    S.cleanup.push(function () { window.removeEventListener('resize', onResize); });
  }

  function bindScroll() {
    var stage = S.ui.stage;
    var timer = null;
    stage.addEventListener('scroll', function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        var mid = stage.scrollTop + stage.clientHeight * 0.35;
        var best = 1, bestD = Infinity;
        Object.keys(S.shells).forEach(function (k) {
          var n = Number(k), sh = S.shells[k];
          var top = sh.shell.offsetTop, h = sh.shell.offsetHeight || 1;
          var d = (mid >= top && mid <= top + h) ? 0 : Math.min(Math.abs(mid - top), Math.abs(mid - (top + h)));
          if (d < bestD) { bestD = d; best = n; }
        });
        if (best !== S.current) {
          S.current = best;
          S.ui.pg.value = String(best);
          ensureLoaded(best);
          if (S.transOn) ensureTrans(best);
        }
      }, 90);
    });
    S.cleanup.push(function () { /* stage removed with host */ });
  }

  function bindObserver() {
    if (!('IntersectionObserver' in window)) {
      // 退化：直接加载前 3 页
      for (var i = 1; i <= Math.min(3, S.total); i++) ensureLoaded(i);
      return;
    }
    S.io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        var n = Number(en.target.getAttribute('data-page'));
        if (n) ensureLoaded(n);
      });
    }, { root: S.ui.stage, rootMargin: '900px 0px' });
    Object.keys(S.shells).forEach(function (k) { S.io.observe(S.shells[k].shell); });
    S.cleanup.push(function () { try { S.io.disconnect(); } catch (e) {} });
  }

  function open(container, path, opts) {
    ensureStyle();
    close();
    S.host = container; S.path = path || ''; S.title = (opts && opts.title) || '';
    S.marks = []; S.revision = 0; S.stale = false; S.transOn = false;
    S.shells = {}; S.loaded = {}; S.textReady = {}; S.blocks = {}; S.blockMeta = {}; S.trans = {}; S.transing = {}; S.transOff = {}; S.genTrans = 0;
    S.current = 1; S.scale = 1; S.fit = 'width'; S.gen++;
    if (!S.path) { container.innerHTML = '<div class="lv-empty">缺少文献文件名</div>'; return Promise.resolve(); }

    buildShell();
    bindGlobal();
    bindScroll();

    return loadLib(function (err) {
      if (err) { container.innerHTML = '<div class="lv-empty">' + esc(err.message) + '</div>'; return; }
      return apiMarks(S.path).then(function (d) {
        if (d && d.ok) { S.marks = d.marks || []; S.revision = d.revision || 0; S.stale = !!d.stale; }
        return window.pdfjsLib.getDocument({ url: '/api/papers?path=' + encodeURIComponent(S.path) }).promise;
      }).then(function (doc) {
        S.doc = doc; S.total = doc.numPages;
        S.ui.total.textContent = '/ ' + S.total;
        return doc.getPage(1).then(function (p) {
          var base = p.getViewport({ scale: 1 });
          S.baseW = base.width; S.baseH = base.height;
          for (var n = 1; n <= S.total; n++) {
            makeShell(n);
            dims(n, base);
          }
          return fitWidth();
        });
      }).then(function () {
        bindObserver();
        renderSidebar();
        return ensureLoaded(1);
      }).catch(function (e) {
        container.innerHTML = '<div class="lv-empty">无法打开 PDF：' + esc(e && e.message || e) +
          '<br><br><a href="/api/papers?path=' + encodeURIComponent(S.path) + '" target="_blank">用系统阅读器打开</a></div>';
      });
    });
  }

  function close() {
    S.cleanup.forEach(function (fn) { try { fn(); } catch (e) {} });
    S.cleanup = [];
    hideMenu(); hidePop();
    try { if (S.io) S.io.disconnect(); } catch (e) {}
    S.io = null;
    if (S.doc) { try { S.doc.destroy(); } catch (e) {} }
    S.doc = null; S.total = 0; S.marks = []; S.shells = {}; S.loaded = {}; S.ui = null;
    if (S.host) { try { S.host.innerHTML = ''; } catch (e) {} }
  }

  function refresh() {
    return apiMarks(S.path).then(function (d) {
      if (d && d.ok) {
        S.marks = d.marks || []; S.revision = d.revision || 0; S.stale = !!d.stale;
        Object.keys(S.shells).forEach(function (n) { renderHighlights(Number(n)); });
        renderSidebar();
      }
    });
  }

  window.LitViewer = {
    open: open, close: close, refresh: refresh,
    goto: goto, translate: function (t) { return apiTranslate([t]); },
    showTranslation: translateSelection, pushToChat: pushToChat,
    _state: S, _ensureLoaded: ensureLoaded, _translateSelection: translateSelection,
    _selectionInfo: selectionInfo
  };
})();