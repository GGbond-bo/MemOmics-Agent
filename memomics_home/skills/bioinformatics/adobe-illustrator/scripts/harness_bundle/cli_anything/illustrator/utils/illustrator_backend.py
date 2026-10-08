"""Illustrator backend: drive Adobe Illustrator via COM -> ExtendScript (JSX).

Verified working on Windows: cscript.exe (VBScript) -> CreateObject("Illustrator.Application")
-> DoJavaScriptFile(path). Returns a JSON string produced inside ExtendScript.

Design notes
------------
* ExtendScript is ES3: there is NO JSON object. JSON is assembled manually with esc().
* Each CLI invocation is a fresh process, so every call opens a temp .jsx + temp .vbs.
* The backend NEVER saves the user's document unless the caller asks for it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

# ---------------------------------------------------------------- cscript


def find_cscript() -> str:
    """Locate cscript.exe without hardcoding drive letters where possible."""
    found = shutil.which("cscript") or shutil.which("cscript.exe")
    if found:
        return found
    for cand in (
        r"C:\Windows\System32\cscript.exe",
        r"C:\Windows\SysWOW64\cscript.exe",
    ):
        if Path(cand).exists():
            return cand
    raise RuntimeError("cscript.exe not found; Illustrator COM bridge unavailable")


# ---------------------------------------------------------------- JSX prelude

_JSX_PRELUDE = r"""
// ---- minimal JSON helpers (ExtendScript is ES3, no JSON object) ----
function esc(s) {
  s = String(s);
  var out = "", i, c;
  for (i = 0; i < s.length; i++) {
    c = s.charAt(i);
    if (c == '"') out += '\\"';
    else if (c == '\\') out += '\\\\';
    else if (c == '\n') out += '\\n';
    else if (c == '\r') out += '';
    else if (c == '\t') out += ' ';
    else out += c;
  }
  return out;
}
function q(s) { return '"' + esc(s) + '"'; }
function num(n) { return (isNaN(n) ? 'null' : String(n)); }
"""


def _wrap(body: str) -> str:
    return _JSX_PRELUDE + "\n" + body


# ---------------------------------------------------------------- JSX bodies

JSX_INFO = _wrap(
    r"""
if (app.documents.length === 0) {
  "{\"version\":" + q(app.version) + ",\"doc_count\":0,\"active_doc\":null}";
} else {
  var d = app.activeDocument;
  var out = '{';
  out += '"version":' + q(app.version) + ',';
  out += '"doc_count":' + num(app.documents.length) + ',';
  out += '"active_doc":' + q(d.name) + ',';
  out += '"saved":' + (d.saved ? 'true' : 'false') + ',';
  out += '"path":' + (d.fullName ? q(d.fullName.fsName) : 'null') + ',';
  out += '"artboard_count":' + num(d.artboards.length) + ',';
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()];
  var rb = ab.artboardRect;
  out += '"active_artboard":' + q(ab.name) + ',';
  out += '"artboard_rect":[' + rb[0] + ',' + rb[1] + ',' + rb[2] + ',' + rb[3] + '],';
  out += '"layer_count":' + num(d.layers.length) + ',';
  out += '"text_frame_count":' + num(d.textFrames.length) + ',';
  out += '"path_item_count":' + num(d.pathItems.length);
  out += '}';
  out;
}
"""
)

JSX_ARTBOARDS = _wrap(
    r"""
if (app.documents.length === 0) {
  "{\"doc_count\":0,\"artboards\":[]}";
} else {
  var d = app.activeDocument;
  var parts = [], i, ab, rb;
  for (i = 0; i < d.artboards.length; i++) {
    ab = d.artboards[i];
    rb = ab.artboardRect;
    parts.push('{"index":' + i + ',"name":' + q(ab.name) +
               ',"rect":[' + rb[0] + ',' + rb[1] + ',' + rb[2] + ',' + rb[3] + ']' +
               ',"active":' + (i === d.artboards.getActiveArtboardIndex() ? 'true' : 'false') + '}');
  }
  '{"doc_count":' + app.documents.length + ',"active_doc":' + q(d.name) +
  ',"artboards":[' + parts.join(',') + ']}';
}
"""
)

JSX_TEXT_LIST = _wrap(
    r"""
if (app.documents.length === 0) {
  "{\"doc_count\":0,\"count\":0,\"items\":[]}";
} else {
  var d = app.activeDocument;
  var items = [], i, tf, sz = null, fn = null, gb, jn = null, jv;
  var LIM = 40;
  for (i = 0; i < d.textFrames.length && i < LIM; i++) {
    tf = d.textFrames[i];
    sz = null; fn = null; jn = null;
    try { sz = tf.textRange.characterAttributes.size; } catch (e) { sz = null; }
    try { fn = tf.textRange.characterAttributes.textFont.name; } catch (e) { fn = null; }
    try {
      jv = tf.textRange.paragraphAttributes.justification;
      if (jv === Justification.CENTER) jn = "center";
      else if (jv === Justification.RIGHT) jn = "right";
      else if (jv === Justification.LEFT) jn = "left";
      else jn = "other";
    } catch (ej) { jn = null; }
    gb = tf.geometricBounds;
    items.push('{"index":' + i +
               ',"contents":' + q(tf.contents) +
               ',"size":' + num(sz) +
               ',"font":' + (fn === null ? 'null' : q(fn)) +
               ',"align":' + (jn === null ? 'null' : q(jn)) +
               ',"bounds":[' + gb[0] + ',' + gb[1] + ',' + gb[2] + ',' + gb[3] + ']}');
  }
  '{"doc_count":' + app.documents.length + ',"active_doc":' + q(d.name) +
  ',"count":' + d.textFrames.length + ',"returned":' + items.length +
  ',"items":[' + items.join(',') + ']}';
}
"""
)


def jsx_text_set(size: float | None = None, font: str | None = None,
                 align: str | None = None, index: int = -1,
                 pattern: str | None = None, from_size: float | None = None) -> str:
    """Build JSX that restyles MATCHING text frames of the ACTIVE document (no save).

    Filters (AND-combined, all optional):
      index >= 0  -> only that frame
      pattern     -> only frames whose contents contain the substring (case-insensitive)
      from_size   -> only frames whose CURRENT size equals it (±0.15 pt)
    Actions: size / font / align (left|center|right). No filter = all frames.
    """
    size_js = "null" if size is None else str(float(size))
    font_js = "null" if not font else json.dumps(font)
    align_js = "null" if not align else json.dumps(str(align).lower())
    pat_js = "null" if pattern is None else json.dumps(pattern)
    from_js = "null" if from_size is None else str(float(from_size))
    return _wrap(
        f"""
