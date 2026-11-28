/* Five-commodity panels: commodity comparison, MSP comparison, district-wise analysis.
   Every panel fetches real API data; commodities without data are shown as "no data", never faked. */
(function (global) {
  "use strict";
  var M = (global.Mandi = global.Mandi || {});
  var U = M.utils, A = M.api, C = M.charts, P = M.panels, $ = U.$, el = U.el;

  /** Cross-commodity panels ignore the commodity filter; the other filters still apply. */
  function scope(f) { return { district: f.district, market: f.market, date_from: f.date_from, date_to: f.date_to }; }
  function td(text, cls, extra) { return el("td", Object.assign({ class: cls || null, text: text }, extra || {})); }
  function pctCell(v) {
    if (v === null || v === undefined) return td("n/a", "num zero");
    var cls = v > 0 ? "pos" : v < 0 ? "neg" : "zero";
    return td(U.fmtPct(v), "num " + cls);
  }
  function seg(host, onPick) {
    host.addEventListener("click", function (ev) {
      var b = ev.target.closest("button[data-v]");
      if (!b) return;
      [].forEach.call(host.children, function (c) { c.classList.toggle("active", c === b); });
      onPick(b.dataset.v);
    });
  }

  /* ------------------------------------------------------- commodity comparison */
  function CommodityPanel(root, canvas, onSelect) {
    var p = P.Panel(root), loadCmp = A.createLoader(), loadHist = A.createLoader();
    var chart = null, cmp = null, hist = null, lastF = null, view = "latest", showMsp = false, selected = null;

    function table() {
      var body = $("#cmpBody"), rows = cmp ? cmp.rows : [];
      body.replaceChildren.apply(body, rows.map(function (r, i) {
        var name = el("td", null, [el("span", { class: "swatch c" + i }), r.label,
          r.has_data && r.days_behind_newest > 0 ? el("span", { class: "tag", text: r.days_behind_newest + "d older" }) : null]);
        if (!r.has_data) {
          return el("tr", { class: "nodata" }, [name, el("td", { colspan: "8", text: r.reason || "No data available" })]);
        }
        var m = r.msp || {};
        return el("tr", { class: "clickable" + (r.commodity === selected ? " sel" : ""), tabindex: "0",
                          title: "Click to select " + r.label,
                          onclick: function () { onSelect(r.commodity); },
                          onkeydown: function (e) { if (e.key === "Enter") onSelect(r.commodity); } }, [
          name, td(U.fmtDate(r.date)), td(U.fmtPrice(r.avg_modal), "num"), td(U.fmtPrice(r.min_price), "num"),
          td(U.fmtPrice(r.max_price), "num"),
          pctCell(r.change_vs_previous ? r.change_vs_previous.pct_change : null),
          td(m.available ? U.fmtPrice(m.msp) : "n/a", "num"),
          m.available && m.pct !== null && m.pct !== undefined ? pctCell(m.pct) : td("n/a", "num zero"),
          td(U.fmtNum(r.markets_reporting), "num"),
        ]);
      }));
    }

    function render() {
      p.clear();
      chart = C.destroy(chart);
      var sub = $("#cmpSub"), note = $("#cmpNote");
      $("#cmpMspWrap").hidden = view !== "price";
      if (!cmp) { sub.textContent = ""; note.textContent = ""; table(); return; }
      var avail = cmp.rows.filter(function (r) { return r.has_data; });
      var missing = cmp.rows.filter(function (r) { return !r.has_data; }).map(function (r) { return r.label; });
      note.textContent = cmp.note || "";
      if (!avail.length) { sub.textContent = ""; p.warn("No price data for any commodity with these filters."); table(); return; }
      if (missing.length) p.warn("No data available for: " + missing.join(", ") + ".");
      table();
      if (view === "latest") {
        sub.textContent = "Latest average modal price vs MSP, each commodity on its own latest date (newest: " + U.fmtDate(cmp.newest_date) + "). Click a bar to select.";
        chart = C.commodityLatest(canvas, null, { rows: cmp.rows, selected: selected, onSelect: function (r) { if (r.has_data) onSelect(r.commodity); } });
      } else if (!hist) {
        sub.textContent = "Loading history…";
      } else if (!hist.dates.length) {
        sub.textContent = ""; p.warn("No history for these filters.");
      } else {
        sub.textContent = view === "index" ? "Prices rebased to 100 on each commodity’s first date, so commodities with different price levels can be compared."
                                           : "Daily average modal price (₹ per quintal). Averages can move when fewer markets report.";
        chart = C.commodityHistory(canvas, null, { series: hist.series, dates: hist.dates, mode: view, showMsp: showMsp });
      }
    }

    async function loadHistory() {
      if (!lastF || view === "latest") return;
      p.loading(true);
      try {
        hist = await loadHist(function (signal) { return A.get("/api/compare/trends", scope(lastF), { signal: signal }); });
        render(); p.loading(false);
      } catch (e) {
        if (e.stale) return;
        p.loading(false); hist = null; p.error(e.message, loadHistory);
      }
    }

    async function load(f) {
      lastF = f; selected = f.commodity; hist = null;
      p.loading(true);
      try {
        cmp = await loadCmp(function (signal) { return A.get("/api/compare/commodities", scope(f), { signal: signal }); });
        render(); p.loading(false);
        if (view !== "latest") loadHistory();
      } catch (e) {
        if (e.stale) return;
        p.loading(false); cmp = null; chart = C.destroy(chart); render();
        p.error(e.message, function () { load(lastF); });
      }
    }

    seg($("#cmpView"), function (v) { view = v; if (v !== "latest" && !hist) { render(); loadHistory(); } else render(); });
    $("#cmpMsp").addEventListener("change", function () { showMsp = this.checked; render(); });
    return { load: load, render: render, root: root };
  }

  /* ------------------------------------------------------------ MSP comparison */
  function MspPanel(root, canvas, breakRoot, onSelect) {
    var p = P.Panel(root), pb = P.Panel(breakRoot), loadO = A.createLoader(), loadB = A.createLoader();
    var chart = null, over = null, brk = null, lastF = null, level = "market";

    function renderBreak() {
      pb.clear();
      var body = $("#mspBreakBody"), sub = $("#mspBreakSub");
      body.replaceChildren();
      if (!brk) { sub.textContent = ""; return; }
      $("#mspBreakTitle").textContent = "Below / above MSP — " + lastF.commodity;
      if (!brk.rows.length) { sub.textContent = ""; pb.warn("No prices for " + lastF.commodity + " with these filters."); return; }
      if (!brk.msp) {
        sub.textContent = U.fmtDate(brk.date);
        pb.warn("MSP is not available for " + lastF.commodity + " on " + U.fmtDate(brk.date) + ", so no comparison can be made.");
      } else {
        sub.textContent = U.fmtDate(brk.date) + " · MSP " + U.fmtPrice(brk.msp.msp) + " (" + brk.msp.season + ") · " +
          brk.below_count + " of " + brk.total + " " + level + "(s) below MSP · most below first";
      }
      body.replaceChildren.apply(body, brk.rows.map(function (r) {
        var name = level === "market" ? r.market + " (" + r.district + ")" : r.district;
        return el("tr", { class: r.status === "below" ? "" : null }, [
          td(name), td(U.fmtPrice(r.avg_modal), "num"), td(r.msp != null ? U.fmtPrice(r.msp) : "n/a", "num"),
          td(r.gap != null ? (r.gap > 0 ? "+" : r.gap < 0 ? "−" : "") + U.fmtPrice(Math.abs(r.gap)) : "n/a", "num " + (r.gap > 0 ? "pos" : r.gap < 0 ? "neg" : "zero")),
          pctCell(r.pct)]);
      }));
    }

    function renderOverview() {
      p.clear();
      chart = C.destroy(chart);
      var sub = $("#mspSub"), note = $("#mspNote");
      if (!over) { sub.textContent = ""; note.textContent = ""; return; }
      note.textContent = over.note || "";
      var comparable = over.rows.filter(function (r) { return r.pct !== null && r.pct !== undefined; });
      var na = over.rows.filter(function (r) { return r.pct === null || r.pct === undefined; }).map(function (r) { return r.label; });
      if (!comparable.length) { sub.textContent = ""; p.warn("No commodity has both price data and an MSP for these filters."); return; }
      sub.textContent = "Average modal price against the MSP of the marketing season each price date falls in.";
      if (na.length) p.warn("Not comparable (no data or no MSP on record): " + na.join(", ") + ".");
      chart = C.mspGap(canvas, null, { rows: over.rows, onSelect: function (r) { if (r.has_data) onSelect(r.commodity); } });
    }

    async function loadBreak() {
      if (!lastF) return;
      pb.loading(true);
      try {
        brk = await loadB(function (signal) {
          return A.get("/api/msp/breakdown", Object.assign({ commodity: lastF.commodity, level: level }, scope(lastF)), { signal: signal });
        });
        renderBreak(); pb.loading(false);
      } catch (e) {
        if (e.stale) return;
        pb.loading(false); brk = null; renderBreak(); pb.error(e.message, loadBreak);
      }
    }

    async function load(f) {
      lastF = f;
      p.loading(true);
      loadBreak();
      try {
        over = await loadO(function (signal) { return A.get("/api/msp", scope(f), { signal: signal }); });
        renderOverview(); p.loading(false);
      } catch (e) {
        if (e.stale) return;
        p.loading(false); over = null; renderOverview(); p.error(e.message, function () { load(lastF); });
      }
    }

    seg($("#mspLevel"), function (v) { level = v; loadBreak(); });
    return { load: load, render: renderOverview, root: root };
  }

  /* ------------------------------------------------------- district analysis */
  function DistrictPanel(root, canvas, onSelect) {
    var p = P.Panel(root), loadD = A.createLoader(), loadM = A.createLoader();
    var chart = null, dist = null, matrix = null, lastF = null, view = "selected";

    function renderSelected() {
      chart = C.destroy(chart);
      var body = $("#distBody"), sub = $("#distSub");
      body.replaceChildren();
      if (!dist) { sub.textContent = ""; return; }
      $("#distTitle").textContent = "District-wise analysis — " + lastF.commodity;
      if (!dist.rows.length) { sub.textContent = ""; p.warn("No prices for " + lastF.commodity + " with these filters."); return; }
      sub.textContent = U.fmtDate(dist.date) + " · state average " + U.fmtPrice(dist.state_average_modal) + " · " +
        (dist.msp ? "MSP " + U.fmtPrice(dist.msp.msp) + " (" + dist.msp.season + "), dashed line; red bars are below MSP" : "MSP not available for this date");
      chart = C.districtBars(canvas, null, { rows: dist.rows, msp: dist.msp ? dist.msp.msp : null,
                                             onSelect: function (r) { onSelect(r.district); } });
      body.replaceChildren.apply(body, dist.rows.map(function (r) {
        return el("tr", { class: "clickable", tabindex: "0", title: "Click to filter to " + r.district,
                          onclick: function () { onSelect(r.district); },
                          onkeydown: function (e) { if (e.key === "Enter") onSelect(r.district); } }, [
          td(r.district), td(U.fmtPrice(r.avg_modal), "num"), td(U.fmtPrice(r.min_price), "num"), td(U.fmtPrice(r.max_price), "num"),
          pctCell(r.vs_state_avg_pct), pctCell(r.msp_pct), td(U.fmtNum(r.markets), "num"),
          td(r.markets_below_msp == null ? "n/a" : r.markets_below_msp + " / " + r.markets, "num")]);
      }));
    }

    function renderMatrix() {
      var head = $("#matrixHead"), body = $("#matrixBody"), sub = $("#distSub");
      head.replaceChildren(); body.replaceChildren();
      if (!matrix) { sub.textContent = ""; return; }
      $("#distTitle").textContent = "District-wise analysis — all commodities";
      sub.textContent = "Average modal price (₹ per quintal) by district; a dash means that district has no data for that commodity.";
      if (!matrix.rows.length) { p.warn("No prices for these filters."); return; }
      var missing = matrix.commodities.filter(function (c) { return !c.newest_date; }).map(function (c) { return c.label; });
      if (missing.length) p.warn("No data available for: " + missing.join(", ") + ".");
      head.appendChild(el("tr", null, [el("th", { text: "District" })].concat(matrix.commodities.map(function (c, i) {
        return el("th", { class: "num" }, [el("span", { class: "swatch c" + i }), c.label]);
      }))));
      body.replaceChildren.apply(body, matrix.rows.map(function (r) {
        return el("tr", { class: "clickable", onclick: function () { onSelect(r.district); } },
          [td(r.district)].concat(matrix.commodities.map(function (c) {
            var v = r.values[c.name];
            if (!v || v.avg_modal === null) return td("—", "num zero");
            var cell = td(U.fmtPrice(v.avg_modal), "num");
            if (!v.is_latest_date) cell.appendChild(el("span", { class: "tag", text: U.shortDate(v.date) }));
            return cell;
          })));
      }));
    }

    function render() {
      p.clear();
      $("#distSelected").hidden = view !== "selected";
      $("#distMatrix").hidden = view !== "matrix";
      if (view === "selected") renderSelected(); else renderMatrix();
    }

    async function load(f) {
      lastF = f;
      p.loading(true);
      try {
        if (view === "selected") {
          dist = await loadD(function (signal) { return A.get("/api/districts/analysis", Object.assign({ commodity: f.commodity }, scope(f)), { signal: signal }); });
        } else {
          matrix = await loadM(function (signal) { return A.get("/api/districts/matrix", scope(f), { signal: signal }); });
        }
        render(); p.loading(false);
      } catch (e) {
        if (e.stale) return;
        p.loading(false); chart = C.destroy(chart); p.error(e.message, function () { load(lastF); });
      }
    }

    seg($("#distView"), function (v) { view = v; if (lastF) load(lastF); });
    return { load: load, render: render, root: root };
  }

  M.analysis = { CommodityPanel: CommodityPanel, MspPanel: MspPanel, DistrictPanel: DistrictPanel };
})(window);
