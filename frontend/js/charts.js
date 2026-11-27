/* Chart.js wrappers. Colours come from CSS variables so light/dark themes both work. */
(function (global) {
  "use strict";
  var M = (global.Mandi = global.Mandi || {});
  var U = M.utils;
  var reduceMotion = global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function palette() { return [css("--c1"), css("--c2"), css("--c3"), css("--c4"), css("--c5")]; }
  function alpha(color, a) {
    var m = /^#([0-9a-f]{6})$/i.exec(color);
    if (!m) return color;
    var n = parseInt(m[1], 16);
    return "rgba(" + (n >> 16) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")";
  }
  function inr(v) { return Number(v).toLocaleString("en-IN"); }

  function base() {
    var text = css("--text"), muted = css("--muted"), grid = css("--grid");
    return {
      text: text, muted: muted, grid: grid,
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: reduceMotion ? false : { duration: 350 },
        color: text,
        plugins: { legend: { labels: { color: text, usePointStyle: true, boxWidth: 8 } } },
      },
    };
  }

  function destroy(chart) { if (chart) chart.destroy(); return null; }

  /* ------------------------------------------------------------------ trend */
  function trend(canvas, old, cfg) {
    destroy(old);
    var b = base(), pal = palette(), series = cfg.series;
    var dates = [];
    series.forEach(function (s) { s.points.forEach(function (p) { if (dates.indexOf(p.date) < 0) dates.push(p.date); }); });
    dates.sort();

    var datasets, meta = {};
    if (cfg.groupBy === "none") {
      var pts = {};
      series[0].points.forEach(function (p) { pts[p.date] = p; meta[p.date] = p.markets_reporting; });
      var pick = function (key) { return dates.map(function (d) { return pts[d] ? pts[d][key] : null; }); };
      datasets = [{ label: "Avg modal", data: pick("avg_modal"), borderColor: pal[0], backgroundColor: alpha(pal[0], 0.15),
                    borderWidth: 3, pointRadius: 4, pointHoverRadius: 6, tension: 0.25, fill: false }];
      if (cfg.showRange) {
        datasets.push({ label: "Lowest min", data: pick("min_price"), borderColor: pal[2], borderDash: [6, 4], borderWidth: 2, pointRadius: 2, tension: 0.25 });
        datasets.push({ label: "Highest max", data: pick("max_price"), borderColor: pal[4], borderDash: [6, 4], borderWidth: 2, pointRadius: 2, tension: 0.25 });
      }
    } else {
      datasets = series.map(function (s, i) {
        var map = {};
        s.points.forEach(function (p) { map[p.date] = p.avg_modal; });
        return { label: s.name, data: dates.map(function (d) { return d in map ? map[d] : null; }),
                 borderColor: pal[i % pal.length], backgroundColor: pal[i % pal.length],
                 borderWidth: 2.5, pointRadius: 3, tension: 0.25, spanGaps: true };
      });
    }

    var opts = b.options;
    opts.interaction = { mode: "index", intersect: false };
    opts.scales = {
      x: { ticks: { color: b.muted, maxRotation: 0, autoSkip: true, callback: function (v) { return U.shortDate(this.getLabelForValue(v)); } }, grid: { display: false } },
      y: { grace: "5%", ticks: { color: b.muted, callback: function (v) { return inr(v); } }, grid: { color: b.grid },
           title: { display: true, text: "₹ per quintal", color: b.muted } },
    };
    opts.plugins.tooltip = { callbacks: {
      title: function (items) { return U.fmtDate(items[0].label); },
      label: function (c) { return c.dataset.label + ": " + U.fmtPrice(c.parsed.y); },
      afterBody: function (items) {
        var n = meta[items[0].label];
        return n != null ? n + " market(s) reporting" : "";
      },
    } };
    canvas.setAttribute("aria-label", "Price trend for " + cfg.commodity + ": " + dates.length + " dates");
    return new Chart(canvas, { type: "line", data: { labels: dates, datasets: datasets }, options: opts });
  }

  /* ---------------------------------------------------------------- compare */
  var valueLabels = {
    id: "valueLabels",
    afterDatasetsDraw: function (chart, args, o) {
      if (!o || !o.enabled) return;
      var ctx = chart.ctx, meta = chart.getDatasetMeta(0);
      ctx.save(); ctx.fillStyle = o.color; ctx.font = "12px " + getComputedStyle(document.body).fontFamily;
      ctx.textBaseline = "middle";
      meta.data.forEach(function (bar, i) {
        var v = chart.data.datasets[0].data[i];
        if (v == null) return;
        ctx.fillText(U.fmtPrice(v), bar.x + 6, bar.y);
      });
      ctx.restore();
    },
  };
  var modalMarkers = {
    id: "modalMarkers",
    afterDatasetsDraw: function (chart, args, o) {
      if (!o || !o.values) return;
      var meta = chart.getDatasetMeta(0), xs = chart.scales.x, ctx = chart.ctx;
      ctx.save(); ctx.fillStyle = o.color;
      meta.data.forEach(function (bar, i) {
        var v = o.values[i];
        if (v == null) return;
        var x = xs.getPixelForValue(v), h = Math.max(bar.height || 12, 10);
        ctx.fillRect(x - 1.5, bar.y - h / 2 - 2, 3, h + 4);
      });
      ctx.restore();
    },
  };

  function compare(canvas, old, cfg) {
    destroy(old);
    var b = base(), pal = palette(), rows = cfg.rows;
    var labels = rows.map(function (r) { return cfg.level === "market" ? r.market : r.district; });
    var opts = b.options, dataset, plugins = {};
    opts.indexAxis = "y";
    opts.layout = { padding: { right: cfg.view === "modal" ? 64 : 8 } };

    if (cfg.view === "modal") {
      dataset = { label: "Avg modal price", data: rows.map(function (r) { return r.avg_modal; }),
        backgroundColor: rows.map(function (r) { return (r.diff_vs_avg_pct || 0) >= 0 ? pal[0] : pal[1]; }),
        borderRadius: 4, maxBarThickness: 22 };
      plugins.valueLabels = { enabled: true, color: b.text };
      opts.scales = { x: { beginAtZero: true, ticks: { color: b.muted, callback: inr }, grid: { color: b.grid } },
                      y: { ticks: { color: b.text }, grid: { display: false } } };
    } else {
      dataset = { label: "Min to max", data: rows.map(function (r) { return [r.min_price, r.max_price]; }),
        backgroundColor: alpha(pal[2], 0.55), borderColor: pal[2], borderWidth: 1, borderRadius: 4,
        borderSkipped: false, maxBarThickness: 22 };
      plugins.modalMarkers = { values: rows.map(function (r) { return r.avg_modal; }), color: pal[1] };
      var lows = rows.map(function (r) { return r.min_price; }).filter(function (v) { return v != null; });
      var highs = rows.map(function (r) { return r.max_price; }).filter(function (v) { return v != null; });
      var lo = lows.length ? Math.min.apply(null, lows) : 0, hi = highs.length ? Math.max.apply(null, highs) : 0;
      var pad = Math.max((hi - lo) * 0.08, 20);
      opts.scales = { x: { min: Math.floor((lo - pad) / 10) * 10, max: Math.ceil((hi + pad) / 10) * 10,
                           ticks: { color: b.muted, callback: inr }, grid: { color: b.grid } },
                      y: { ticks: { color: b.text }, grid: { display: false } } };
    }

    opts.plugins.legend = { display: false };
    opts.plugins.valueLabels = plugins.valueLabels || { enabled: false };
    opts.plugins.modalMarkers = plugins.modalMarkers || false;
    opts.plugins.tooltip = { callbacks: {
      title: function (items) { return items[0].label; },
      label: function (c) {
        var r = rows[c.dataIndex], out = [];
        if (r.market && r.district) out.push("District: " + r.district);
        out.push("Avg modal: " + U.fmtPrice(r.avg_modal));
        out.push("Min " + U.fmtPrice(r.min_price) + " · Max " + U.fmtPrice(r.max_price));
        out.push("Spread: " + U.fmtPrice(r.spread));
        out.push("vs day average: " + U.fmtPct(r.diff_vs_avg_pct));
        out.push("Records: " + r.records);
        return out;
      },
    } };
    opts.onClick = function (evt, els) { if (els.length && cfg.onSelect) cfg.onSelect(rows[els[0].index]); };
    opts.onHover = function (evt, els) { evt.native.target.style.cursor = els.length ? "pointer" : "default"; };
    canvas.setAttribute("aria-label", "Comparison of " + rows.length + " " + cfg.level + "s");
    return new Chart(canvas, { type: "bar", data: { labels: labels, datasets: [dataset] }, options: opts,
                               plugins: [valueLabels, modalMarkers] });
  }

  M.charts = { trend: trend, compare: compare, destroy: destroy };
})(window);
