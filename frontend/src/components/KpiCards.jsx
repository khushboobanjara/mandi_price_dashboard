import { useApi } from "../api.js";
import { fmtDate, fmtPct, fmtPrice } from "../utils.js";
import ErrorBox from "./ErrorBox.jsx";

function Delta({ change, label }) {
  if (!change) return null;
  if (change.pct_change === null || change.pct_change === undefined) {
    return <div className="delta flat">{label}: n/a (no common markets)</div>;
  }
  const cls = change.pct_change > 0 ? "up" : change.pct_change < 0 ? "down" : "flat";
  return (
    <div className={`delta ${cls}`} title="Compares only markets that reported on both dates">
      {fmtPct(change.pct_change)} {label}
      <span className="muted"> ({change.markets_compared} market{change.markets_compared === 1 ? "" : "s"})</span>
    </div>
  );
}

function Card({ label, value, sub, children }) {
  return (
    <div className="card kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="muted small">{sub}</div>}
      {children}
    </div>
  );
}

export default function KpiCards({ filters, refreshKey }) {
  const { data, error, loading, reload } = useApi("/api/kpis", filters, [refreshKey]);
  const k = data?.commodities?.[filters.commodity];

  return (
    <section className={loading ? "loading" : ""}>
      <ErrorBox message={error} onRetry={reload} />
      {k && !k.has_data && <div className="card empty">No prices found for these filters.</div>}
      {k?.has_data && (
        <>
          <div className="kpis">
            <Card label="Avg modal price" value={fmtPrice(k.summary.avg_modal)} sub={`as of ${fmtDate(k.latest_date)}`}>
              <Delta change={k.change_vs_previous} label={`vs ${fmtDate(k.previous_date)}`} />
              <Delta change={k.change_vs_week} label={k.week_compare_date ? `vs ${fmtDate(k.week_compare_date)}` : "vs a week ago"} />
            </Card>
            <Card label="Lowest min price" value={fmtPrice(k.summary.min_price)} sub="across reporting markets" />
            <Card label="Highest max price" value={fmtPrice(k.summary.max_price)} sub="across reporting markets" />
            <Card label="Markets reporting" value={k.summary.markets_reporting} sub={`${k.summary.records} records`} />
            <Card label="Highest modal market" value={k.summary.highest_modal_market?.market ?? "—"}
                  sub={fmtPrice(k.summary.highest_modal_market?.price)} />
            <Card label="Lowest modal market" value={k.summary.lowest_modal_market?.market ?? "—"}
                  sub={fmtPrice(k.summary.lowest_modal_market?.price)} />
          </div>
          {k.summary.missing_price_rows > 0 && (
            <div className="warn">{k.summary.missing_price_rows} record(s) have a missing min, max or modal price.</div>
          )}
        </>
      )}
    </section>
  );
}