var TARGET_SIZE = {size_js};
var TARGET_FONT = {font_js};
var TARGET_ALIGN = {align_js};
var IDX = {int(index)};
var PATTERN = {pat_js};
var FROM_SIZE = {from_js};
if (app.documents.length === 0) {{
  "{{\\"error\\":\\"no open document\\"}}";
}} else {{
  var d = app.activeDocument;
  var changed = 0, skipped = 0, i, tf, ca, ok, pp = null, cs = null, jj = null;
  if (PATTERN !== null) pp = String(PATTERN).toLowerCase();
  if (TARGET_ALIGN !== null) {{
    jj = Justification.CENTER;
    if (TARGET_ALIGN === "left") jj = Justification.LEFT;
    else if (TARGET_ALIGN === "right") jj = Justification.RIGHT;
  }}
  var touched = [];
  for (i = 0; i < d.textFrames.length; i++) {{
    tf = d.textFrames[i];
    ok = true;
    if (IDX >= 0 && i !== IDX) ok = false;
    if (ok && pp !== null) {{
      try {{ if (String(tf.contents).toLowerCase().indexOf(pp) < 0) ok = false; }}
      catch (e1) {{ ok = false; }}
    }}
    if (ok && FROM_SIZE !== null) {{
      try {{ cs = tf.textRange.characterAttributes.size; }}
      catch (e2) {{ cs = null; }}
      if (cs === null || Math.abs(cs - FROM_SIZE) > 0.15) ok = false;
    }}
    if (!ok) {{ skipped++; continue; }}
    try {{
      ca = tf.textRange.characterAttributes;
      if (TARGET_SIZE !== null) ca.size = TARGET_SIZE;
      if (TARGET_FONT !== null) ca.textFont = app.textFonts.getByName(TARGET_FONT);
      if (jj !== null) tf.textRange.paragraphAttributes.justification = jj;
      // hardening (2026-10-04): verify the write stuck; re-assert up to 2 rounds.
      if (TARGET_SIZE !== null) {{
        var rs = 0;
        for (rs = 0; rs < 2; rs++) {{
          try {{
            if (Math.abs(tf.textRange.characterAttributes.size - TARGET_SIZE) <= 0.01) {{ break; }}
            ca.size = TARGET_SIZE;
          }} catch (e4) {{}}
        }}
      }}
      if (jj !== null) {{
        try {{
          if (tf.textRange.paragraphAttributes.justification !== jj) {{
            tf.textRange.paragraphAttributes.justification = jj;
          }}
        }} catch (e5) {{}}
      }}
      changed++;
      if (touched.length < 40) touched.push(i);
    }} catch (e3) {{
      skipped++;
    }}
  }}
  var out = '{{';
  out += '"action":"text-set",';
  out += '"active_doc":' + q(d.name) + ',';
  out += '"changed":' + changed + ',';
  out += '"skipped":' + skipped + ',';
  out += '"total":' + d.textFrames.length + ',';
  out += '"touched":[' + touched.join(',') + '],';
  out += '"size":' + num(TARGET_SIZE) + ',';
  out += '"size_from":' + num(FROM_SIZE) + ',';
  out += '"font":' + (TARGET_FONT === null ? 'null' : q(TARGET_FONT)) + ',';
  out += '"align":' + (TARGET_ALIGN === null ? 'null' : q(TARGET_ALIGN)) + ',';
  out += '"index":' + IDX + ',';
  out += '"pattern":' + (PATTERN === null ? 'null' : q(PATTERN)) + ',';
  out += '"saved":false';
  out += '}}';
  out;
}}
"""
    )


def jsx_probe_text(text: str = "MemOmics CLI probe", size: float = 12.0) -> str:
    """Create an ISOLATED new document, add a rect + text, export PNG, close without saving.

    Never touches the user's open documents.
    """
    safe = json.dumps(text)
    return _wrap(
        f"""
var TEXT = {safe};
var SIZE = {float(size)};
var outPath = "";

var newDoc = app.documents.add(DocumentColorSpace.RGB, 400, 300);
var rect = newDoc.pathItems.rectangle(250, 60, 280, 160);
rect.filled = true;
// NOTE: build the colour object directly. Do NOT use swatches.getByName("CMYK Red"):
// this document is RGB, so the CMYK swatch does not exist -> Error 1302 (verified bug).
var rgb = new RGBColor();
rgb.red = 240; rgb.green = 90; rgb.blue = 70;
rect.fillColor = rgb;

var tf = newDoc.textFrames.add();
tf.contents = TEXT;
tf.position = [70, 210];
tf.textRange.characterAttributes.size = SIZE;

