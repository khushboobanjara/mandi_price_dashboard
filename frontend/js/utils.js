/* Helpers: DOM, formatting, toasts, safe storage. No dependencies. */
(function (global) {
  "use strict";
  var M = (global.Mandi = global.Mandi || {});
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function $(sel, root) { return (root || document).querySelector(sel); }

  /** Build an element safely (text is always set with textContent, never innerHTML). */
  function el(tag, props, children) {
    var node = document.createElement(tag);
    Object.keys(props || {}).forEach(function (k) {
      var v = props[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.slice(0, 2) === "on") node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    });
    [].concat(children || []).forEach(function (c) {
      if (c === null || c === undefined || c === false) return;
      node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return node;
  }

  function parseDay(s) { // "YYYY-MM-DD" as a local date (avoids timezone shifts)
    var p = String(s).split("-").map(Number);
    return new Date(p[0], p[1] - 1, p[2]);
  }
  function fmtDate(s) {
    if (!s) return "—";
    var d = parseDay(s);
    return d.getDate() + " " + MONTHS[d.getMonth()] + " " + d.getFullYear();
  }
  function shortDate(s) {
    if (!s) return "";
    var d = parseDay(s);
    return d.getDate() + " " + MONTHS[d.getMonth()];
  }
  function fmtPrice(v) {
    if (v === null || v === undefined || isNaN(v)) return "—";
    return "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  }
  function fmtNum(v) {
    return v === null || v === undefined ? "—" : Number(v).toLocaleString("en-IN");
  }
  function fmtPct(v) {
    if (v === null || v === undefined) return "n/a";
    var arrow = v > 0 ? "▲" : v < 0 ? "▼" : "•";
    return arrow + " " + Math.abs(v).toFixed(2) + "%";
  }
  function fmtDateTime(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d)) return "—";
    return d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }
  function relTime(iso, now) {
    if (!iso) return "never";
    var mins = Math.round(((now || Date.now()) - new Date(iso).getTime()) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return mins + " min ago";
    var h = Math.floor(mins / 60), m = mins % 60;
    if (h < 48) return h + " h " + (m ? m + " min " : "") + "ago";
    return Math.floor(h / 24) + " days ago";
  }
  function countdown(iso, now) {
    if (!iso) return "not scheduled";
    var mins = Math.round((new Date(iso).getTime() - (now || Date.now())) / 60000);
    if (mins <= 0) return "due now";
    if (mins < 60) return "in " + mins + " min";
    return "in " + Math.floor(mins / 60) + " h " + (mins % 60) + " min";
  }
  function debounce(fn, ms) {
    var t;
    return function () {
      var a = arguments, self = this;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(self, a); }, ms);
    };
  }
  function store(key, value) { // localStorage can be blocked (private mode); never throw
    try {
      if (value === undefined) return global.localStorage.getItem(key);
      global.localStorage.setItem(key, value);
    } catch (e) { /* ignore */ }
    return null;
  }
  function toast(text, type, ms) {
    var box = $("#toasts");
    if (!box) return;
    var t = el("div", { class: "toast " + (type || ""), text: text });
    box.appendChild(t);
    setTimeout(function () { t.remove(); }, ms || 5000);
  }

  M.utils = {
    $: $, el: el, fmtDate: fmtDate, shortDate: shortDate, fmtPrice: fmtPrice, fmtNum: fmtNum,
    fmtPct: fmtPct, fmtDateTime: fmtDateTime, relTime: relTime, countdown: countdown,
    debounce: debounce, store: store, toast: toast,
  };
})(window);
