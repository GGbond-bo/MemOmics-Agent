/* MemOmics PDF 阅读器（EmbedPDF/PDFium 真引擎，2026-11-14）
 * 完整渲染文字、图、表、公式；选区使用 EmbedPDF SelectionPlugin.segmentRects。
 * 高亮由 AnnotationPlugin 渲染，同时写回 papers/.annotations/<stem>.json。
 */
import EmbedPDF from './vendor/embedpdf/embedpdf.js';

(function () {
  'use strict';
  var COLORS = ['yellow', 'green', 'blue', 'pink', 'purple'];
  var HEX = { yellow: '#fcd34d', green: '#86efac', blue: '#7dd3fc', pink: '#f9a8d4', purple: '#d8b4fe' };
  var E = {
    host: null, path: '', container: null, registry: null, selection: null, annotations: null,
    docId: '', marks: [], revision: 0, pageSizes: {}, current: null, menu: null,
    pointer: { x: 300, y: 300 }, cleanup: [], creating: {}
  };

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function esc(s) { return String(s || '').replace(/[&<>"']/g, function (c) { return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]; }); }
  function toast(t) { var x = el('div', 'ep-toast', t); document.body.appendChild(x); setTimeout(function () { try { x.remove(); } catch (e) {} }, 1800); }

  function style() {
    if (document.getElementById('lit-embedpdf-style')) return;
    var css = [
      '.ep-host{height:100%;min-height:420px;background:#eef1f5;}',
      '.ep-target{height:100%;min-height:420px;}',
      '.ep-target embedpdf-container{display:block;width:100%;height:100%;min-height:420px;}',
      '.ep-loading{height:100%;display:flex;align-items:center;justify-content:center;color:#667085;font-size:13px;}',
      '.ep-menu{position:fixed;z-index:10040;background:#fff;border:1px solid #d8dce3;border-radius:8px;box-shadow:0 6px 22px rgba(0,0,0,.24);padding:5px;display:flex;gap:4px;align-items:center;}',
      '.ep-menu button{border:0;background:transparent;cursor:pointer;font-size:12px;padding:3px 6px;border-radius:5px;color:#1f2937;}',
      '.ep-menu button:hover{background:#eef1f5;}',
      '.ep-menu .sw{width:16px;height:16px;border-radius:4px;border:1px solid rgba(0,0,0,.15);cursor:pointer;}',
      '.ep-toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:10050;background:#166534;color:#fff;padding:7px 14px;border-radius:6px;font-size:12px;}'
    ].join('\n');
    var st = el('style'); st.id = 'lit-embedpdf-style'; st.textContent = css; document.head.appendChild(st);
  }

  function rectNorm(r, ps) {
    if (!r || !ps || !ps.width || !ps.height) return null;
    return { x: r.origin.x / ps.width, y: r.origin.y / ps.height,
             w: r.size.width / ps.width, h: r.size.height / ps.height };
  }
  function rectPt(r, ps) {
    return { origin: { x: r.x * ps.width, y: r.y * ps.height },
             size: { width: r.w * ps.width, height: r.h * ps.height } };
  }
  function boundsOf(rects) {
    var x1 = Math.min.apply(null, rects.map(function (r) { return r.origin.x; }));
    var y1 = Math.min.apply(null, rects.map(function (r) { return r.origin.y; }));
    var x2 = Math.max.apply(null, rects.map(function (r) { return r.origin.x + r.size.width; }));
    var y2 = Math.max.apply(null, rects.map(function (r) { return r.origin.y + r.size.height; }));
    return { origin: { x: x1, y: y1 }, size: { width: x2 - x1, height: y2 - y1 } };
  }

  function hideMenu() { if (E.menu) { try { E.menu.remove(); } catch (e) {} E.menu = null; } }

  function showMenu(info) {
    hideMenu();
    var m = el('div', 'ep-menu');
    COLORS.forEach(function (c) {
      var sw = el('div', 'sw'); sw.style.background = HEX[c]; sw.title = '高亮（' + c + '）';
      sw.onmousedown = function (e) { e.preventDefault(); };
      sw.onclick = function () { saveSelection(c, ''); hideMenu(); };
      m.appendChild(sw);
    });
    var note = el('button', '', '💬 批注');
    note.onmousedown = function (e) { e.preventDefault(); };
    note.onclick = function () {
      var comment = window.prompt('写批注（保存到本文献）', '');
      if (comment !== null) saveSelection('yellow', comment);
      hideMenu();
    };
    m.appendChild(note);
    var tr = el('button', '', '🌐 译');
    tr.onmousedown = function (e) { e.preventDefault(); };
    tr.onclick = function () {
      hideMenu();
      if (window.LitViewer && LitViewer.showTranslation) LitViewer.showTranslation({ text: info.text, x: E.pointer.x, y: E.pointer.y, page: info.page });
    };
    m.appendChild(tr);
    var copy = el('button', '', '📋 复制');
    copy.onmousedown = function (e) { e.preventDefault(); };
    copy.onclick = function () { navigator.clipboard.writeText(info.text); toast('已复制'); hideMenu(); };
    m.appendChild(copy);
    var chat = el('button', '', '💬 加入对话');
    chat.onmousedown = function (e) { e.preventDefault(); };
    chat.onclick = function () {
      if (window.LitViewer && LitViewer.pushToChat) LitViewer.pushToChat(info.text, info.page);
      hideMenu();
    };
    m.appendChild(chat);
    document.body.appendChild(m);
    m.style.left = Math.min(window.innerWidth - m.offsetWidth - 8, Math.max(8, E.pointer.x - m.offsetWidth / 2)) + 'px';
    m.style.top = Math.min(window.innerHeight - m.offsetHeight - 8, E.pointer.y + 8) + 'px';
    E.menu = m;
  }

  function apiWrite(payload) {
    return fetch('/api/lit/marks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      .then(function (r) { return r.json(); });
  }

  function saveSelection(color, comment) {
    var cur = E.current;
    if (!cur || !cur.formatted.length || !E.annotations) return;
    var chain = Promise.resolve();
    cur.formatted.forEach(function (f) {
      var ps = E.pageSizes[f.pageIndex];
      if (!ps) return;
      var id = 'mk_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8) + '_p' + f.pageIndex;
      var rects = f.segmentRects && f.segmentRects.length ? f.segmentRects : [f.rect];
      var obj = {
        id: id, type: 9, pageIndex: f.pageIndex, rect: f.rect,
        segmentRects: rects, strokeColor: HEX[color], opacity: 0.4,
        contents: comment || cur.text, custom: { markId: id }, created: new Date(), modified: new Date()
      };
      E.creating[id] = true;
      E.annotations.forDocument(cur.docId).createAnnotation(f.pageIndex, obj);
      var mark = {
        id: id, annotation_id: id, kind: comment ? 'note' : 'highlight', page: f.pageIndex + 1,
        space: 'norm', rects: rects.map(function (r) { return rectNorm(r, ps); }).filter(Boolean),
        quote: cur.text, comment: comment || '', color: color
      };
      chain = chain.then(function () {
        return apiWrite({ path: E.path, action: 'add', mark: mark, revision: E.revision }).then(function (d) {
          if (!d.ok) throw new Error(d.error || '保存失败');
          E.revision = d.revision; E.marks.push(d.mark);
        });
      });
    });
    chain.then(function () {
      try { E.selection.forDocument(cur.docId).clear(); } catch (e) {}
      toast('已保存');
    }).catch(function (e) { toast('保存失败：' + e.message); });
  }

  function importMarks() {
    if (!E.annotations) return;
    var items = [];
    E.marks.forEach(function (m) {
      if (m.space !== 'norm' || !(m.rects || []).length) return;
      var ps = E.pageSizes[m.page - 1]; if (!ps) return;
      var rects = m.rects.map(function (r) { return rectPt(r, ps); });
      items.push({ annotation: {
        id: m.annotation_id || m.id, type: 9, pageIndex: m.page - 1,
        rect: boundsOf(rects), segmentRects: rects,
        strokeColor: HEX[m.color] || HEX.yellow, opacity: 0.4,
        contents: m.comment || m.quote || '', custom: { markId: m.id }
      } });
    });
    if (items.length) {
      try { E.annotations.importAnnotations(items); } catch (e) { console.warn('[EmbedPDF] import marks failed', e); }
    }
  }

  function bindAnnotationSync() {
    if (!E.annotations || !E.annotations.onAnnotationEvent) return;
    E.annotations.onAnnotationEvent(function (ev) {
      if (!ev || !ev.annotation) return;
      var id = ev.annotation.id;
      if (ev.type === 'create') {
        if (E.creating[id]) { delete E.creating[id]; return; }
        if (E.marks.some(function (m) { return (m.annotation_id || m.id) === id; })) return;
        // 通过 EmbedPDF 自带工具创建的批注也同步进 MemOmics。
        var ps = E.pageSizes[ev.pageIndex]; if (!ps) return;
        var rects = ev.annotation.segmentRects || [ev.annotation.rect];
        var mark = {
          id: id, annotation_id: id, kind: 'highlight', page: ev.pageIndex + 1, space: 'norm',
          rects: rects.map(function (r) { return rectNorm(r, ps); }).filter(Boolean),
          quote: ev.annotation.contents || '', comment: ev.annotation.contents || '',
          color: COLORS.find(function (c) { return HEX[c] === ev.annotation.strokeColor; }) || 'yellow'
        };
        apiWrite({ path: E.path, action: 'add', mark: mark, revision: E.revision }).then(function (d) {
          if (d.ok) { E.revision = d.revision; E.marks.push(d.mark); }
        });
      } else if (ev.type === 'delete') {
        var m = E.marks.find(function (x) { return (x.annotation_id || x.id) === id; });
        if (!m) return;
        apiWrite({ path: E.path, action: 'delete', id: m.id, revision: E.revision }).then(function (d) {
          if (d.ok) { E.revision = d.revision; E.marks = E.marks.filter(function (x) { return x.id !== m.id; }); }
        });
      }
    });
  }

  function bindSelection() {
    if (!E.selection) return;
    E.selection.onEndSelection(function (ev) {
      if (!ev || !ev.documentId) return;
      var scope = E.selection.forDocument(ev.documentId);
      var formatted = scope.getFormattedSelection() || [];
      if (!formatted.length) { hideMenu(); return; }
      scope.getSelectedText().toPromise().then(function (lines) {
        var text = (lines || []).join('\n').replace(/\s+/g, ' ').trim();
        if (!text) { hideMenu(); return; }
        E.docId = ev.documentId;
        E.current = { docId: ev.documentId, formatted: formatted, text: text, page: formatted[0].pageIndex + 1 };
        showMenu(E.current);
      }).catch(function () { hideMenu(); });
    });
  }

  function open(host, path) {
    style(); close();
    E.host = host; E.path = path; E.marks = []; E.revision = 0; E.current = null;
    host.innerHTML = '<div class="ep-loading">正在加载 PDF 引擎…</div>';
    return fetch('/api/lit/marks?path=' + encodeURIComponent(path), { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (md) {
      E.marks = md && md.ok ? (md.marks || []) : [];
      E.revision = md && md.ok ? md.revision : 0;
      host.innerHTML = '';
      var target = el('div', 'ep-target'); host.appendChild(target);
      var container = EmbedPDF.init({
        type: 'container', target: target,
        src: '/api/papers?path=' + encodeURIComponent(path),
        worker: false,
        wasmUrl: '/assets/vendor/embedpdf/pdfium.wasm',
        fontFallback: null,
        fonts: { ui: null, signature: null },
        tabBar: 'never',
        pan: { defaultMode: 'never' },
        i18n: { defaultLocale: 'zh-CN' },
        theme: { preference: 'light' },
        annotations: { autoCommit: true, annotationAuthor: 'MemOmics' }
      });
      if (!container) throw new Error('EmbedPDF 初始化失败');
      E.container = container;
      return container.registry.then(function (registry) {
        E.registry = registry;
        var sp = registry.getPlugin('selection');
        var ap = registry.getPlugin('annotation');
        E.selection = sp && sp.provides ? sp.provides() : null;
        E.annotations = ap && ap.provides ? ap.provides() : null;
        // 页尺寸直接来自 PDF 文档对象，不再依赖已移除的阅读模式接口。
        try {
          var dm = registry.getPlugin('document-manager');
          var dmc = dm && dm.provides ? dm.provides() : null;
          var active = dmc && dmc.getActiveDocument ? dmc.getActiveDocument() : null;
          (active && active.pages || []).forEach(function (p) {
            if (p.size && p.size.width && p.size.height) {
              E.pageSizes[p.index] = { width: p.size.width, height: p.size.height };
            }
          });
        } catch (e) { console.warn('[EmbedPDF] page sizes unavailable', e); }
        bindSelection(); bindAnnotationSync();
        setTimeout(importMarks, 800);
        function pointer(ev) { E.pointer = { x: ev.clientX, y: ev.clientY }; }
        document.addEventListener('mouseup', pointer, true);
        E.cleanup.push(function () { document.removeEventListener('mouseup', pointer, true); });
        function key(ev) { if (ev.key === 'Escape') hideMenu(); }
        document.addEventListener('keydown', key, true);
        E.cleanup.push(function () { document.removeEventListener('keydown', key, true); });
      });
    }).catch(function (e) {
      console.error('[EmbedPDF] open failed', e);
      host.innerHTML = '<div class="ep-loading">PDF 引擎加载失败：' + esc(e.message || e) + '</div>';
      throw e;
    });
  }

  function close() {
    E.cleanup.forEach(function (fn) { try { fn(); } catch (e) {} }); E.cleanup = [];
    hideMenu();
    try { if (E.container) E.container.remove(); } catch (e) {}
    E.container = null; E.registry = null; E.selection = null; E.annotations = null;
    E.current = null; E.marks = []; E.pageSizes = {}; E.host = null;
  }

  window.LitEmbed = { open: open, close: close, _state: E };
})();