outPath = Folder.temp.fsName + "/memomics_cli_probe.png";
var f = new File(outPath);
var opts = new ExportOptionsPNG24();
opts.antiAliasing = true;
opts.transparency = false;
opts.artBoardClipping = true;
newDoc.exportFile(f, ExportType.PNG24, opts);

var info = '{{';
info += '"pathitems":' + newDoc.pathItems.length + ',';
info += '"textframes":' + newDoc.textFrames.length + ',';
info += '"text":' + q(TEXT) + ',';
info += '"size":' + num(SIZE) + ',';
info += '"png":' + q(outPath) + ',';
info += '"png_exists":' + (f.exists ? 'true' : 'false') + ',';
info += '"png_bytes":' + (f.exists ? f.length : 0);
info += '}}';

newDoc.close(SaveOptions.DONOTSAVECHANGES);
info + '';
"""
    )


def jsx_export(out_path: str, fmt: str = "pdf", png_bg: str = "transparent") -> str:
    fmt = fmt.upper()
    trans_js = "true" if str(png_bg).lower() != "white" else "false"
    safe_path = json.dumps(out_path.replace("\\", "/"))
    return _wrap(
        f"""
var OUT = {safe_path};
var FMT = "{fmt}";
var TRANS = {trans_js};
if (app.documents.length === 0) {{
  "{{\\"error\\":\\"no open document\\"}}";
}} else {{
  var d = app.activeDocument;
  var f = new File(OUT);
  if (FMT === "PDF") {{
    var o = new PDFSaveOptions();
    o.preserveEditability = false;
    d.saveAs(f, o);
  }} else if (FMT === "SVG") {{
    var o2 = new ExportOptionsSVG();
    d.exportFile(f, ExportType.SVG, o2);
  }} else {{
    var o3 = new ExportOptionsPNG24();
    o3.antiAliasing = true;
    o3.artBoardClipping = true;
    o3.transparency = TRANS;
    d.exportFile(f, ExportType.PNG24, o3);
  }}
  var res = '{{';
  res += '"action":"export",';
  res += '"doc":' + q(d.name) + ',';
  res += '"format":"' + FMT + '",';
  res += '"path":' + q(OUT) + ',';
  res += '"exists":' + (f.exists ? 'true' : 'false') + ',';
  res += '"bytes":' + (f.exists ? f.length : 0) + ',';
  res += '"saved":' + (d.saved ? 'true' : 'false');
  res += '}}';
  res;
}}
"""
    )


def jsx_gradient_probe() -> str:
    """Workaround probe: ExtendScript cannot *construct* a gradient directly.

    Strategy: reuse a gradient swatch that already exists in the document
    (`swatches.getByName(<gradient>).color` returns a GradientColor).
    Runs in an ISOLATED document; never touches the user's files.
    """
    return _wrap(
        r"""
var newDoc = app.documents.add(DocumentColorSpace.RGB, 400, 300);

// 1) inventory gradient swatches
var grads = [], i, sw, gname = null, err = "", applied = false;
for (i = 0; i < newDoc.swatches.length; i++) {
  sw = newDoc.swatches[i];
  if (sw.typename === "Gradient") grads.push(sw.name);
}

// 2) apply the first available gradient to a rect (workaround path)
if (grads.length > 0) {
  gname = grads[0];
  try {
    var r = newDoc.pathItems.rectangle(250, 60, 280, 160);
    r.filled = true;
    r.fillColor = newDoc.swatches.getByName(gname).color;
    applied = true;
  } catch (e) {
    err = String(e);
  }
}

// 3) correct ExtendScript path: build a GradientColor and point it at a Gradient
var viaGradientColor = false;
if (newDoc.gradients.length > 0) {
  try {
    var r2 = newDoc.pathItems.rectangle(250, 60, 280, 160);
    r2.filled = true;
    var gc = new GradientColor();
    gc.gradient = newDoc.gradients[0];
    gc.origin = [80, 260];
    gc.angle = 45;
    r2.fillColor = gc;
    viaGradientColor = true;
  } catch (e2) {
    err = err + " | gradientcolor: " + String(e2);
  }
}

// 4) diagnostic: what swatch typenames actually exist?
var tns = [], j, seen = {}, t;
for (j = 0; j < newDoc.swatches.length; j++) {
  t = newDoc.swatches[j].typename;
  if (!seen[t]) { seen[t] = true; tns.push(t); }
}

var out = '{';
out += '"gradient_swatches":[' + (grads.length ? '"' + grads.join('","') + '"' : '') + '],';
out += '"gradient_count":' + grads.length + ',';
out += '"swatch_typenames":[' + (tns.length ? '"' + tns.join('","') + '"' : '') + '],';
out += '"gradients_collection":' + newDoc.gradients.length + ',';
out += '"applied_via_swatch":' + (applied ? 'true' : 'false') + ',';
var viaCollection = false;
out += '"applied_via_collection":' + (viaCollection ? 'true' : 'false') + ',';
out += '"applied_via_gradientcolor":' + (viaGradientColor ? 'true' : 'false') + ',';
out += '"used_name":' + (gname === null ? 'null' : q(gname)) + ',';
out += '"error":' + (err === "" ? 'null' : q(err)) + ',';
out += '"pathitems":' + newDoc.pathItems.length;
out += '}';
newDoc.close(SaveOptions.DONOTSAVECHANGES);
out + '';
"""
    )


# ------------------------------------------------- full-chain loop commands
# 2026-10-04: added for the build -> look -> adjust -> look acceptance loop.
# Coordinate convention for ALL new commands: x = px from artboard LEFT,
# y = px from artboard TOP (screen-like, y grows downwards). Converted to
# Illustrator-native coords inside the JSX (y grows upwards).


def parse_rgb(color: str) -> tuple:
    """'#RRGGBB' / '#RGB' / 'RRGGBB' -> (r, g, b). Raises ValueError when bad."""
    h = str(color).strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in h):
        raise ValueError(f"bad color: {color!r} (expect #RRGGBB)")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def norm_hex(color: str) -> str:
    r, g, b = parse_rgb(color)
    return f"#{r:02x}{g:02x}{b:02x}"


def jsx_new_doc(width: float = 800, height: float = 600) -> str:
    """Create a NEW untitled RGB document (never saved; left open for the loop)."""
    return _wrap(
        f"""
