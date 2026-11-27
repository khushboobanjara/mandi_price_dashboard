const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Parse "YYYY-MM-DD" as a local date (new Date("2026-11-27") would shift by timezone).
function parseDate(s) {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function fmtDate(s) {
  if (!s) return "—";
  const d = parseDate(s);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

export function shortDate(s) {
  if (!s) return "";
  const d = parseDate(s);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

export function fmtPrice(v) {
  if (v === null || v === undefined) return "—";
  return "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

export function fmtPct(v) {
  if (v === null || v === undefined) return "n/a";
  const arrow = v > 0 ? "▲" : v < 0 ? "▼" : "•";
  return `${arrow} ${Math.abs(v).toFixed(2)}%`;
}

export function timeAgo(hours) {
  if (hours === null || hours === undefined) return "never";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min ago`;
  return `${hours.toFixed(1)} h ago`;
}

export function fmtDateTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}
