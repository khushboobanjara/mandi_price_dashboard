/* Thin fetch wrapper: timeouts, one retry for GETs, readable errors, cancellable loaders. */
(function (global) {
  "use strict";
  var M = (global.Mandi = global.Mandi || {});
  var TIMEOUT_MS = 20000;

  function ApiError(message, status, kind) {
    var e = new Error(message);
    e.name = "ApiError"; e.status = status || 0; e.kind = kind || "http";
    return e;
  }

  function qs(params) {
    var p = new URLSearchParams();
    Object.keys(params || {}).forEach(function (k) {
      var v = params[k];
      if (v !== undefined && v !== null && v !== "") p.append(k, v);
    });
    var s = p.toString();
    return s ? "?" + s : "";
  }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  async function readDetail(res) {
    try {
      var body = await res.json();
      if (typeof body.detail === "string") return body.detail;
      if (Array.isArray(body.detail)) return body.detail.map(function (d) { return d.msg; }).join("; ");
      return body.detail ? JSON.stringify(body.detail) : "";
    } catch (e) { return ""; }
  }

  async function attempt(method, url, signal, timeout) {
    var ctrl = new AbortController(), timedOut = false;
    var timer = setTimeout(function () { timedOut = true; ctrl.abort(); }, timeout);
    var onAbort = function () { ctrl.abort(); };
    if (signal) {
      if (signal.aborted) ctrl.abort(); else signal.addEventListener("abort", onAbort);
    }
    try {
      return await fetch(url, { method: method, signal: ctrl.signal, headers: { Accept: "application/json" } });
    } catch (e) {
      if (timedOut) throw ApiError("The server took too long to respond.", 0, "timeout");
      if (signal && signal.aborted) { var a = new Error("aborted"); a.name = "AbortError"; throw a; }
      throw ApiError("Cannot reach the API. Is the server running?", 0, "network");
    } finally {
      clearTimeout(timer);
      if (signal) signal.removeEventListener("abort", onAbort);
    }
  }

  async function request(method, path, params, opts) {
    opts = opts || {};
    var url = path + qs(params), tries = method === "GET" ? 2 : 1, last;
    for (var i = 0; i < tries; i++) {
      try {
        var res = await attempt(method, url, opts.signal, opts.timeout || TIMEOUT_MS);
        if (res.ok) return await res.json();
        var detail = await readDetail(res);
        last = ApiError(detail || ("Server error (" + res.status + ")"), res.status, "http");
        if (![502, 503, 504].includes(res.status)) throw last; // retry only transient errors
      } catch (e) {
        if (e.name === "AbortError" || e.kind === "http" && ![502, 503, 504].includes(e.status)) throw e;
        last = e;
      }
      if (i < tries - 1) await sleep(500);
    }
    throw last;
  }

  /** Download the CSV export as a file (keeps the page in control for loading + errors). */
  async function downloadCsv(params) {
    var res = await attempt("GET", "/api/export/csv" + qs(params), null, 60000);
    if (!res.ok) throw ApiError((await readDetail(res)) || ("Export failed (" + res.status + ")"), res.status);
    var blob = await res.blob();
    var m = /filename="?([^";]+)"?/i.exec(res.headers.get("Content-Disposition") || "");
    var name = m ? m[1] : "mandi_prices.csv";
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    return name;
  }

  /** Download one of the CSV reports (commodity_summary, district_analysis, msp, history). */
  async function downloadReport(kind, params) {
    var p = Object.assign({}, params, { kind: kind });
    var res = await attempt("GET", "/api/export/report" + qs(p), null, 60000);
    if (!res.ok) throw ApiError((await readDetail(res)) || ("Report failed (" + res.status + ")"), res.status);
    var blob = await res.blob();
    var m = /filename="?([^";]+)"?/i.exec(res.headers.get("Content-Disposition") || "");
    var name = m ? m[1] : "mandi_report_" + kind + ".csv";
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    return name;
  }

  /** Each loader cancels its previous request, so fast filter changes never show stale data. */
  function createLoader() {
    var current = null;
    return async function run(fn) {
      if (current) current.abort();
      var ctrl = (current = new AbortController());
      try { return await fn(ctrl.signal); }
      catch (e) { if (ctrl.signal.aborted) e.stale = true; throw e; }
    };
  }

  M.api = {
    get: function (path, params, opts) { return request("GET", path, params, opts); },
    post: function (path, opts) { return request("POST", path, null, opts); },
    downloadCsv: downloadCsv, downloadReport: downloadReport, createLoader: createLoader, qs: qs,
  };
})(window);