var d = app.documents.add(DocumentColorSpace.RGB, {float(width)}, {float(height)});
var ab = d.artboards[0].artboardRect;
var out = '{{';
out += '"action":"new-doc",';
out += '"created":true,';
out += '"doc_count":' + app.documents.length + ',';
out += '"active_doc":' + q(d.name) + ',';
out += '"saved":' + (d.saved ? 'true' : 'false') + ',';
out += '"artboard_rect":[' + ab.join(',') + ']';
out += '}}';
out + '';
"""
    )


def jsx_rect(x: float, y: float, w: float, h: float, color: str = "#e04040") -> str:
    """Draw a rectangle on the ACTIVE document. x/y = from left/top. No save."""
    r, g, b = parse_rgb(color)
    hx = norm_hex(color)
    return _wrap(
        f"""
var X = {float(x)}, Y = {float(y)}, W = {float(w)}, H = {float(h)};
if (app.documents.length === 0) {{
  '{{"error":"no open document"}}';
}} else {{
  var d = app.activeDocument;
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var r = d.pathItems.rectangle(ab[1] - Y, ab[0] + X, W, H);
  r.filled = true;
  var c = new RGBColor(); c.red = {r}; c.green = {g}; c.blue = {b};
  r.fillColor = c;
  var bd = r.geometricBounds;
  var out = '{{';
  out += '"action":"rect",';
  out += '"index":' + (d.pathItems.length - 1) + ',';
  out += '"pathitems":' + d.pathItems.length + ',';
  out += '"bounds":[' + bd.join(',') + '],';
  out += '"fill":' + q('{hx}') + ',';
  out += '"saved":' + (d.saved ? 'true' : 'false');
  out += '}}';
  out;
}}
"""
    )


def jsx_text_add(content: str, x: float, y: float, size: float = 24.0,
                 color: str = "#111111", font: str = None) -> str:
    """Add a text frame to the ACTIVE document. x/y = anchor from left/top. No save."""
    safe = json.dumps(content)
    r, g, b = parse_rgb(color)
    hx = norm_hex(color)
    font_js = "null" if not font else json.dumps(font)
    return _wrap(
        f"""
var TEXT = {safe};
var X = {float(x)}, Y = {float(y)}, SZ = {float(size)};
var FN = {font_js};
if (app.documents.length === 0) {{
  '{{"error":"no open document"}}';
}} else {{
  var d = app.activeDocument;
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var tf = d.textFrames.add();
  tf.contents = TEXT;
  tf.position = [ab[0] + X, ab[1] - Y];
  var err = "";
  try {{ tf.textRange.characterAttributes.size = SZ; }} catch (e) {{ err = err + String(e); }}
  try {{
    var c = new RGBColor(); c.red = {r}; c.green = {g}; c.blue = {b};
    tf.textRange.characterAttributes.fillColor = c;
  }} catch (e2) {{ err = err + String(e2); }}
  if (FN !== null) {{
    try {{ tf.textRange.characterAttributes.textFont = app.textFonts.getByName(FN); }}
    catch (e3) {{ err = err + String(e3); }}
  }}
  // HARDENING (2026-10-04, observed intermittently): a fresh frame's FIRST
  // characterAttributes write is sometimes dropped (frame keeps the 12pt default).
  // Verify + re-assert in a bounded read->write->read loop (max 3), then report the
  // ACTUAL stored size. Deliberately NO app.redraw() here (keep the call profile
  // plain; a one-off Illustrator fail-fast crash was observed in a long session).
  var attempt, sizeActual = null;
  for (attempt = 0; attempt < 3; attempt++) {{
    try {{ sizeActual = tf.textRange.characterAttributes.size; }} catch (e5) {{ sizeActual = null; }}
    if (sizeActual !== null && Math.abs(sizeActual - SZ) <= 0.01) {{ break; }}
    try {{ tf.textRange.characterAttributes.size = SZ; }} catch (e6) {{ err = err + String(e6); }}
    try {{ sizeActual = tf.textRange.characterAttributes.size; }} catch (e7) {{ sizeActual = null; }}
    if (sizeActual !== null && Math.abs(sizeActual - SZ) <= 0.01) {{ break; }}
  }}
  var bd = tf.geometricBounds;
  var out = '{{';
  out += '"action":"text-add",';
  out += '"index":' + (d.textFrames.length - 1) + ',';
  out += '"textframes":' + d.textFrames.length + ',';
  out += '"contents":' + q(TEXT) + ',';
  out += '"size":' + num(sizeActual) + ',';
  out += '"size_requested":' + num(SZ) + ',';
  out += '"bounds":[' + bd.join(',') + '],';
  out += '"fill":' + q('{hx}') + ',';
  out += '"error":' + (err === "" ? 'null' : q(err)) + ',';
  out += '"saved":' + (d.saved ? 'true' : 'false');
  out += '}}';
  out;
}}
"""
    )


def jsx_recolor(color: str, index: int = -1, target: str = "path") -> str:
    """Recolor path items (rectangles) or text frames. index<0 = all. No save."""
    r, g, b = parse_rgb(color)
    hx = norm_hex(color)
    return _wrap(
        f"""
