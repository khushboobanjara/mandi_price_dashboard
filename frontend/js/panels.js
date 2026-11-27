/* Dashboard panels. Each panel fetches its own real API data and can re-render from cache. */
(function (global) {
  "use strict";
  var M = (global.Mandi = global.Mandi || {});
  var U = M.utils, A = M.api, C = M.charts, $ = U.$, el = U.el;

  /** Shared loading + error handling for a panel root element. */
  function Panel(root) {
    var msg = $('[data-role="msg"]', root);
    return {
      root: root,
      loading: function (on) { root.classList.toggle("is-loading", !!on); root.setAttribute("aria-busy", on ? "true" : "false"); },
      clear: function () { if (msg) msg.replaceChildren(); },
      error: function (text, retry) {
        if (!msg) return;
        msg.replaceChildren(el("div", { class: "msg error", role: "alert" }, [
          el("span", { text: "⚠ " + text }),
          retry ? el("button", { class: "btn small", type: "button", text: "Retry", onclick: retry }) : null,
        ]));
      },
      warn: function (text) { if (msg) msg.appendChild(el("div", { class: "msg warn", text: text })); },
    };
  }

  /* -------------------------------------------------------------------- KPI */
  function KpiPanel(host, noteHost, actions) {
    var load = A.createLoader(), last = null;

    function delta(change, label) {
      if (!change) return null;
      if (change.pct_change === null || change.pct_change === undefined)
        return el("div", { class: "delta flat", text: label + ": n/a (no common markets)" });
      var cls = change.pct_change > 0 ? "up" : change.pct_change < 0 ? "down" : "flat";
      var n = change.markets_compared;
      return el("div", { class: "delta " + cls, title: "Compares only markets that reported on both dates" },
        [U.fmtPct(change.pct_change) + " " + label, el("span", { class: "muted", text: " (" + n + " market" + (n === 1 ? "" : "s") + ")" })]);
    }

    function card(label, value, sub, extra, action, hint, isText) {
      var inner = [el("div", { class: "kpi-label", text: label }),
        el("div", { class: "kpi-value" + (isText ? " text" : ""), text: String(value) }),
        sub ? el("div", { class: "kpi-sub", text: sub }) : null].concat(extra || []);
      if (action) {
        inner.push(el("div", { class: "kpi-hint", text: hint }));
        return el("button", { class: "card kpi", type: "button", onclick: action, "aria-label": label + ": " + value + ". " + hint }, inner);
      }
      return el("div", { class: "card kpi" }, inner);
    }

    function skeleton() {
      host.replaceChildren.apply(host, [1, 2, 3, 4, 5, 6].map(function () {
        return el("div", { class: "card kpi skeleton" }, [el("div", { class: "kpi-label", text: "." }),
          el("div", { class: "kpi-value", text: "." }), el("div", { class: "kpi-sub", text: "." })]);
      }));
    }

    function render() {
      if (!last) return;
      var k = last.k, s = k.summary;
      noteHost.textContent = last.note || "";
      if (!k.has_data) {
        host.replaceChildren(el("div", { class: "card empty", text: "No prices found for these filters." }));
        return;
      }
      var hi = s.highest_modal_market, lo = s.lowest_modal_market;
      var cards = [
        card("Avg modal price", U.fmtPrice(s.avg_modal), "as of " + U.fmtDate(k.latest_date),
          [delta(k.change_vs_previous, "vs " + U.fmtDate(k.previous_date)),
           delta(k.change_vs_week, k.week_compare_date ? "vs " + U.fmtDate(k.week_compare_date) : "vs a week ago")],
          actions.toTrend, "Click to view trend"),
        card("Lowest min price", U.fmtPrice(s.min_price), "across reporting markets", null, actions.lowestMin, "Click to list lowest prices"),
        card("Highest max price", U.fmtPrice(s.max_price), "across reporting markets", null, actions.highestMax, "Click to list highest prices"),
        card("Markets reporting", U.fmtNum(s.markets_reporting), U.fmtNum(s.records) + " records", null, actions.toCompare, "Click to compare markets"),
        card("Highest modal market", hi ? hi.market : "—", hi ? U.fmtPrice(hi.price) : "", null,
          hi ? function () { actions.filterMarket(hi.market); } : null, "Click to filter to this market", true),
        card("Lowest modal market", lo ? lo.market : "—", lo ? U.fmtPrice(lo.price) : "", null,
          lo ? function () { actions.filterMarket(lo.market); } : null, "Click to filter to this market", true),
      ];
      host.replaceChildren.apply(host, cards);
      if (s.missing_price_rows > 0)
        noteHost.textContent = s.missing_price_rows + " record(s) have a missing min, max or modal price. " + (last.note || "");
    }

    return {
      render: render,
      async load(f) {
        host.setAttribute("aria-busy", "true");
        if (!last) skeleton();
        try {
          var data = await load(function (signal) { return A.get("/api/kpis", f, { signal: signal }); });
          last = { k: data.commodities[f.commodity] || { has_data: false }, note: data.note };
          render();
        } catch (e) {
          if (e.stale) return;
          host.replaceChildren(el("div", { class: "msg error", role: "alert" }, [
            el("span", { text: "⚠ Could not load indicators: " + e.message }),
            el("button", { class: "btn small", type: "button", text: "Retry", onclick: function () { actions.retry(); } }),
          ]));
        } finally { host.setAttribute("aria-busy", "false"); }
      },
    };
  }

  /* ------------------------------------------------------------------ trend */
  function TrendPanel(root, canvas) {
    var p = Panel(root), load = A.createLoader(), chart = null, data = null, lastF = null;
    var groupBy = "none", showRange = $("#trendRange").checked;

    function render() {
      p.clear();
      chart = C.destroy(chart);
      if (!data) return;
      var rows = data.series.length ? data.series[0].points : [];
      if (!data.series.length || !rows.length) {
        p.warn("No data for these filters.");
        return;
      }
      if (groupBy === "none" && rows.length > 1) {
        var latest = rows[rows.length - 1];
        var peak = Math.max.apply(null, rows.map(function (r) { return r.markets_reporting; }));
        if (latest.markets_reporting < peak * 0.5)
          p.warn("Only " + latest.markets_reporting + " market(s) have reported for " + U.fmtDate(latest.date) +
                 " so far (up to " + peak + " on earlier days), so the latest average may not be comparable.");
      }
      chart = C.trend(canvas, null, { series: data.series, groupBy: groupBy, showRange: showRange, commodity: data.commodity });
    }

    async function doLoad(f) {
      lastF = f;
      $("#trendTitle").textContent = "Price trend — " + f.commodity;
      p.loading(true);
      try {
        data = await load(function (signal) {
          return A.get("/api/trends", Object.assign({}, f, { group_by: groupBy, top: 5 }), { signal: signal });
        });
        render();
        p.loading(false);
      } catch (e) {
        if (e.stale) return;
        p.loading(false); chart = C.destroy(chart); data = null;
        p.error(e.message, function () { doLoad(lastF); });
      }
    }

    $("#trendGroup").addEventListener("click", function (ev) {
      var b = ev.target.closest("button[data-v]");
      if (!b) return;
      groupBy = b.dataset.v;
      [].forEach.call(this.children, function (c) { c.classList.toggle("active", c === b); });
      $("#rangeToggleWrap").style.display = groupBy === "none" ? "" : "none";
      if (lastF) doLoad(lastF);
    });
    $("#trendRange").addEventListener("change", function () { showRange = this.checked; render(); });

    return { load: doLoad, render: render, root: root };
  }

  /* ---------------------------------------------------------------- compare */
  function ComparePanel(root, canvas, onSelect) {
    var p = Panel(root), load = A.createLoader(), chart = null, data = null, lastF = null;
    var level = "market", view = "modal";

    function render() {
      p.clear();
      chart = C.destroy(chart);
      var sub = $("#cSub");
      if (!data) { sub.textContent = ""; return; }
      var f = lastF;
      $("#compareTitle").textContent = (level === "market" ? "Market" : "District") + " comparison — " + data.commodity;
      if (!data.rows.length) {
        sub.textContent = "";
        p.warn("No prices on this date for these filters.");
        return;
      }
      sub.textContent = U.fmtDate(data.date) + " · average modal " + U.fmtPrice(data.average_modal) + " · top " + data.rows.length +
        " by modal price" + (view === "modal" ? " · blue/green = at or above average, amber = below" : " · marker = avg modal");
      $("#cHint").textContent = "Click a bar to filter the dashboard to that " + level + ".";
      chart = C.compare(canvas, null, { rows: data.rows, level: level, view: view, onSelect: function (r) { onSelect(level, r); } });
    }

    async function doLoad(f) {
      lastF = f;
      p.loading(true);
      var params = { commodity: f.commodity, district: f.district, market: f.market, level: level,
                     date: $("#cDate").value, limit: $("#cLimit").value };
      try {
        data = await load(function (signal) { return A.get("/api/markets/compare", params, { signal: signal }); });
        render();
        p.loading(false);
      } catch (e) {
        if (e.stale) return;
        p.loading(false); chart = C.destroy(chart); data = null; $("#cSub").textContent = "";
        p.error(e.message, function () { doLoad(lastF); });
      }
    }

    function seg(id, setter, reload) {
      $(id).addEventListener("click", function (ev) {
        var b = ev.target.closest("button[data-v]");
        if (!b) return;
        setter(b.dataset.v);
        [].forEach.call(this.children, function (c) { c.classList.toggle("active", c === b); });
        if (reload) { if (lastF) doLoad(lastF); } else render();
      });
    }
    seg("#cLevel", function (v) { level = v; }, true);
    seg("#cView", function (v) { view = v; }, false);
    $("#cDate").addEventListener("change", function () { if (lastF) doLoad(lastF); });
    $("#cLimit").addEventListener("change", function () { if (lastF) doLoad(lastF); });

    return {
      load: doLoad, render: render, root: root,
      setDateBounds: function (r) {
        var d = $("#cDate");
        d.min = (r && r.min) || ""; d.max = (r && r.max) || "";
      },
      setLevel: function (v) { $('#cLevel button[data-v="' + v + '"]').click(); },
    };
  }

  /* ------------------------------------------------------------------ table */
  var COLUMNS = [
    ["date", "Date", true, false], ["district", "District", true, false], ["market", "Market", true, false],
    ["variety", "Variety", false, false], ["grade", "Grade", false, false],
    ["min_price", "Min", true, true], ["max_price", "Max", true, true], ["modal_price", "Modal", true, true],
  ];

  function TablePanel(root) {
    var p = Panel(root), load = A.createLoader(), lastF = null;
    var s = { sortBy: "date", order: "desc", page: 1, size: 25 };
    var head = $("#tHead"), body = $("#tBody"), pager = $("#pager"), count = $("#tCount");

    function renderHead() {
      head.replaceChildren.apply(head, COLUMNS.map(function (c) {
        var active = s.sortBy === c[0];
        var th = el("th", { class: (c[3] ? "num " : "") + (c[2] ? "sortable" : ""), scope: "col",
          "aria-sort": c[2] ? (active ? (s.order === "asc" ? "ascending" : "descending") : "none") : null });
        if (!c[2]) { th.textContent = c[1]; return th; }
        th.appendChild(el("button", { class: "th-btn", type: "button",
          onclick: function () { sortBy(c[0]); } }, [c[1], el("span", { class: "arrow", text: active ? (s.order === "asc" ? " ▲" : " ▼") : "" })]));
        return th;
      }));
    }

    function sortBy(key, order) {
      if (order) { s.sortBy = key; s.order = order; }
      else if (key === s.sortBy) s.order = s.order === "asc" ? "desc" : "asc";
      else { s.sortBy = key; s.order = key.indexOf("price") >= 0 ? "desc" : "asc"; }
      s.page = 1;
      if (lastF) doLoad(lastF);
    }

    function rangeBar(r) {
      if (r.min_price == null || r.max_price == null || r.modal_price == null) return null;
      var span = r.max_price - r.min_price;
      var pos = span > 0 ? Math.min(100, Math.max(0, (r.modal_price - r.min_price) / span * 100)) : 50;
      var bar = el("span", { class: "rangebar", title: "Modal position between min and max" }, [el("i")]);
      bar.firstChild.style.left = "calc(" + pos + "% - 1.5px)";
      return bar;
    }

    function renderPager(d) {
      pager.replaceChildren();
      if (!d || d.pages <= 1) return;
      var go = function (n) { return function () { s.page = n; doLoad(lastF); }; };
      pager.append(
        el("button", { class: "btn small", type: "button", text: "« First", disabled: d.page <= 1, onclick: go(1) }),
        el("button", { class: "btn small", type: "button", text: "← Prev", disabled: d.page <= 1, onclick: go(d.page - 1) }),
        el("span", { text: "Page " + d.page + " of " + U.fmtNum(d.pages) }),
        el("button", { class: "btn small", type: "button", text: "Next →", disabled: d.page >= d.pages, onclick: go(d.page + 1) }),
        el("button", { class: "btn small", type: "button", text: "Last »", disabled: d.page >= d.pages, onclick: go(d.pages) }));
    }

    function renderRows(d) {
      count.textContent = U.fmtNum(d.total) + " record" + (d.total === 1 ? "" : "s");
      body.replaceChildren.apply(body, d.items.map(function (r) {
        return el("tr", null, [
          el("td", { text: U.fmtDate(r.date) }), el("td", { text: r.district }), el("td", { text: r.market }),
          el("td", { text: r.variety }), el("td", { text: r.grade }),
          el("td", { class: "num", text: U.fmtPrice(r.min_price) }), el("td", { class: "num", text: U.fmtPrice(r.max_price) }),
          el("td", { class: "num" }, [U.fmtPrice(r.modal_price), rangeBar(r)]),
        ]);
      }));
      if (!d.items.length) body.replaceChildren(el("tr", null, [el("td", { colspan: "8", class: "empty", text: "No records for these filters." })]));
      renderPager(d);
    }

    async function doLoad(f) {
      lastF = f;
      renderHead();
      p.loading(true); p.clear();
      try {
        var d = await load(function (signal) {
          return A.get("/api/prices", Object.assign({}, f, { sort_by: s.sortBy, order: s.order, page: s.page, page_size: s.size }), { signal: signal });
        });
        if (d.pages && s.page > d.pages) { s.page = d.pages; return doLoad(f); }
        renderRows(d);
        p.loading(false);
      } catch (e) {
        if (e.stale) return;
        p.loading(false);
        p.error(e.message, function () { doLoad(lastF); });
      }
    }

    $("#tSize").addEventListener("change", function () { s.size = Number(this.value); s.page = 1; if (lastF) doLoad(lastF); });
    return { load: doLoad, render: function () {}, root: root, resetPage: function () { s.page = 1; }, sortBy: sortBy };
  }

  /* ------------------------------------------------------------------- logs */
  function LogsPanel(box) {
    var p = Panel(box), load = A.createLoader(), body = $("#logsBody");
    async function doLoad() {
      p.clear();
      try {
        var rows = await load(function (signal) { return A.get("/api/fetch-logs", { limit: 10 }, { signal: signal }); });
        body.replaceChildren.apply(body, rows.map(function (r) {
          return el("tr", null, [
            el("td", { text: U.fmtDateTime(r.started_at) }), el("td", { text: r.trigger }),
            el("td", null, [el("span", { class: "pill " + r.status, text: r.status })]),
            el("td", { class: "num", text: U.fmtNum(r.records_fetched) }), el("td", { class: "num", text: U.fmtNum(r.records_inserted) }),
            el("td", { class: "num", text: U.fmtNum(r.records_updated) }), el("td", { class: "num", text: U.fmtNum(r.records_rejected) }),
            el("td", { text: (r.error_message || "").split("\n")[0].slice(0, 90), title: r.error_message || null }),
          ]);
        }));
        if (!rows.length) body.replaceChildren(el("tr", null, [el("td", { colspan: "8", class: "empty", text: "No refreshes recorded yet." })]));
      } catch (e) { if (!e.stale) p.error(e.message, doLoad); }
    }
    return { load: doLoad, isOpen: function () { return box.open; } };
  }

  M.panels = { Panel: Panel, KpiPanel: KpiPanel, TrendPanel: TrendPanel, ComparePanel: ComparePanel, TablePanel: TablePanel, LogsPanel: LogsPanel };
})(window);
