from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import ClassVar

from .base import ReportContext
from .commit_word_frequencies import _word_counts
from .commit_wordcloud import _load_stopwords_file

_DEFAULT_MAX_WORDS = 300


def _resolve_max_words(raw: object) -> int:
    if raw is None:
        return _DEFAULT_MAX_WORDS
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        print(
            f"warning: reports.commit-wordcloud-interactive.max_words={raw!r} is "
            f"not a positive integer; falling back to {_DEFAULT_MAX_WORDS}.",
            file=sys.stderr,
        )
        return _DEFAULT_MAX_WORDS
    return raw


class CommitWordcloudInteractive:
    id: ClassVar[str] = "commit-wordcloud-interactive"
    description: ClassVar[str] = "Self-contained interactive, tunable wordcloud (HTML)."
    filename: ClassVar[str] = "commit-wordcloud-interactive.html"
    requires_jira: ClassVar[bool] = False
    accepted_params: ClassVar[frozenset[str]] = frozenset({"max_words", "stopwords_file"})

    def render(self, ctx: ReportContext) -> Path:
        out = ctx.output_dir / self.filename
        max_words = _resolve_max_words(ctx.params.get("max_words"))
        extra_stopwords = _load_stopwords_file(ctx.params.get("stopwords_file"))

        counts = _word_counts(ctx)
        for word in extra_stopwords:
            counts.pop(word, None)

        # [[word, count], ...] sorted by descending count (most_common), capped so
        # the client-side "max words" slider still has some headroom above the
        # PNG's 200-word default.
        words = [[w, n] for w, n in counts.most_common(max_words)]

        # Escape "</" so the payload can never terminate the surrounding <script>.
        data_json = json.dumps(words, ensure_ascii=False).replace("</", "<\\/")
        html = _TEMPLATE.replace("__WORDS_JSON__", data_json)
        out.write_text(html, encoding="utf-8")
        return out


