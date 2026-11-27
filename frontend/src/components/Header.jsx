import { fmtDate, fmtDateTime, timeAgo } from "../utils.js";
import ErrorBox from "./ErrorBox.jsx";

const LABELS = { fresh: "Fresh", delayed: "Delayed", stale: "Stale", never: "No data yet" };

export default function Header({ freshness, onRefresh, refreshing, refreshMsg, exportHref }) {
  const f = freshness.data;
  return (
    <header className="header">
      <div className="header-top">
        <div>
          <h1>Rajasthan Wheat &amp; Mustard Mandi Prices</h1>
          <p className="muted">Prices in ₹ per quintal · Source: api.dharun.dev</p>
        </div>
        <div className="actions">
          <a className="btn" href={exportHref} download>⬇ Export CSV</a>
          <button className="btn primary" onClick={onRefresh} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "⟳ Refresh data"}
          </button>
        </div>
      </div>

      {f && (
        <div className="fresh-row">
          <span className={`badge ${f.status}`}>{LABELS[f.status] ?? f.status}</span>
          <span>Last updated: <strong>{timeAgo(f.hours_since_refresh)}</strong></span>
          <span>Latest prices: <strong>{fmtDate(f.latest_price_date)}</strong></span>
          <span>Next auto-refresh: <strong>{fmtDateTime(f.next_scheduled_refresh)}</strong></span>
          <span className="muted">{f.total_records.toLocaleString("en-IN")} records stored</span>
        </div>
      )}

      <ErrorBox message={freshness.error} onRetry={freshness.reload} />
      {f && f.last_refresh_status && f.last_refresh_status !== "success" && f.last_refresh_status !== "running" && (
        <div className="warn">
          Last refresh {f.last_refresh_status === "partial" ? "was partial" : "failed"}
          {f.last_refresh_error ? `: ${f.last_refresh_error}` : "."} Showing the data stored so far.
        </div>
      )}
      {f && f.days_behind > 0 && (
        <div className="warn">Latest prices are {f.days_behind} day(s) old.</div>
      )}
      {refreshMsg && <div className={refreshMsg.type === "ok" ? "ok" : refreshMsg.type === "warn" ? "warn" : "error"}>{refreshMsg.text}</div>}
    </header>
  );
}