var IDX = {int(index)}, TARGET = "{target}";
if (app.documents.length === 0) {{
  '{{"error":"no open document"}}';
}} else {{
  var d = app.activeDocument;
  var changed = 0, total = 0, i, it;
  var c = new RGBColor(); c.red = {r}; c.green = {g}; c.blue = {b};
  if (TARGET === "text") {{
    total = d.textFrames.length;
    for (i = 0; i < total; i++) {{
      if (IDX >= 0 && i !== IDX) continue;
      try {{ d.textFrames[i].textRange.characterAttributes.fillColor = c; changed++; }} catch (e) {{}}
    }}
  }} else {{
    total = d.pathItems.length;
    for (i = 0; i < total; i++) {{
      if (IDX >= 0 && i !== IDX) continue;
      try {{ d.pathItems[i].filled = true; d.pathItems[i].fillColor = c; changed++; }} catch (e) {{}}
    }}
  }}
  var out = '{{';
  out += '"action":"recolor",';
  out += '"target":"' + TARGET + '",';
  out += '"index":' + IDX + ',';
  out += '"changed":' + changed + ',';
  out += '"total":' + total + ',';
  out += '"fill":' + q('{hx}') + ',';
  out += '"saved":' + (d.saved ? 'true' : 'false');
  out += '}}';
  out;
}}
"""
    )


def jsx_move(index: int = -1, dx: float = 0.0, dy: float = 0.0, target: str = "path") -> str:
    """Move one path item / text frame, or ALL page items (target=all).

    dx right+, dy DOWN+ (screen-like). Returns bounds before/after (native coords).
    """
    return _wrap(
        f"""
var IDX = {int(index)}, DX = {float(dx)}, DY = {float(dy)}, TARGET = "{target}";
if (app.documents.length === 0) {{
  '{{"error":"no open document"}}';
}} else {{
  var d = app.activeDocument;
  var ok = false, err = "", bd = null, moved = 0, nestedSk = 0, i, it, b0, b1;
  var unionBounds = function () {{
    var L = 1e9, T = -1e9, R = -1e9, B = 1e9, k, o, g;
    for (k = 0; k < d.pageItems.length; k++) {{
      o = d.pageItems[k];
      try {{
        g = o.geometricBounds;
        if ((g[2] - g[0]) > 0.001 || (g[1] - g[3]) > 0.001) {{
          if (g[0] < L) L = g[0];
          if (g[1] > T) T = g[1];
          if (g[2] > R) R = g[2];
          if (g[3] < B) B = g[3];
        }}
      }} catch (eg) {{}}
    }}
    if (L > R || B > T) return null;
    return [L, T, R, B];
  }};
  b0 = unionBounds();
  try {{
    if (TARGET === "all") {{
      // NOTE (2026-10-04, verified the hard way): document.pageItems INCLUDES items
      // nested inside groups. Translating every member would move a nested item once
      // per containment level (depth-2 => 2x, depth-3 => 3x). Translate ONLY depth-1
      // items, i.e. direct children of a layer; nested content follows its ancestor.
      for (i = 0; i < d.pageItems.length; i++) {{
        it = d.pageItems[i];
        var isTop = false;
        try {{ isTop = (String(it.parent.typename) === "Layer"); }} catch (ep) {{ isTop = false; }}
        if (!isTop) {{ nestedSk++; continue; }}
        try {{ it.translate(DX, -DY); moved++; }} catch (ei) {{}}
      }}
      ok = (moved > 0);
      bd = unionBounds();
    }} else if (TARGET === "text") {{
      var tf = d.textFrames[IDX];
      var p = tf.position;
      tf.position = [p[0] + DX, p[1] - DY];
      bd = tf.geometricBounds;
      moved = 1;
      ok = true;
    }} else {{
      var pit = d.pathItems[IDX];
      pit.translate(DX, -DY);
      bd = pit.geometricBounds;
      moved = 1;
      ok = true;
    }}
  }} catch (e) {{ err = String(e); }}
  var out = '{{';
  out += '"action":"move",';
  out += '"target":"' + TARGET + '",';
  out += '"index":' + IDX + ',';
  out += '"moved":' + moved + ',';
  out += '"nested_skipped":' + nestedSk + ',';
  out += '"ok":' + (ok ? 'true' : 'false') + ',';
  out += '"bounds":' + (bd === null ? 'null' : ('[' + bd.join(',') + ']')) + ',';
  out += '"bounds_before":' + (b0 === null ? 'null' : ('[' + b0.join(',') + ']')) + ',';
  out += '"error":' + (err === "" ? 'null' : q(err)) + ',';
  out += '"saved":' + (d.saved ? 'true' : 'false');
  out += '}}';
  out;
}}
"""
    )


def jsx_close_untitled(dry_run: bool = False) -> str:
    """Close UNSAVED documents whose name starts with 未标题 (harness-made strays).

    Defensive: only touches unsaved 未标题-* docs, always DONOTSAVECHANGES.
    """
    dr = "true" if dry_run else "false"
    return _wrap(
        f"""