# Self-contained HTML: inline CSS + data + app JS, no external requests, so the
# file opens offline exactly like the Plotly HTML reports. `__WORDS_JSON__` is the
# only substitution point (see render()). Everything else — including all `{}` in
# the JS/CSS — is literal, which is why this is a plain string, not an f-string.
_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Interactive commit wordcloud</title>
<style>
  :root { --bg:#ffffff; --fg:#1f2430; --muted:#6b7280; --line:#e5e7eb; --accent:#2563eb; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         color:var(--fg); background:var(--bg); }
  header { padding:14px 18px; border-bottom:1px solid var(--line); }
  header h1 { margin:0; font-size:18px; }
  header p { margin:4px 0 0; color:var(--muted); font-size:13px; }
  .layout { display:flex; gap:0; align-items:stretch; min-height:calc(100vh - 62px); }
  .cloud { flex:1 1 auto; min-width:0; position:relative; }
  canvas { display:block; width:100%; height:100%; }
  .empty { position:absolute; inset:0; display:none; align-items:center; justify-content:center;
           color:var(--muted); font-size:15px; }
  aside { flex:0 0 320px; border-left:1px solid var(--line); display:flex; flex-direction:column;
          max-height:calc(100vh - 62px); }
  .controls { padding:14px 16px; border-bottom:1px solid var(--line); }
  .controls h2, .wl h2 { margin:0 0 10px; font-size:13px; text-transform:uppercase;
                         letter-spacing:.04em; color:var(--muted); }
  .ctl { margin-bottom:12px; }
  .ctl label { display:flex; justify-content:space-between; font-size:13px; margin-bottom:4px; }
  .ctl .val { color:var(--accent); font-variant-numeric:tabular-nums; }
  .ctl input[type=range] { width:100%; }
  .btns { display:flex; gap:8px; flex-wrap:wrap; }
  button { font:inherit; font-size:13px; padding:6px 10px; border:1px solid var(--line);
           background:#f9fafb; border-radius:6px; cursor:pointer; }
  button:hover { border-color:var(--accent); color:var(--accent); }
  .wl { padding:14px 16px; overflow:hidden; display:flex; flex-direction:column; flex:1 1 auto; }
  .wl .search { width:100%; padding:6px 8px; margin-bottom:10px; border:1px solid var(--line);
                border-radius:6px; font:inherit; font-size:13px; }
  .rows { overflow-y:auto; flex:1 1 auto; }
  .row { display:grid; grid-template-columns: 1fr auto 62px 26px; gap:6px; align-items:center;
         padding:3px 0; font-size:13px; border-bottom:1px solid #f3f4f6; }
  .row .w { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .row .c { color:var(--muted); font-variant-numeric:tabular-nums; text-align:right; }
  .row input.mult { width:60px; padding:2px 4px; font:inherit; font-size:12px;
                    border:1px solid var(--line); border-radius:4px; }
  .row button.rm { padding:0; width:24px; height:24px; line-height:1; border-radius:4px; }
  .hint { color:var(--muted); font-size:12px; margin-top:8px; }
</style>
</head>
<body>
<header>
  <h1>Interactive commit wordcloud</h1>
  <p>Tune the weighting sliders, adjust or remove individual words &mdash;
     the cloud redraws live.</p>
</header>
<div class="layout">
  <div class="cloud">
    <canvas id="cv"></canvas>
    <div class="empty" id="empty">No words captured.</div>
  </div>
  <aside>
    <div class="controls">
      <h2>Weights</h2>
      <div class="ctl">
        <label>Emphasis (frequency&rarr;size) <span class="val" id="v-power">1.0</span></label>
        <input type="range" id="power" min="0.3" max="3" step="0.1" value="1">
      </div>
      <div class="ctl">
        <label>Min count <span class="val" id="v-min">1</span></label>
        <input type="range" id="minCount" min="1" max="2" step="1" value="1">
      </div>
      <div class="ctl">
        <label>Max words <span class="val" id="v-max">200</span></label>
        <input type="range" id="maxWords" min="10" max="300" step="5" value="200">
      </div>
      <div class="ctl">
        <label>Font size range <span class="val" id="v-font">12&ndash;72</span></label>
        <input type="range" id="fontMin" min="8" max="48" step="1" value="12">
        <input type="range" id="fontMax" min="24" max="140" step="2" value="72">
      </div>
      <div class="btns">
        <button id="copyRemoved">Copy removed words</button>
        <button id="reset">Reset</button>
      </div>
    </div>
    <div class="wl">
      <h2>Words (<span id="wcount">0</span>)</h2>
      <input type="search" class="search" id="search" placeholder="Filter words&hellip;">
      <div class="rows" id="rows"></div>
      <div class="hint" id="removedHint"></div>
    </div>
  </aside>
</div>

<script id="data" type="application/json">__WORDS_JSON__</script>
<script>
(function () {
  "use strict";
  var RAW = JSON.parse(document.getElementById("data").textContent || "[]");
  // Model: each word carries its base count, a per-word multiplier, and a removed flag.
  var WORDS = RAW.map(function (p) {
    return { text: p[0], count: p[1], mult: 1, removed: false };
  });
  var MAXCOUNT = WORDS.reduce(function (m, w) { return Math.max(m, w.count); }, 1);

  var PALETTE = ["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed",
                 "#0891b2", "#be185d", "#4d7c0f", "#b45309", "#1e40af"];

  var els = {
    cv: document.getElementById("cv"),
    empty: document.getElementById("empty"),
    power: document.getElementById("power"),
    minCount: document.getElementById("minCount"),
    maxWords: document.getElementById("maxWords"),
    fontMin: document.getElementById("fontMin"),
    fontMax: document.getElementById("fontMax"),
    vPower: document.getElementById("v-power"),
    vMin: document.getElementById("v-min"),
    vMax: document.getElementById("v-max"),
    vFont: document.getElementById("v-font"),
    rows: document.getElementById("rows"),
    search: document.getElementById("search"),
    wcount: document.getElementById("wcount"),
    removedHint: document.getElementById("removedHint"),
    copyRemoved: document.getElementById("copyRemoved"),
    reset: document.getElementById("reset")
  };
  var ctx = els.cv.getContext("2d");

  // Slider bounds derived from the data.
  els.minCount.max = String(Math.max(2, MAXCOUNT));
  els.maxWords.max = String(Math.max(10, WORDS.length));
  els.maxWords.value = String(Math.min(200, Math.max(10, WORDS.length)));

  function active() { return WORDS.filter(function (w) { return !w.removed; }); }

  // Words that survive the min-count filter and the max-words cap, ranked by
  // effective weight (count * per-word multiplier), largest first.
  function selected() {
    var minC = +els.minCount.value;
    var cap = +els.maxWords.value;
    var list = active().filter(function (w) { return w.count >= minC; });
    list.sort(function (a, b) { return b.count * b.mult - a.count * a.mult; });
    return list.slice(0, cap);
  }

  function sizeFor(ew, lo, hi) {
    var fMin = +els.fontMin.value, fMax = Math.max(+els.fontMax.value, +els.fontMin.value + 4);
    var power = +els.power.value;
    var norm = hi > lo ? (ew - lo) / (hi - lo) : 1;
    return fMin + (fMax - fMin) * Math.pow(norm, power);
  }

  function fitCanvas() {
    var rect = els.cv.parentNode.getBoundingClientRect();
    var dpr = window.devicePixelRatio || 1;
    els.cv.width = Math.max(320, Math.floor(rect.width * dpr));
    els.cv.height = Math.max(320, Math.floor(rect.height * dpr));
  }

  function drawCloud() {
    fitCanvas();
    ctx.clearRect(0, 0, els.cv.width, els.cv.height);
    var words = selected();
    els.empty.style.display = words.length ? "none" : "flex";
    if (!words.length) return;

    var weights = words.map(function (w) { return w.count * w.mult; });
    var lo = Math.min.apply(null, weights), hi = Math.max.apply(null, weights);

    ctx.textBaseline = "middle";
    ctx.textAlign = "center";
    var cx = els.cv.width / 2, cy = els.cv.height / 2;
    var placed = [];
    words.forEach(function (w, i) {
      var size = sizeFor(w.count * w.mult, lo, hi) * (window.devicePixelRatio || 1);
      ctx.font = "bold " + size + "px system-ui, sans-serif";
      var halfW = ctx.measureText(w.text).width / 2 + 3;
      var halfH = size / 2 + 3;
      for (var t = 0; t < 4000; t++) {
        var r = 0.55 * t, a = 0.22 * t;
        var x = cx + r * Math.cos(a), y = cy + r * Math.sin(a);
        var box = { l: x - halfW, r: x + halfW, t: y - halfH, b: y + halfH };
        if (box.l < 0 || box.t < 0 || box.r > els.cv.width || box.b > els.cv.height) continue;
        var hit = false;
        for (var j = 0; j < placed.length; j++) {
          var p = placed[j];
          if (box.l < p.r && box.r > p.l && box.t < p.b && box.b > p.t) { hit = true; break; }
        }
        if (!hit) {
          ctx.fillStyle = PALETTE[i % PALETTE.length];
          ctx.fillText(w.text, x, y);
          placed.push(box);
          break;
        }
      }
    });
  }

  function drawList() {
    var q = els.search.value.trim().toLowerCase();
    var list = active().filter(function (w) { return !q || w.text.toLowerCase().indexOf(q) >= 0; });
    list.sort(function (a, b) { return b.count * b.mult - a.count * a.mult; });
    els.wcount.textContent = String(active().length);
    var frag = document.createDocumentFragment();
    list.forEach(function (w) {
      var row = document.createElement("div");
      row.className = "row";
      var name = document.createElement("span");
      name.className = "w"; name.textContent = w.text; name.title = w.text;
      var cnt = document.createElement("span");
      cnt.className = "c"; cnt.textContent = w.count;
      var mult = document.createElement("input");
      mult.className = "mult"; mult.type = "number"; mult.min = "0"; mult.step = "0.1";
      mult.value = String(w.mult); mult.title = "Per-word weight multiplier";
      mult.addEventListener("input", function () {
        var v = parseFloat(mult.value);
        w.mult = isNaN(v) || v < 0 ? 0 : v;
        drawCloud();
      });
      var rm = document.createElement("button");
      rm.className = "rm"; rm.textContent = "\\u00d7"; rm.title = "Remove word";
      rm.addEventListener("click", function () { w.removed = true; render(); });
      row.appendChild(name); row.appendChild(cnt); row.appendChild(mult); row.appendChild(rm);
      frag.appendChild(row);
    });
    els.rows.innerHTML = "";
    els.rows.appendChild(frag);
    var removed = WORDS.filter(function (w) { return w.removed; });
    els.removedHint.textContent = removed.length
      ? removed.length + " word(s) removed \\u2014 use 'Copy removed words' to reuse as stopwords."
      : "";
  }

  function syncLabels() {
    els.vPower.textContent = (+els.power.value).toFixed(1);
    els.vMin.textContent = els.minCount.value;
    els.vMax.textContent = els.maxWords.value;
    els.vFont.textContent = els.fontMin.value + "\\u2013" + els.fontMax.value;
  }

  function render() { syncLabels(); drawCloud(); drawList(); }

  ["power", "minCount", "maxWords", "fontMin", "fontMax"].forEach(function (k) {
    els[k].addEventListener("input", function () { syncLabels(); drawCloud(); });
  });
  els.search.addEventListener("input", drawList);

  els.copyRemoved.addEventListener("click", function () {
    var text = WORDS.filter(function (w) { return w.removed; })
                    .map(function (w) { return w.text; }).join("\\n");
    if (navigator.clipboard && text) {
      navigator.clipboard.writeText(text).then(function () {
        els.copyRemoved.textContent = "Copied!";
        setTimeout(function () { els.copyRemoved.textContent = "Copy removed words"; }, 1200);
      });
    } else {
      window.prompt("Removed words (copy):", text);
    }
  });

  els.reset.addEventListener("click", function () {
    WORDS.forEach(function (w) { w.removed = false; w.mult = 1; });
    els.power.value = "1";
    els.minCount.value = "1";
    els.maxWords.value = String(Math.min(200, Math.max(10, WORDS.length)));
    els.fontMin.value = "12";
    els.fontMax.value = "72";
    els.search.value = "";
    render();
  });

  window.addEventListener("resize", drawCloud);
  render();
})();
</script>
</body>
</html>
"""
