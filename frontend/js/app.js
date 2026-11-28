/* Application controller: filters, URL state, freshness polling, manual refresh, export, theme. */
(function (global) {
  "use strict";
  var M = global.Mandi, U = M.utils, A = M.api, P = M.panels, $ = U.$, el = U.el;

  var DEFAULTS = { commodity: "Wheat", district: "", market: "", date_from: "", date_to: "" };
  var KEYS = Object.keys(DEFAULTS);
  var COMMODITIES = ["Wheat", "Mustard", "Bajra", "Soybean", "Gram"];   // same order as the API
  var POLL_MS = 60 * 1000, TICK_MS = 30 * 1000;

  var filters = Object.assign({}, DEFAULTS);
  var optionsLoader = A.createLoader();
  var freshness = null, health = null, apiDown = false, lastStamp, refreshing = false;
  var panels = {};

  /* ------------------------------------------------------------ URL + theme */
  function readUrl() {
    var q = new URLSearchParams(location.search), f = Object.assign({}, DEFAULTS);
    KEYS.forEach(function (k) { if (q.has(k)) f[k] = q.get(k); });
    if (COMMODITIES.indexOf(f.commodity) < 0) f.commodity = "Wheat";
    return f;
  }
  function syncUrl() {
    var q = new URLSearchParams();
    KEYS.forEach(function (k) { if (filters[k] && filters[k] !== DEFAULTS[k]) q.set(k, filters[k]); });
    var s = q.toString();
    history.replaceState(null, "", location.pathname + (s ? "?" + s : ""));
  }
  function applyTheme(t) {
    if (t) document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
  }

  /* ---------------------------------------------------------------- filters */
  function fillSelect(sel, items, current, allLabel) {
    var opts = [el("option", { value: "", text: allLabel })].concat(items.map(function (it) {
      return el("option", { value: it.value, text: it.label });
    }));
    sel.replaceChildren.apply(sel, opts);
    sel.value = current;
  }

  async function loadOptions() {
    try {
      var o = await optionsLoader(function (signal) {
        return A.get("/api/filters", { commodity: filters.commodity, district: filters.district }, { signal: signal });
      });
      if (filters.district && o.districts.indexOf(filters.district) < 0) filters.district = "";
      if (filters.market && !o.markets.some(function (m) { return m.market === filters.market; })) filters.market = "";
      fillSelect($("#fDistrict"), o.districts.map(function (d) { return { value: d, label: d }; }), filters.district, "All districts");
      fillSelect($("#fMarket"), o.markets.map(function (m) { return { value: m.market, label: m.market + " (" + m.district + ")" }; }), filters.market, "All markets");
      markCommodities(o);
      var r = o.date_range || {};
      [$("#fFrom"), $("#fTo")].forEach(function (i) { i.min = r.min || ""; i.max = r.max || ""; });
      panels.compare.setDateBounds(r);
      syncUrl(); renderChips();
    } catch (e) {
      if (!e.stale) banner("error", "Could not load filter options: " + e.message);
    }
  }

  /** Label commodities that have no stored data yet, so users know before selecting them. */
  function markCommodities(o) {
    var stored = o.commodities || [], labels = {};
    (o.supported_commodities || []).forEach(function (c) { labels[c.name] = c.label; });
    [].forEach.call($("#fCommodity").options, function (opt) {
      var base = labels[opt.value] || opt.textContent.replace(/ \(no data\)$/, "");
      opt.textContent = stored.indexOf(opt.value) < 0 ? base + " (no data)" : base;
    });
  }

  function renderChips() {
    var labels = { district: "District", market: "Market", date_from: "From", date_to: "To" };
    var chips = Object.keys(labels).filter(function (k) { return filters[k]; }).map(function (k) {
      return el("span", { class: "chip" }, [labels[k] + ": " + filters[k],
        el("button", { type: "button", "aria-label": "Clear " + labels[k], text: "×", onclick: function () { var p = {}; p[k] = ""; applyFilters(p); } })]);
    });
    $("#chips").replaceChildren.apply($("#chips"), chips);
  }

  function syncInputs() {
    $("#fCommodity").value = filters.commodity;
    $("#fDistrict").value = filters.district;
    $("#fMarket").value = filters.market;
    $("#fFrom").value = filters.date_from;
    $("#fTo").value = filters.date_to;
  }

  async function applyFilters(patch) {
    var prev = filters;
    var next = Object.assign({}, filters, patch);
    if (patch.commodity && patch.commodity !== prev.commodity && !("district" in patch)) { next.district = ""; next.market = ""; }
    if (patch.district !== undefined && patch.district !== prev.district && !("market" in patch)) next.market = "";
    if (next.date_from && next.date_to && next.date_from > next.date_to) {
      banner("warn", "“From” date must be on or before “To” date.");
      syncInputs();
      return;
    }
    clearBanner("filter");
    filters = next;
    syncInputs(); syncUrl(); renderChips();
    if (prev.commodity !== next.commodity || prev.district !== next.district) await loadOptions();
    syncInputs();
    loadPanels();
  }

  function loadPanels() {
    var f = Object.assign({}, filters);
    panels.kpi.load(f); panels.trend.load(f); panels.compare.load(f); panels.table.load(f);
    panels.cmp.load(f); panels.msp.load(f); panels.dist.load(f);
    if (panels.logs.isOpen()) panels.logs.load();
  }

  /* ---------------------------------------------------------------- banners */
  function banner(type, text, tag, retry) {
    var box = $("#banners");
    [].forEach.call(box.querySelectorAll('[data-tag="' + (tag || "filter") + '"]'), function (n) { n.remove(); });
    box.appendChild(el("div", { class: "msg " + type, "data-tag": tag || "filter", role: type === "error" ? "alert" : null }, [
      el("span", { text: text }),
      retry ? el("button", { class: "btn small", type: "button", text: "Retry", onclick: retry }) : null,
    ]));
  }
  function clearBanner(tag) {
    [].forEach.call($("#banners").querySelectorAll('[data-tag="' + tag + '"]'), function (n) { n.remove(); });
  }

  /* ------------------------------------------------- freshness + health UI */
  var LABELS = { fresh: "Fresh", delayed: "Delayed", stale: "Stale", never: "No data yet", offline: "Offline" };

  function renderStatus() {
    var badge = $("#freshBadge"), items = $("#statusItems"), sys = $("#sysStatus");
    if (apiDown) {
      badge.className = "badge offline"; badge.textContent = LABELS.offline;
      items.replaceChildren(el("span", { text: "Cannot reach the API. Showing the last loaded data; retrying every minute." }));
      sys.replaceChildren(el("span", null, [el("i", { class: "dot bad" }), "API offline"]));
      return;
    }
    if (freshness) {
      var f = freshness;
      badge.className = "badge " + f.status; badge.textContent = LABELS[f.status] || f.status;
      var now = Date.now();
      items.replaceChildren(
        el("span", null, ["Last updated: ", el("strong", { text: U.relTime(f.last_successful_refresh_at, now) })]),
        el("span", null, ["Latest prices: ", el("strong", { text: U.fmtDate(f.latest_price_date) })]),
        el("span", null, ["Next auto-refresh: ", el("strong", { text: U.countdown(f.next_scheduled_refresh, now) }),
          f.next_scheduled_refresh ? el("span", { class: "muted", text: " (" + U.fmtDateTime(f.next_scheduled_refresh) + ")" }) : null]),
        el("span", { class: "muted", text: U.fmtNum(f.total_records) + " records stored" }));
    }
    if (health) {
      var busy = health.refresh_running;
      var parts = [
        el("span", null, [el("i", { class: "dot " + (health.status === "ok" ? "ok" : "bad") }), health.database ? "Database OK" : "Database down"]),
        el("span", null, [el("i", { class: "dot " + (health.scheduler_running ? "ok" : "bad") }), health.scheduler_running ? "Scheduler on" : "Scheduler off"]),
      ];
      if (busy) parts.push(el("span", null, [el("i", { class: "dot busy" }), "Updating…"]));
      sys.replaceChildren.apply(sys, parts);
    }
    setRefreshButton();
  }

  function renderFreshBanners() {
    clearBanner("fresh");
    var f = freshness;
    if (!f) return;
    if (f.status === "never") banner("warn", "No price data stored yet. Use “Refresh data” to fetch the latest mandi prices.", "fresh");
    else if (f.last_refresh_status === "failed" || f.last_refresh_status === "partial")
      banner("warn", "Last refresh " + (f.last_refresh_status === "partial" ? "was partial" : "failed") +
        (f.last_refresh_error ? ": " + brief(f.last_refresh_error, 160) : ".") + " Showing the data stored so far.", "fresh");
    else if (f.days_behind > 0) banner("warn", "Latest prices are " + f.days_behind + " day(s) old. The source may not have published newer data yet.", "fresh");
  }

  async function pollStatus(initial) {
    var res = await Promise.allSettled([A.get("/health", null, { timeout: 8000 }), A.get("/api/freshness", null, { timeout: 8000 })]);
    var wasDown = apiDown;
    apiDown = res[0].status === "rejected" && res[1].status === "rejected";
    if (res[0].status === "fulfilled") health = res[0].value;
    if (res[1].status === "fulfilled") {
      freshness = res[1].value;
      var stamp = freshness.last_successful_refresh_at;
      if (!initial && lastStamp !== undefined && stamp !== lastStamp) {
        U.toast("New mandi data arrived — dashboard updated.", "ok");
        loadOptions().then(loadPanels);
      }
      lastStamp = stamp;
    }
    if (wasDown && !apiDown && !initial) { U.toast("Connection restored.", "ok"); loadOptions().then(loadPanels); }
    renderStatus(); renderFreshBanners();
  }

  /* ---------------------------------------------------------- manual refresh */
  function setRefreshButton() {
    var b = $("#refreshBtn"), serverBusy = health && health.refresh_running;
    b.disabled = refreshing || !!serverBusy || apiDown;
    b.textContent = refreshing ? "⟳ Refreshing…" : serverBusy ? "⟳ Updating…" : "⟳ Refresh data";
  }
  function brief(t, n) { t = String(t || "").split("\n")[0]; return t.length > n ? t.slice(0, n - 1) + "…" : t; }
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };

  async function runRefresh() {
    if (refreshing) return;
    refreshing = true; setRefreshButton();
    try {
      var before = (await A.get("/api/refresh/status")).last_refresh;
      var beforeId = before ? before.id : 0, needNew = true;
      try { await A.post("/api/refresh"); }
      catch (e) { if (e.status !== 409) throw e; needNew = false; }  // already running: just wait for it
      var result = null;
      for (var i = 0; i < 90 && !result; i++) {
        await sleep(2000);
        var s = await A.get("/api/refresh/status");
        var lr = s.last_refresh;
        if (!s.running && lr && lr.status !== "running" && (!needNew || lr.id > beforeId)) result = lr;
      }
      if (!result) U.toast("Refresh is still running. The dashboard will update when it finishes.", "warn", 7000);
      else if (result.status === "success")
        U.toast("Refresh finished: " + result.records_fetched + " fetched, " + result.records_inserted + " new, " +
                result.records_updated + " updated, " + result.records_rejected + " rejected.", "ok", 8000);
      else U.toast("Refresh " + result.status + ": " + brief(result.error_message || "see server log", 140),
                   result.status === "partial" ? "warn" : "error", 9000);
      await pollStatus(true);
      await loadOptions(); loadPanels();
    } catch (e) {
      U.toast(e.status === 429 ? e.message : "Refresh failed: " + brief(e.message, 140), e.status === 429 ? "warn" : "error", 7000);
    } finally { refreshing = false; setRefreshButton(); }
  }

  /* ----------------------------------------------------------------- export */
  async function exportCsv() {
    var b = $("#exportBtn");
    b.disabled = true; b.textContent = "Exporting…";
    try {
      var name = await A.downloadCsv(filters);
      U.toast("Downloaded " + name, "ok");
    } catch (e) { U.toast("Export failed: " + e.message, "error", 7000); }
    finally { b.disabled = false; b.textContent = "⬇ Export CSV"; }
  }

  async function exportReport() {
    var b = $("#reportBtn"), kind = $("#reportKind").value;
    b.disabled = true; b.textContent = "Preparing…";
    try {
      var name = await A.downloadReport(kind, { commodity: kind === "commodity_summary" ? "" : filters.commodity,
        district: filters.district, market: filters.market, date_from: filters.date_from, date_to: filters.date_to });
      U.toast("Downloaded " + name, "ok");
    } catch (e) { U.toast("Report failed: " + e.message, "error", 7000); }
    finally { b.disabled = false; b.textContent = "⬇ Report CSV"; }
  }

  /* ------------------------------------------------------------------- init */
  function scrollTo(id) { var n = $(id); n.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }); }

  function init() {
    applyTheme(U.store("mandi-theme") || "");
    filters = readUrl();
    $("#fCommodity").value = filters.commodity;
    $("#fFrom").value = filters.date_from; $("#fTo").value = filters.date_to;

    panels.kpi = P.KpiPanel($("#kpis"), $("#kpiNote"), {
      toTrend: function () { scrollTo("#trendPanel"); },
      toCompare: function () { panels.compare.setLevel("market"); scrollTo("#comparePanel"); },
      lowestMin: function () { panels.table.sortBy("min_price", "asc"); scrollTo("#tablePanel"); },
      highestMax: function () { panels.table.sortBy("max_price", "desc"); scrollTo("#tablePanel"); },
      filterMarket: function (m) { applyFilters({ market: m }); scrollTo("main"); },
      retry: function () { panels.kpi.load(filters); },
    });
    panels.trend = P.TrendPanel($("#trendPanel"), $("#trendChart"));
    panels.compare = P.ComparePanel($("#comparePanel"), $("#compareChart"), function (level, row) {
      if (level === "market") applyFilters({ district: row.district || filters.district, market: row.market });
      else applyFilters({ district: row.district, market: "" });
    });
    panels.table = P.TablePanel($("#tablePanel"));
    var pickCommodity = function (c) { applyFilters({ commodity: c }); scrollTo("#kpis"); };
    panels.cmp = M.analysis.CommodityPanel($("#cmpPanel"), $("#cmpChart"), pickCommodity);
    panels.msp = M.analysis.MspPanel($("#mspPanel"), $("#mspChart"), $("#mspBreakPanel"), pickCommodity);
    panels.dist = M.analysis.DistrictPanel($("#distPanel"), $("#distChart"), function (d) { applyFilters({ district: d, market: "" }); scrollTo("main"); });
    panels.logs = P.LogsPanel($("#logsBox"));

    $("#fCommodity").addEventListener("change", function () { applyFilters({ commodity: this.value }); });
    $("#fDistrict").addEventListener("change", function () { applyFilters({ district: this.value }); });
    $("#fMarket").addEventListener("change", function () { applyFilters({ market: this.value }); });
    var dateChange = U.debounce(function (k, v) { var p = {}; p[k] = v; applyFilters(p); }, 250);
    $("#fFrom").addEventListener("change", function () { dateChange("date_from", this.value); });
    $("#fTo").addEventListener("change", function () { dateChange("date_to", this.value); });
    $("#resetBtn").addEventListener("click", function () { applyFilters(Object.assign({}, DEFAULTS)); });
    $("#refreshBtn").addEventListener("click", runRefresh);
    $("#exportBtn").addEventListener("click", exportCsv);
    $("#reportBtn").addEventListener("click", exportReport);
    $("#logsBox").addEventListener("toggle", function () { if (this.open) panels.logs.load(); });
    $("#themeBtn").addEventListener("click", function () {
      var cur = document.documentElement.getAttribute("data-theme");
      var dark = cur ? cur === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      var next = dark ? "light" : "dark";
      applyTheme(next); U.store("mandi-theme", next);
      panels.trend.render(); panels.compare.render();
      panels.cmp.render(); panels.msp.render(); panels.dist.render();
    });
    document.addEventListener("visibilitychange", function () { if (!document.hidden) pollStatus(); });

    // Boot: freshness first (cheap), then options, then every panel.
    pollStatus(true);
    loadOptions().then(function () { syncInputs(); loadPanels(); });
    setInterval(function () { if (!document.hidden) pollStatus(); }, POLL_MS);
    setInterval(function () { if (!document.hidden) renderStatus(); }, TICK_MS);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})(window);