var DRY = {dr};
var before = app.documents.length, closed = [], kept = [], i, d, nm, isU;
for (i = app.documents.length - 1; i >= 0; i--) {{
  d = app.documents[i];
  nm = String(d.name);
  isU = false;
  try {{ isU = (nm.charCodeAt(0) === 26410 && nm.charCodeAt(1) === 26631 && nm.charCodeAt(2) === 39064); }} catch (e) {{ isU = false; }}
  var isEmpty = (d.pathItems.length === 0 && d.textFrames.length === 0);
  if (isU && (d.saved === false || isEmpty)) {{
    if (!DRY) {{ d.close(SaveOptions.DONOTSAVECHANGES); }}
    closed.push(nm);
  }} else {{ kept.push(nm); }}
}}
var cl = [], kp = [];
for (i = 0; i < closed.length; i++) cl.push(q(String(closed[i])));
for (i = 0; i < kept.length; i++) kp.push(q(String(kept[i])));
var out = '{{';
out += '"action":"close-untitled",';
out += '"dry_run":' + (DRY ? 'true' : 'false') + ',';
out += '"docs_before":' + before + ',';
out += '"closed":[' + cl.join(',') + '],';
out += '"kept":[' + kp.join(',') + '],';
out += '"docs_after":' + app.documents.length;
out += '}}';
out + '';
"""
    )


# ------------------------------------------------- file import & document ops
# 2026-10-04 (round 2): added for the real panel-prep workflow (open a PDF panel,
# restyle its text, fit it into an A4 top half, export, close without saving).


def jsx_open(path: str) -> str:
    """Open an .ai / .pdf / .svg file as a document (editable text when AI can). No save."""
    safe = json.dumps(str(path).replace("\\", "/"))
    return _wrap(
        f"""
var P = {safe};
var f = new File(P);
if (!f.exists) {{
  '{{"error":"file not found","path":' + q(P) + '}}';
}} else {{
  var before = app.documents.length;
  var d = null, err = "", prev = null;
  try {{ prev = app.userInteractionLevel; app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; }} catch (e0) {{}}
  try {{ d = app.open(f); }} catch (e) {{ err = String(e); }}
  try {{ if (prev !== null) app.userInteractionLevel = prev; }} catch (e9) {{}}
  if (d === null) {{
    '{{"action":"open","opened":false,"path":' + q(P) + ',"error":' + q(err) + '}}';
  }} else {{
    var ab = [0, 0, 0, 0];
    try {{ ab = d.artboards[0].artboardRect; }} catch (eab) {{}}
    var out = '{{';
    out += '"action":"open",';
    out += '"opened":true,';
    out += '"path":' + q(P) + ',';
    out += '"docs_before":' + before + ',';
    out += '"doc_count":' + app.documents.length + ',';
    out += '"active_doc":' + q(d.name) + ',';
    out += '"saved":' + (d.saved ? 'true' : 'false') + ',';
    out += '"artboard_count":' + d.artboards.length + ',';
    out += '"artboard_rect":[' + ab.join(',') + '],';
    out += '"text_frame_count":' + d.textFrames.length + ',';
    out += '"path_item_count":' + d.pathItems.length + ',';
    out += '"placed_item_count":' + d.placedItems.length + ',';
    out += '"group_item_count":' + d.groupItems.length + ',';
    out += '"error":' + (err === "" ? 'null' : q(err));
    out += '}}';
    out + '';
  }}
}}
"""
    )


def jsx_artboard_set(index: int = 0, w: float = 0.0, h: float = 0.0,
                     x: float | None = None, y: float | None = None) -> str:
    """Resize one artboard (origin kept unless x/y offsets given). No save."""
    x_js = "null" if x is None else str(float(x))
    y_js = "null" if y is None else str(float(y))
    return _wrap(
        f"""
var IDX = {int(index)}, W = {float(w)}, H = {float(h)}, OX = {x_js}, OY = {y_js};
if (app.documents.length === 0) {{
  '{{"error":"no open document"}}';
}} else {{
  var d = app.activeDocument;
  if (IDX < 0 || IDX >= d.artboards.length) {{
    '{{"action":"artboard-set","ok":false,"error":"artboard index out of range","count":' + d.artboards.length + '}}';
  }} else {{
    var ab = d.artboards[IDX];
    var cur = ab.artboardRect;
    var LEFT = (OX === null) ? cur[0] : (cur[0] + OX);
    var TOP = (OY === null) ? cur[1] : (cur[1] - OY);
    ab.artboardRect = [LEFT, TOP, LEFT + W, TOP - H];
    var now = ab.artboardRect;
    var out = '{{';
    out += '"action":"artboard-set",';
    out += '"ok":true,';
    out += '"index":' + IDX + ',';
    out += '"before":[' + cur.join(',') + '],';
    out += '"after":[' + now.join(',') + '],';
    out += '"artboard_count":' + d.artboards.length + ',';
    out += '"w":' + num(W) + ',';
    out += '"h":' + num(H) + ',';
    out += '"saved":' + (d.saved ? 'true' : 'false');
    out += '}}';
    out + '';
  }}
}}
"""
    )


def jsx_place(path: str, x: float | None = None, y: float | None = None,
              w: float | None = None, h: float | None = None) -> str:
    """Place an external file as a LINKED item into the ACTIVE document (no save).

    NOTE: placed PDF/SVG stay linked graphics -> their text is NOT editable.
    Use `open` when the text must be restyled.
    """
    safe = json.dumps(str(path).replace("\\", "/"))
    x_js = "null" if x is None else str(float(x))
    y_js = "null" if y is None else str(float(y))
    w_js = "null" if w is None else str(float(w))
    h_js = "null" if h is None else str(float(h))
    return _wrap(
        f"""
