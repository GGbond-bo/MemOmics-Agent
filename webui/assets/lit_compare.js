/* MemOmics 文献对照：左原文 PDF / 右结构化译文（2026-11-16）
 *
 * 2026-11-15 的「原位置中文覆盖」有两个硬伤：
 *   1) 只有一个页面，用户点「对照」看不到左右两面；
 *   2) 中文块高度与英文行高不一致，压住正文；一旦译文重排整页都会错位。
 * 现在默认改为左右双栏：左栏原 PDF 页图不动，右栏按 blockId 逐段渲染译文，
 * 两栏按「页 + 页内比例」双向联动，点原文某段可直接定位到对应中文段。
 * 覆盖模式仍保留为可选（只在有合格译文时才落字，缺译段落保留英文原样）。
 */
(function () {
  'use strict';

  var C = {
    host: null, path: '', data: null, mode: 'split', sync: true, scale: 1,
    pages: {}, current: 1, io: null, lock: 0, lockTimer: null, cleanup: [],
    active: { page: 0, index: -1 }, ui: {}, pdfRel: '', prefill: {}, prepareTimer: null
  };

  var MISSING = '（此段暂未译出）';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function esc(s) {
    return String(s || '').replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function style() {
    if (document.getElementById('lit-compare-style')) return;
    var css = [
      '.lc-root{height:100%;display:flex;flex-direction:column;min-height:420px;background:#eef1f5;color:#1f2937;font-size:13px;}',
      '.lc-bar{display:flex;align-items:center;gap:6px;padding:6px 9px;border-bottom:1px solid #d8dce3;background:#fff;font-size:12px;flex-wrap:wrap;}',
      '.lc-bar button{border:1px solid #d8dce3;background:#fff;border-radius:5px;padding:3px 9px;cursor:pointer;font-size:12px;}',
      '.lc-bar button.on{background:#2d8659;color:#fff;border-color:transparent;}',
      '.lc-bar input{width:48px;text-align:center;border:1px solid #d8dce3;border-radius:4px;padding:2px;font-size:12px;}',
      '.lc-sep{width:1px;height:16px;background:#e3e7ee;margin:0 2px;}',
      '.lc-status{color:#667085;font-size:11px;margin-left:auto;}',
      '.lc-body{flex:1;display:flex;min-height:0;}',
      '.lc-pane{flex:1 1 0;min-width:0;overflow:auto;position:relative;padding:12px 10px 48px;}',
      '.lc-pane.is-hidden{display:none;}',
      '.lc-right{border-left:1px solid #d8dce3;background:#fbfcfd;}',
      '.lc-lpage,.lc-rpage{margin:0 auto 16px;position:relative;}',
      '.lc-page-label{text-align:left;font-size:11px;color:#8a6d3b;margin:0 0 5px;position:sticky;top:0;background:rgba(238,241,245,.92);padding:2px 0;z-index:3;}',
      '.lc-right .lc-page-label{background:rgba(251,252,253,.94);color:#667085;}',
      '.lc-frame{position:relative;background:#fff;box-shadow:0 1px 7px rgba(0,0,0,.16);}',
      '.lc-frame img{display:block;width:100%;height:auto;user-select:none;-webkit-user-drag:none;cursor:crosshair;}',
      '.lc-overlays{position:absolute;inset:0;pointer-events:none;}',
      '.lc-ov{position:absolute;box-sizing:border-box;background:#fff;color:#111;overflow:hidden;white-space:normal;overflow-wrap:anywhere;padding:1px 2px;line-height:1.15;border-radius:1px;}',
      '.lc-ov.heading{font-weight:700;}',
      '.lc-flash{position:absolute;box-sizing:border-box;border:2px solid #2d8659;background:rgba(45,134,89,.13);border-radius:2px;pointer-events:none;transition:opacity .45s;}',
      '.lc-cards{max-width:860px;margin:0 auto;}',
      '.lc-card{border:1px solid #e3e7ee;border-radius:7px;padding:8px 10px;margin:0 0 8px;background:#fff;cursor:pointer;line-height:1.62;transition:border-color .15s,box-shadow .15s;}',
      '.lc-card:hover{border-color:#9dc4ae;}',
      '.lc-card.is-active{border-color:#2d8659;box-shadow:0 0 0 2px rgba(45,134,89,.16);}',
      '.lc-card.is-heading{border-left:3px solid #2d8659;}',
      '.lc-card.is-heading .zh{font-weight:700;}',
      '.lc-card.is-pending .zh{color:#98a2b3;}',
      '.lc-card.is-missing{background:#fff9ec;border-color:#f0d9a8;}',
      '.lc-card.is-missing .zh{color:#8a6d3b;}',
      '.lc-card.is-nontrans .zh{color:#98a2b3;font-size:11px;line-height:1.45;}',
      '.lc-card .src{display:none;margin-top:5px;padding-top:5px;border-top:1px dashed #e3e7ee;color:#98a2b3;font-size:11px;line-height:1.5;}',
      '.lc-card:hover .src,.lc-card.is-active .src{display:block;}',
      '.lc-card .retry{margin-left:6px;border:1px solid #e0c98a;background:#fff;color:#8a6d3b;border-radius:4px;padding:0 6px;font-size:11px;cursor:pointer;}',
      '.lc-pdf{position:relative;}',
      '.lc-pdf img{display:block;width:100%;height:auto;box-shadow:0 1px 7px rgba(0,0,0,.16);background:#fff;cursor:crosshair;}',
      '.lc-pdf-empty{padding:22px 12px;border:1px dashed #d8dce3;border-radius:7px;color:#98a2b3;text-align:center;font-size:12px;background:#fff;}',
      '.lc-pdf-empty button{margin-left:6px;border:1px solid #d8dce3;background:#fff;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px;}',
      '.lc-empty{padding:30px;color:#888;text-align:center;}'
    ].join('\n');
    var st = el('style'); st.id = 'lit-compare-style'; st.textContent = css;
    document.head.appendChild(st);
  }

  function paneWidth() {
    if (!C.ui.left) return 700;
    return clamp(C.ui.left.clientWidth - 26, 280, 900) * C.scale;
  }
  function leftWidth() {
    if (!C.ui.left) return 700;
    return clamp(C.ui.left.clientWidth - 26, 280, 900);
  }

  /* ---------------- 左侧：原 PDF 页 ---------------- */

  function makeLeftPage(p) {
    var sec = el('section', 'lc-lpage'); sec.setAttribute('data-page', p.page);
    sec.appendChild(el('div', 'lc-page-label', '原文 · 第 ' + p.page + ' 页'));
    var frame = el('div', 'lc-frame');
    var img = el('img'); img.alt = '第 ' + p.page + ' 页'; img.draggable = false;
    var ov = el('div', 'lc-overlays');
    frame.appendChild(img); frame.appendChild(ov); sec.appendChild(frame);
    C.ui.left.appendChild(sec);
    var rec = { data: p, secL: sec, frame: frame, img: img, ov: ov, boxes: [], loaded: false, flash: null };
    C.pages[p.page] = Object.assign(C.pages[p.page] || {}, rec);
    img.addEventListener('click', function (ev) { onLeftClick(p.page, ev); });
    return rec;
  }

  function ensureOverlay(n) {
    var pg = C.pages[n];
    if (!pg || pg.boxes.length) return;
    (pg.data.blocks || []).forEach(function (b) {
      var d = el('div', 'lc-ov' + (b.kind === 'heading' ? ' heading' : ''));
      d.style.left = (b.rect.x * 100) + '%';
      d.style.top = (b.rect.y * 100) + '%';
      d.style.width = (b.rect.w * 100) + '%';
      d.style.height = (b.rect.h * 100) + '%';
      d.style.display = 'none';
      pg.ov.appendChild(d);
      pg.boxes.push({ data: b, el: d });
    });
  }

  function fitBlock(item, widthPx) {
    var b = item.data, d = item.el;
    var fs = Math.max(7, Math.min(22, b.font_size * C.scale));
    d.style.fontSize = fs + 'px';
    // 中文可能比英文长；只在原矩形内逐级缩小，不改矩形位置。
    for (var i = 0; i < 16 && d.scrollHeight > d.clientHeight + 1 && fs > 6.5; i++) {
      fs -= 0.5; d.style.fontSize = fs + 'px';
    }
  }

  function applyOverlayPage(n) {
    var pg = C.pages[n];
    if (!pg || !pg.tr) return;
    ensureOverlay(n);
    pg.boxes.forEach(function (item, i) {
      var t = (pg.tr[i] || '').trim();
      var src = (pg.data.blocks[i] || {}).text || '';
      var usable = t && t !== src && t.indexOf(MISSING) === -1;
      if (usable) {
        item.el.textContent = t;
        item.el.style.display = 'block';
        fitBlock(item, pg.frame.clientWidth);
      } else {
        // 缺译时保留英文原样，绝不压一块空白
        item.el.style.display = 'none';
      }
    });
  }
  function applyOverlayAll() {
    Object.keys(C.pages).forEach(function (k) { applyOverlayPage(Number(k)); });
  }
  function hideOverlayAll() {
    Object.keys(C.pages).forEach(function (k) {
      (C.pages[k].boxes || []).forEach(function (item) { item.el.style.display = 'none'; });
    });
  }

  /* ---------------- 右侧：结构化译文 ---------------- */

  function makeRightPage(p) {
    var sec = el('section', 'lc-rpage'); sec.setAttribute('data-page', p.page);
    sec.appendChild(el('div', 'lc-page-label', '译文 · 第 ' + p.page + ' 页'));
    var cards = el('div', 'lc-cards');
    var pdf = el('div', 'lc-pdf');
    var pdfImg = el('img'); pdfImg.alt = '译文 PDF 第 ' + p.page + ' 页'; pdfImg.draggable = false;
    pdfImg.style.display = 'none';
    var pdfEmpty = el('div', 'lc-pdf-empty', '本页翻译完成后自动生成译文 PDF');
    pdf.appendChild(pdfImg); pdf.appendChild(pdfEmpty);
    pdfImg.addEventListener('click', function (ev) { onRightPdfClick(p.page, ev); });
    var rec = C.pages[p.page] || {};
    rec.cards = [];
    (p.blocks || []).forEach(function (b, i) {
      var card = el('div', 'lc-card is-pending' + (b.kind === 'heading' ? ' is-heading' : ''));
      card.setAttribute('data-i', String(i));
      var zh = el('div', 'zh', '…');
      var src = el('div', 'src', b.text || '');
      card.appendChild(zh); card.appendChild(src);
      card.addEventListener('click', function () { activate(p.page, i, false); });
      cards.appendChild(card);
      rec.cards.push({ data: b, el: card, zh: zh });
    });
    sec.appendChild(pdf);
    sec.appendChild(cards);
    cards.style.display = 'none';  // 默认双 PDF；文本对照模式再展开
    C.ui.right.appendChild(sec);
    rec.data = p; rec.secR = sec; rec.cardsBox = cards;
    rec.pdfBox = pdf; rec.pdfImg = pdfImg; rec.pdfEmpty = pdfEmpty; rec.pdfRel = '';
    // 已完成的对照任务直接回填译文，避免打开时再次调用模型
    if (C.prefill && Object.keys(C.prefill).length) {
      rec.tr = (p.blocks || []).map(function (b) { return C.prefill[b.id] || ''; });
      rec.prefilled = true;
      rec.cards.forEach(function (_, i) { paintCard(rec, i, rec.tr[i]); });
    }
    C.pages[p.page] = rec;
    return rec;
  }

  function paintCard(pg, i, text) {
    var item = (pg.cards || [])[i];
    if (!item) return;
    var src = (pg.data.blocks[i] || {}).text || '';
    var t = (text || '').trim();
    item.el.classList.remove('is-pending', 'is-missing', 'is-nontrans');
    item.zh.textContent = '';
    if (!needsTranslation(src)) {
      // 无词可译（DOI / 图号 / 数字行）：原样展示，不报错、不给重试
      item.el.classList.add('is-nontrans');
      item.zh.textContent = src;
      return;
    }
    if (!t || t === src) {
      item.el.classList.add('is-missing');
      item.zh.appendChild(document.createTextNode(MISSING));
      var btn = el('button', 'retry', '重试');
      btn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        retryBlock(pg.data.page, i);
      });
      item.zh.appendChild(btn);
    } else {
      item.zh.textContent = t;
    }
  }

  function statusFor(n) {
    var pg = C.pages[n];
    if (!pg || !pg.cards || !pg.cards.length) return '';
    var total = 0, done = 0;
    pg.cards.forEach(function (item, i) {
      var src = (pg.data.blocks[i] || {}).text || '';
      if (!needsTranslation(src)) return;
      total += 1;
      var t = String((pg.tr || [])[i] || '').trim();
      if (t && t !== src) done += 1;
    });
    return '第 ' + n + ' 页 ' + done + '/' + total + ' 段已译';
  }

  /* ---------------- 翻译 ---------------- */

  function needsTranslation(text) {
    // DOI / URL / 页码 / 图号 / 纯符号这类没有可译内容的行，不必显示「未译出」
    var s = String(text || '');
    if (/https?:\/\/|doi\.org|10\.\d{4,}\//i.test(s)) return false;
    return /[A-Za-z]{3,}/.test(s);
  }

  // 后端单次最多 40 段 / 12000 字符，整页 90+ 段必须分批发，否则后半页被截断
  function chunkBlocks(blocks, maxItems, maxChars) {
    var groups = [], cur = [], chars = 0, base = 0;
    blocks.forEach(function (b, i) {
      var len = (b.text || '').length;
      if (cur.length && (cur.length >= maxItems || chars + len > maxChars)) {
        groups.push({ base: base, items: cur });
        cur = []; chars = 0; base = i;
      }
      if (!cur.length) base = i;
      cur.push(b); chars += len;
    });
    if (cur.length) groups.push({ base: base, items: cur });
    return groups;
  }

  function translatePage(n, force) {
    var pg = C.pages[n];
    if (!pg || pg.busy) return Promise.resolve();
    if (pg.tr && !force) {
      if (C.mode === 'split' || C.mode === 'target') ensurePdf(n);
      return Promise.resolve();
    }
    var blocks = pg.data.blocks || [];
    if (!blocks.length) return Promise.resolve();
    pg.busy = true;
    pg.tr = pg.tr || [];
    var groups = chunkBlocks(blocks, 40, 11000);
    var step = 0;
    function run() {
      if (step >= groups.length) {
        pg.busy = false;
        if (C.ui.status) C.ui.status.textContent = statusFor(n) || ('第 ' + n + ' 页已处理');
        if (C.mode === 'split' || C.mode === 'target') ensurePdf(n);
        return Promise.resolve();
      }
      var g = groups[step];
      var texts = g.items.map(function (b) { return b.text; });
      if (C.ui.status) {
        C.ui.status.textContent = '第 ' + n + ' 页翻译中… (' + (step + 1) + '/' + groups.length + ')';
      }
      return fetch('/api/lit/translate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texts: texts, to: 'zh' })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (!d.ok) throw new Error(d.error || '翻译失败');
        (d.translations || []).forEach(function (t, k) {
          var i = g.base + k;
          pg.tr[i] = t;
          paintCard(pg, i, t);
        });
        if (C.mode === 'overlay') applyOverlayPage(n);
        step += 1;
        return run();
      });
    }
    return run().catch(function (e) {
      pg.busy = false;
      if (C.ui.status) C.ui.status.textContent = '第 ' + n + ' 页翻译失败：' + e.message;
    });
  }

  function retryBlock(n, i) {
    var pg = C.pages[n];
    if (!pg || pg.busy) return;
    var block = (pg.data.blocks || [])[i];
    if (!block) return;
    pg.busy = true;
    if (C.ui.status) C.ui.status.textContent = '重试 P' + n + ' 第 ' + (i + 1) + ' 段…';
    fetch('/api/lit/translate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texts: [block.text], to: 'zh' })
    }).then(function (r) { return r.json(); }).then(function (d) {
      var t = ((d.translations || [])[0] || '').trim();
      pg.tr = pg.tr || [];
      pg.tr[i] = t;
      paintCard(pg, i, t);
      if (C.mode === 'overlay') applyOverlayPage(n);
      // 单段重试后需要重建本页译文 PDF，避免右栏停留在旧内容
      pg.pdfRel = '';
      pg.prefilled = false;
      if (C.mode === 'split' || C.mode === 'target') ensurePdf(n);
      pg.busy = false;
      if (C.ui.status) C.ui.status.textContent = statusFor(n);
    }).catch(function (e) {
      pg.busy = false;
      if (C.ui.status) C.ui.status.textContent = '重试失败：' + e.message;
    });
  }

  // 右栏双 PDF：把本页译文写回派生 PDF，再用同一个页图接口渲染
  function ensurePdf(n) {
    var pg = C.pages[n];
    if (!pg || !pg.pdfImg || pg.pdfBusy || pg.pdfRel) return Promise.resolve();
    if (C.pdfRel && pg.prefilled) {
      // 已完成整篇任务：右栏直接取整篇译文 PDF 的对应页，不再逐页重建
      pg.pdfRel = C.pdfRel;
      pg.pdfImg.src = '/api/papers/page?path=' + encodeURIComponent(C.pdfRel) +
        '&page=' + (n - 1) + '&dpi=150';
      pg.pdfImg.style.display = 'block';
      pg.pdfEmpty.style.display = 'none';
      return Promise.resolve();
    }
    if (C.mode !== 'split' && C.mode !== 'target') return Promise.resolve();
    var map = {}, count = 0;
    (pg.data.blocks || []).forEach(function (b, i) {
      var t = String((pg.tr || [])[i] || '').trim();
      if (t && t !== b.text) { map[b.id] = t; count += 1; }
    });
    if (!count) {
      pg.pdfEmpty.textContent = '本页暂无可写回的译文';
      return Promise.resolve();
    }
    pg.pdfBusy = true;
    pg.pdfEmpty.style.display = 'block';
    pg.pdfEmpty.textContent = '正在生成本页译文 PDF…';
    return fetch('/api/lit/translation_pdf', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: C.path, translations: map, page: n })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) throw new Error(d.error || '译文 PDF 生成失败');
      pg.pdfRel = d.rel;
      pg.pdfImg.src = '/api/papers/page?path=' + encodeURIComponent(d.rel) +
        '&page=0&dpi=150&ts=' + Date.now();
      pg.pdfImg.style.display = 'block';
      pg.pdfEmpty.style.display = 'none';
      pg.pdfBusy = false;
      if (C.ui.status) C.ui.status.textContent = '第 ' + n + ' 页译文 PDF 已生成（' + d.written + ' 段）';
    }).catch(function (e) {
      pg.pdfBusy = false;
      pg.pdfEmpty.textContent = '译文 PDF 生成失败：' + e.message;
    });
  }

  function exportPdf() {
    var all = {}, pageCount = 0;
    Object.keys(C.pages).forEach(function (k) {
      var pg = C.pages[k], has = false;
      (pg.data.blocks || []).forEach(function (b, i) {
        var t = String((pg.tr || [])[i] || '').trim();
        if (t && t !== b.text) { all[b.id] = t; has = true; }
      });
      if (has) pageCount += 1;
    });
    if (!Object.keys(all).length) {
      if (C.ui.status) C.ui.status.textContent = '请先完成至少一段翻译，再导出译文 PDF';
      return;
    }
    if (C.ui.status) C.ui.status.textContent = '正在导出译文 PDF…';
    fetch('/api/lit/translation_pdf', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: C.path, translations: all })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) throw new Error(d.error || '导出失败');
      var a = el('a'); a.href = d.download; a.download = d.file; a.target = '_blank';
      document.body.appendChild(a); a.click(); a.remove();
      if (C.ui.status) C.ui.status.textContent = '译文 PDF 已导出：' + d.written + ' 段，覆盖 ' + pageCount + ' 页';
    }).catch(function (e) {
      if (C.ui.status) C.ui.status.textContent = '导出失败：' + e.message;
    });
  }

  function onRightPdfClick(n, ev) {
    var pg = C.pages[n];
    if (!pg || !pg.pdfImg) return;
    var rect = pg.pdfImg.getBoundingClientRect();
    var r = clamp((ev.clientY - rect.top) / Math.max(1, rect.height), 0, 1);
    var blocks = pg.data.blocks || [];
    var best = -1, bd = 1e9;
    blocks.forEach(function (b, i) {
      var d = Math.abs(b.rect.y + b.rect.h / 2 - r);
      if (d < bd) { bd = d; best = i; }
    });
    if (best >= 0) activate(n, best, false);
  }

  function translateSoon() {
    if (C.mode === 'source') return;
    translatePage(C.current);
    [C.current + 1, C.current - 1].forEach(function (n) {
      if (C.pages[n]) translatePage(n);
    });
  }

  /* ---------------- 模式 / 同步 ---------------- */

  var MODES = [
    { id: 'split', label: '双 PDF' },
    { id: 'source', label: '仅原文' },
    { id: 'target', label: '仅译文' },
    { id: 'cards', label: '文本对照' },
    { id: 'overlay', label: '原位置覆盖' }
  ];

  function setMode(m) {
    C.mode = m;
    var left = C.ui.left, right = C.ui.right;
    var showPdf = (m === 'split' || m === 'target');
    left.classList.toggle('is-hidden', m === 'target' || m === 'cards');
    right.classList.toggle('is-hidden', !(showPdf || m === 'cards'));
    Object.keys(C.pages).forEach(function (k) {
      var pg = C.pages[k];
      if (pg.cardsBox) pg.cardsBox.style.display = m === 'cards' ? '' : 'none';
      if (pg.pdfBox) pg.pdfBox.style.display = showPdf ? '' : 'none';
    });
    (C.ui.modeBtns || []).forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-mode') === m); });
    if (m === 'overlay') {
      Object.keys(C.pages).forEach(function (k) { ensureOverlay(Number(k)); });
      applyOverlayAll();
      Object.keys(C.pages).forEach(function (k) { if (C.pages[k].tr) return; translatePage(Number(k)); });
    } else {
      hideOverlayAll();
    }
    if (showPdf) {
      translateSoon();
      ensurePdf(C.current);
    }
    if (m === 'split' || m === 'source' || m === 'overlay') {
      [C.current - 1, C.current, C.current + 1].forEach(function (n) {
        if (C.pages[n]) ensureImage(n);
      });
    }
    if (C.ui.status) {
      C.ui.status.textContent = m === 'overlay'
        ? '覆盖模式：仅在已有合格译文时落字，缺译段落保留英文'
        : (C.sync ? '左右联动已开启' : '左右联动已关闭');
    }
  }

  function findSec(pane, n) {
    return pane.querySelector('[data-page="' + n + '"]');
  }

  function topPage(pane) {
    var list = pane.querySelectorAll('[data-page]');
    var top = pane.scrollTop + 6, best = 1;
    for (var i = 0; i < list.length; i++) {
      var s = list[i], n = Number(s.getAttribute('data-page'));
      if (s.offsetTop <= top) best = n;
      if (s.offsetTop <= top && s.offsetTop + s.offsetHeight > top) return n;
    }
    return best;
  }

  function syncFrom(src) {
    if (!C.sync || C.lock) return;
    var dst = src === C.ui.left ? C.ui.right : C.ui.left;
    if (!dst || dst.classList.contains('is-hidden')) return;
    var n = topPage(src);
    var sSrc = findSec(src, n), sDst = findSec(dst, n);
    if (!sSrc || !sDst) return;
    var r = clamp((src.scrollTop - sSrc.offsetTop) / Math.max(1, sSrc.offsetHeight), 0, 1);
    var target = Math.max(0, sDst.offsetTop + r * sDst.offsetHeight);
    C.lock = 1;
    dst.scrollTop = target;
    clearTimeout(C.lockTimer);
    C.lockTimer = setTimeout(function () { C.lock = 0; }, 90);
  }

  function scrollToPage(n) {
    ['left', 'right'].forEach(function (k) {
      var pane = C.ui[k];
      if (!pane || pane.classList.contains('is-hidden')) return;
      var sec = findSec(pane, n);
      if (!sec) return;
      C.lock = 1;
      pane.scrollTop = Math.max(0, sec.offsetTop - 6);
    });
    clearTimeout(C.lockTimer);
    C.lockTimer = setTimeout(function () { C.lock = 0; }, 90);
  }

  function goto(n) {
    n = clamp(parseInt(n, 10) || 1, 1, (C.data.pages || []).length || 1);
    C.current = n;
    C.ui.pg.value = String(n);
    scrollToPage(n);
    ensureImage(n);
    translatePage(n);
    if (C.mode === 'overlay') applyOverlayPage(n);
  }

  function applyScale() {
    Object.keys(C.pages).forEach(function (k) {
      var pg = C.pages[k];
      if (!pg.frame) return;
      pg.frame.style.width = paneWidth() + 'px';
      pg.frame.style.height = (pg.data.height / pg.data.width * paneWidth()) + 'px';
      if (pg.boxes.length) pg.boxes.forEach(function (item) { fitBlock(item, pg.frame.clientWidth); });
    });
    if (C.ui.right) C.ui.right.style.fontSize = (13 * C.scale).toFixed(1) + 'px';
    if (C.ui.zoom) C.ui.zoom.textContent = Math.round(C.scale * 100) + '%';
  }

  /* ---------------- 交互 ---------------- */

  function flashOn(pg, b) {
    if (pg.flash) { pg.flash.remove(); pg.flash = null; }
    var f = el('div', 'lc-flash');
    f.style.left = (b.rect.x * 100) + '%';
    f.style.top = (b.rect.y * 100) + '%';
    f.style.width = (b.rect.w * 100) + '%';
    f.style.height = (b.rect.h * 100) + '%';
    pg.frame.appendChild(f);
    pg.flash = f;
    setTimeout(function () { if (f.parentNode) f.style.opacity = '0'; }, 900);
    setTimeout(function () { if (f.parentNode) f.remove(); }, 1500);
  }

  function activate(n, i, fromLeft) {
    var pg = C.pages[n];
    if (!pg) return;
    Object.keys(C.pages).forEach(function (k) {
      (C.pages[k].cards || []).forEach(function (c) { c.el.classList.remove('is-active'); });
    });
    var item = (pg.cards || [])[i];
    if (item) {
      item.el.classList.add('is-active');
      C.active = { page: n, index: i };
    }
    var block = (pg.data.blocks || [])[i];
    if (block && pg.frame) flashOn(pg, block);

    // 对侧滚到同一页、同一纵向比例
    if (fromLeft) {
      var pane = C.ui.right;
      var sec = findSec(pane, n);
      if (sec && item) {
        C.lock = 1;
        pane.scrollTop = Math.max(0, sec.offsetTop + (block ? block.rect.y : 0) * sec.offsetHeight - 40);
        clearTimeout(C.lockTimer);
        C.lockTimer = setTimeout(function () { C.lock = 0; }, 90);
      }
    } else {
      var lp = C.ui.left;
      var lsec = findSec(lp, n);
      if (lsec && block) {
        C.lock = 1;
        lp.scrollTop = Math.max(0, lsec.offsetTop + block.rect.y * lsec.offsetHeight - 40);
        clearTimeout(C.lockTimer);
        C.lockTimer = setTimeout(function () { C.lock = 0; }, 90);
      }
    }
    if (C.ui.status) C.ui.status.textContent = '已定位 P' + n + ' 第 ' + (i + 1) + ' 段';
  }

  function onLeftClick(n, ev) {
    var pg = C.pages[n];
    if (!pg || !pg.img) return;
    var rect = pg.img.getBoundingClientRect();
    var r = clamp((ev.clientY - rect.top) / Math.max(1, rect.height), 0, 1);
    var blocks = pg.data.blocks || [];
    var best = -1, bd = 1e9;
    blocks.forEach(function (b, i) {
      var center = b.rect.y + b.rect.h / 2;
      var d = Math.abs(center - r);
      if (d < bd) { bd = d; best = i; }
    });
    if (best >= 0) activate(n, best, true);
  }

  function ensureImage(n) {
    var pg = C.pages[n];
    if (!pg || pg.loaded) return;
    pg.loaded = true;
    pg.img.src = '/api/papers/page?path=' + encodeURIComponent(C.path) +
      '&page=' + (n - 1) + '&dpi=150';
  }

  /* ---------------- 装配 ---------------- */

  function build(d) {
    var root = el('div', 'lc-root');
    var bar = el('div', 'lc-bar');

    var prev = el('button', '', '◀');
    var next = el('button', '', '▶');
    var pg = el('input', ''); pg.value = '1';
    var total = el('span', '', '/ ' + (d.pages || []).length);
    var out = el('button', '', '−');
    var zoom = el('span', '', '100%');
    var inn = el('button', '', '+');
    var fit = el('button', '', '适宽');

    var modeBtns = MODES.map(function (m) {
      var b = el('button', m.id === 'split' ? 'on' : '', m.label);
      b.setAttribute('data-mode', m.id);
      b.onclick = function () { setMode(m.id); };
      return b;
    });
    var syncBtn = el('button', 'on', '联动 ✓');
    var exportBtn = el('button', '', '导出译文 PDF');
    var status = el('span', 'lc-status', '左原文 PDF / 右译文 PDF，按页与段落联动');

    [prev, next, pg, total, el('span', 'lc-sep'), out, zoom, inn, fit,
      el('span', 'lc-sep')].forEach(function (x) { bar.appendChild(x); });
    modeBtns.forEach(function (b) { bar.appendChild(b); });
    bar.appendChild(el('span', 'lc-sep'));
    bar.appendChild(syncBtn);
    bar.appendChild(exportBtn);
    bar.appendChild(status);

    var body = el('div', 'lc-body');
    var left = el('div', 'lc-pane lc-left');
    var right = el('div', 'lc-pane lc-right');
    body.appendChild(left); body.appendChild(right);
    root.appendChild(bar); root.appendChild(body);
    C.host.innerHTML = '';
    C.host.appendChild(root);

    C.ui = { root: root, bar: bar, left: left, right: right, pg: pg, zoom: zoom,
             status: status, modeBtns: modeBtns, syncBtn: syncBtn };

    prev.onclick = function () { goto(C.current - 1); };
    next.onclick = function () { goto(C.current + 1); };
    pg.onchange = function () { goto(pg.value); };
    out.onclick = function () { C.scale = Math.max(0.5, C.scale / 1.2); applyScale(); };
    inn.onclick = function () { C.scale = Math.min(2.5, C.scale * 1.2); applyScale(); };
    fit.onclick = function () { C.scale = 1; applyScale(); };
    syncBtn.onclick = function () {
      C.sync = !C.sync;
      syncBtn.classList.toggle('on', C.sync);
      syncBtn.textContent = C.sync ? '联动 ✓' : '联动';
      if (status) status.textContent = C.sync ? '左右联动已开启' : '左右联动已关闭';
    };
    exportBtn.onclick = exportPdf;

    (d.pages || []).forEach(function (p) {
      makeLeftPage(p);
      makeRightPage(p);
    });
    applyScale();

    left.addEventListener('scroll', function () { syncFrom(left); });
    right.addEventListener('scroll', function () { syncFrom(right); });

    // 左侧页图懒加载 + 触发对译
    if (typeof IntersectionObserver === 'function') {
      C.io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          var n = Number(en.target.getAttribute('data-page'));
          ensureImage(n);
          if (C.mode !== 'source') translatePage(n);
        });
      }, { root: left, rootMargin: '700px 0px' });
      Object.keys(C.pages).forEach(function (k) {
        if (C.pages[k].secL && C.pages[k].secL.parentNode === left) C.io.observe(C.pages[k].secL);
      });
    } else {
      Object.keys(C.pages).forEach(function (k) { ensureImage(Number(k)); });
    }

    goto(1);
  }

  function close() {
    C.cleanup.forEach(function (fn) { try { fn(); } catch (e) {} });
    C.cleanup = [];
    if (C.io) { try { C.io.disconnect(); } catch (e) {} }
    if (C.lockTimer) clearTimeout(C.lockTimer);
    if (C.prepareTimer) clearTimeout(C.prepareTimer);
    C.io = null; C.pages = {}; C.data = null; C.host = null; C.lock = 0;
    C.pdfRel = ''; C.prefill = {}; C.prepareTimer = null;
  }

  function prepare(host, path) {
    style(); close();
    C.host = host; C.path = path;
    host.innerHTML = '<div class="lc-empty">正在检查对照翻译状态…</div>';

    function progress(d) {
      var pct = clamp(Number(d.percent) || 0, 0, 100);
      host.innerHTML = '<div class="lc-empty">' +
        '<div style="font-weight:600;color:#1f2937;margin-bottom:8px;">正在进行对照翻译</div>' +
        '<div style="margin-bottom:8px;">翻译成功并生成译文 PDF 后才能打开对照。</div>' +
        '<div style="color:#667085;margin-bottom:8px;">已处理 ' + (d.done_pages || 0) + '/' + (d.pages || 0) +
        ' 页 · ' + (d.done_blocks || 0) + '/' + (d.total_blocks || 0) + ' 段</div>' +
        '<div style="height:8px;background:#e3e7ee;border-radius:5px;overflow:hidden;max-width:420px;margin:0 auto;">' +
        '<div style="height:100%;width:' + pct + '%;background:#2d8659;"></div></div>' +
        '<div style="color:#98a2b3;margin-top:8px;font-size:11px;">可切换到其它页面，任务会在后台继续。</div></div>';
    }

    function failed(d) {
      host.innerHTML = '<div class="lc-empty">对照翻译失败：' + esc(d.error || d.message || '未知错误') + '</div>';
      var btn = el('button', '', '重新翻译');
      btn.onclick = function () { start(); };
      var box = host.querySelector('.lc-empty');
      if (box) box.appendChild(btn);
    }

    function ready() {
      return fetch('/api/lit/compare_job?path=' + encodeURIComponent(path) + '&include_translations=1',
        { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
        if (d.status !== 'done' || !d.pdf_rel) {
          failed({ error: '译文 PDF 尚未生成完成' });
          return;
        }
        // 任务真正完成后才进入双 PDF 对照
        return open(host, path, { pdfRel: d.pdf_rel, translations: d.translations || {} });
      });
    }

    function poll() {
      C.prepareTimer = null;
      return fetch('/api/lit/compare_job?path=' + encodeURIComponent(path), { cache: 'no-store' })
        .then(function (r) { return r.json(); }).then(function (d) {
          if (d.status === 'done') return ready();
          if (d.status === 'failed') { failed(d); return; }
          progress(d);
          C.prepareTimer = setTimeout(poll, 1500);
        }).catch(function (e) { failed({ error: e.message || e }); });
    }

    function start() {
      host.innerHTML = '<div class="lc-empty">正在创建对照翻译任务…</div>';
      return fetch('/api/lit/compare_job', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d.ok === false) { failed(d); return; }
        if (d.status === 'done') return ready();
        progress(d);
        C.prepareTimer = setTimeout(poll, 500);
      }).catch(function (e) { failed({ error: e.message || e }); });
    }

    return fetch('/api/lit/compare_job?path=' + encodeURIComponent(path), { cache: 'no-store' })
      .then(function (r) { return r.json(); }).then(function (d) {
        if (d.status === 'done' && d.pdf_rel) return ready();
        if (d.status === 'running' || d.status === 'queued') { progress(d); return poll(); }
        return start();
      }).catch(function (e) { failed({ error: e.message || e }); });
  }

  function open(host, path, options) {
    options = options || {};
    style(); close();
    C.host = host; C.path = path; C.data = null; C.pages = {};
    C.pdfRel = String(options.pdfRel || '');
    C.prefill = options.translations || {};
    C.current = 1; C.scale = 1; C.mode = 'split'; C.sync = true;
    host.innerHTML = '<div class="lc-empty">正在读取原始版面…</div>';
    return fetch('/api/lit/layout?path=' + encodeURIComponent(path), { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) {
          host.innerHTML = '<div class="lc-empty">' + esc(d.error || '读取失败') + '</div>';
          return;
        }
        C.data = d;
        build(d);
      })
      .catch(function (e) {
        host.innerHTML = '<div class="lc-empty">对照加载失败：' + esc(e.message || e) + '</div>';
      });
  }

  window.LitCompare = { open: open, prepare: prepare, close: close, _state: C };
})();