var P = {safe}, X = {x_js}, Y = {y_js}, W = {w_js}, H = {h_js};
var f = new File(P);
if (app.documents.length === 0) {{
  '{{"error":"no open document"}}';
}} else if (!f.exists) {{
  '{{"action":"place","ok":false,"error":"file not found","path":' + q(P) + '}}';
}} else {{
  var d = app.activeDocument;
  var pi = null, err = "", prev = null;
  try {{ prev = app.userInteractionLevel; app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; }} catch (e0) {{}}
  try {{ pi = d.placedItems.add(); pi.file = f; }} catch (e) {{ err = String(e); }}
  try {{ if (prev !== null) app.userInteractionLevel = prev; }} catch (e9) {{}}
  if (pi === null || err !== "") {{
    '{{"action":"place","ok":false,"error":' + q(err) + '}}';
  }} else {{
    var w0 = pi.width, h0 = pi.height, k;
    if (W !== null && H !== null) {{ pi.width = W; pi.height = H; }}
    else if (W !== null) {{ k = W / w0; pi.width = W; pi.height = h0 * k; }}
    else if (H !== null) {{ k = H / h0; pi.height = H; pi.width = w0 * k; }}
    if (X !== null || Y !== null) {{
      var abx = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
      var tgtX = (X === null) ? pi.position[0] : (abx[0] + X);
      var tgtY = (Y === null) ? pi.position[1] : (abx[1] - Y);
      try {{ pi.position = [tgtX, tgtY]; }} catch (ep) {{ err = err + String(ep); }}
    }}
    var bd = pi.geometricBounds;
    var out = '{{';
    out += '"action":"place",';
    out += '"ok":' + (err === "" ? 'true' : 'false') + ',';
    out += '"file":' + q(P) + ',';
    out += '"placed_count":' + d.placedItems.length + ',';
    out += '"width":' + num(pi.width) + ',';
    out += '"height":' + num(pi.height) + ',';
    out += '"bounds":[' + bd.join(',') + '],';
    out += '"error":' + (err === "" ? 'null' : q(err)) + ',';
    out += '"saved":' + (d.saved ? 'true' : 'false');
    out += '}}';
    out + '';
  }}
}}
"""
    )


def jsx_close_doc(all_docs: bool = False, force: bool = False, dry_run: bool = False) -> str:
    """Close the active document (or all) WITHOUT saving.

    Safety guard: named documents that are not 未标题-* are refused unless force=True.
    """
    all_js = "true" if all_docs else "false"
    force_js = "true" if force else "false"
    dry_js = "true" if dry_run else "false"
    return _wrap(
        f"""
var ALL = {all_js}, FORCE = {force_js}, DRY = {dry_js};
var before = app.documents.length;
var closed = [], refused = [], i, d, nm;
var isUntitled = function (n) {{
  try {{ return (n.charCodeAt(0) === 26410 && n.charCodeAt(1) === 26631 && n.charCodeAt(2) === 39064); }}
  catch (e) {{ return false; }}
}};
var list = [];
if (before > 0) {{
  if (ALL) {{ for (i = 0; i < app.documents.length; i++) list.push(app.documents[i]); }}
  else {{ list.push(app.activeDocument); }}
}}
for (i = 0; i < list.length; i++) {{
  d = list[i];
  nm = String(d.name);
  if (isUntitled(nm) || FORCE) {{
    closed.push(nm);
    if (!DRY) {{ try {{ d.close(SaveOptions.DONOTSAVECHANGES); }} catch (e2) {{}} }}
  }} else {{
    refused.push(nm);
  }}
}}
var cl = [], rf = [];
for (i = 0; i < closed.length; i++) cl.push(q(String(closed[i])));
for (i = 0; i < refused.length; i++) rf.push(q(String(refused[i])));
var out = '{{';
out += '"action":"close-doc",';
out += '"dry_run":' + (DRY ? 'true' : 'false') + ',';
out += '"all":' + (ALL ? 'true' : 'false') + ',';
out += '"force":' + (FORCE ? 'true' : 'false') + ',';
out += '"docs_before":' + before + ',';
out += '"closed":[' + cl.join(',') + '],';
out += '"refused":[' + rf.join(',') + '],';
out += '"docs_after":' + app.documents.length;
out += '}}';
out + '';
"""
    )


JSX_BOUNDS = _wrap(
    r"""
if (app.documents.length === 0) {
  '{"error":"no open document"}';
} else {
  var d = app.activeDocument;
  var ab = d.artboards[d.artboards.getActiveArtboardIndex()].artboardRect;
  var L = 1e9, T = -1e9, R = -1e9, B = 1e9, n = 0, i, o, g;
  for (i = 0; i < d.pageItems.length; i++) {
    o = d.pageItems[i];
    try {
      g = o.geometricBounds;
      if ((g[2] - g[0]) > 0.001 || (g[1] - g[3]) > 0.001) {
        if (g[0] < L) L = g[0];
        if (g[1] > T) T = g[1];
        if (g[2] > R) R = g[2];
        if (g[3] < B) B = g[3];
        n++;
      }
    } catch (eg) {}
  }
  var out = '{"action":"bounds",';
  out += '"doc":' + q(d.name) + ',';
  out += '"page_items":' + d.pageItems.length + ',';
  out += '"counted":' + n + ',';
  out += '"textframes":' + d.textFrames.length + ',';
  out += '"pathitems":' + d.pathItems.length + ',';
  out += '"placeditems":' + d.placedItems.length + ',';
  out += '"artboard_rect":[' + ab.join(',') + '],';
  if (n === 0) {
    out += '"bounds":null,"bounds_screen":null';
  } else {
    out += '"bounds":[' + L + ',' + T + ',' + R + ',' + B + '],';
    out += '"bounds_screen":[' + L + ',' + (ab[1] - T) + ',' + R + ',' + (ab[1] - B) + ']';
  }
  out += '}';
  out + '';
}
"""
)


JSX_ITEMS = _wrap(
    r"""
function h2(v) {
  v = Math.round(v);
  if (v < 0) v = 0;
  if (v > 255) v = 255;
  var s = v.toString(16);
  return (s.length < 2) ? ('0' + s) : s;
}
function hexOf(c) {
  if (!c) return null;
  try {
    if (String(c.typename) !== 'RGBColor') return String(c.typename);
    return '#' + h2(c.red) + h2(c.green) + h2(c.blue);
  } catch (e) { return null; }
}
if (app.documents.length === 0) {
  '{"error":"no open document"}';
} else {
  var d = app.activeDocument;
  var ps = [], ts = [], i, it, bd, fh, sz;
  for (i = 0; i < d.pathItems.length && i < 40; i++) {
    it = d.pathItems[i];
    bd = it.geometricBounds;
    fh = hexOf(it.fillColor);
    ps.push('{"index":' + i + ',"bounds":[' + bd.join(',') + ']' +
            ',"fill":' + (fh === null ? 'null' : q(fh)) + '}');
  }
  for (i = 0; i < d.textFrames.length && i < 40; i++) {
    it = d.textFrames[i];
    bd = it.geometricBounds;
    sz = null;
    try { sz = it.textRange.characterAttributes.size; } catch (e) { sz = null; }
    try { fh = hexOf(it.textRange.characterAttributes.fillColor); } catch (e2) { fh = null; }
    ts.push('{"index":' + i + ',"contents":' + q(it.contents) +
            ',"size":' + num(sz) + ',"bounds":[' + bd.join(',') + ']' +
            ',"fill":' + (fh === null ? 'null' : q(fh)) + '}');
  }
  '{"doc":' + q(d.name) +
  ',"pathitems_count":' + d.pathItems.length +
  ',"textframes_count":' + d.textFrames.length +
  ',"pathitems":[' + ps.join(',') + ']' +
  ',"textframes":[' + ts.join(',') + ']}';
}
"""
)


# ---------------------------------------------------------------- runner


class IllustratorError(RuntimeError):
    pass


def run_jsx(jsx_body: str, timeout: int = 180, keep_dir: Path | None = None) -> dict:
    """Run JSX via the COM bridge; retry ONCE for connection-level failures only.

    Connection-level = COM_FAIL (object could not be created / app busy or starting)
    or unparseable output (cscript produced nothing). Then the script never ran, so
    a retry is safe. A JS_FAIL (the script threw / the app refused it) is NOT
    retried: it may have partially executed — surface it and re-check state with
    read-only commands (info/items/bounds) before running a write again.
    """
    try:
        return _run_jsx_once(jsx_body, timeout=timeout, keep_dir=keep_dir)
    except IllustratorError as exc:
        msg = str(exc)
        transient = ("COM_FAIL" in msg) or ("unexpected bridge output" in msg)
        if not transient:
            raise
        time.sleep(1.5)
        return _run_jsx_once(jsx_body, timeout=timeout, keep_dir=keep_dir)


def _run_jsx_once(jsx_body: str, timeout: int = 180, keep_dir: Path | None = None) -> dict:
    """Write jsx + vbs to temp, run cscript, return parsed JSON dict."""
    cscript = find_cscript()
    workdir = Path(keep_dir) if keep_dir else Path(tempfile.mkdtemp(prefix="ai_cli_"))
    workdir.mkdir(parents=True, exist_ok=True)
    jsx_path = workdir / "op.jsx"
    vbs_path = workdir / "run.vbs"
    jsx_path.write_text(jsx_body, encoding="utf-8")
    jsx_fwd = jsx_path.as_posix()
    vbs_path.write_text(
        "On Error Resume Next\r\n"
        "Dim app, res\r\n"
        'Set app = CreateObject("Illustrator.Application")\r\n'
        "If Err.Number <> 0 Then\r\n"
        '  WScript.Echo "COM_FAIL|" & Err.Description\r\n'
        "  WScript.Quit 1\r\n"
        "End If\r\n"
        f'res = app.DoJavaScriptFile("{jsx_fwd}")\r\n'
        "If Err.Number <> 0 Then\r\n"
        '  WScript.Echo "JS_FAIL|" & Err.Description\r\n'
        "  WScript.Quit 2\r\n"
        "End If\r\n"
        'WScript.Echo "RESULT|" & res\r\n',
        encoding="utf-8",
    )
    proc = subprocess.run(
        [cscript, "//nologo", str(vbs_path)],
        capture_output=True,
        timeout=timeout,
    )

    def _decode(raw: bytes) -> str:
        # cscript writes to the console using the OEM code page (GBK on zh-CN), so try
        # UTF-8 first and fall back to GBK before resorting to replacement characters.
        for enc in ("utf-8", "gbk", "cp936"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    out = _decode(proc.stdout or b"").strip()
    err = _decode(proc.stderr or b"").strip()
    if proc.returncode != 0 or out.startswith("COM_FAIL|") or out.startswith("JS_FAIL|"):
        raise IllustratorError(f"bridge failed rc={proc.returncode}: {out or err}")
    if not out.startswith("RESULT|"):
        raise IllustratorError(f"unexpected bridge output: {out[:400]}")
    payload = out[len("RESULT|"):].strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise IllustratorError(f"non-JSON payload: {payload[:400]}") from exc


def is_available() -> bool:
    try:
        find_cscript()
    except RuntimeError:
        return False
    try:
        run_jsx(_wrap('"{\\"ok\\":true}";'), timeout=60)
        return True
    except Exception:
        return False