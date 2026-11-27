import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api.js";
import { fmtDate, fmtPrice, shortDate } from "../utils.js";
import ErrorBox from "./ErrorBox.jsx";

const PALETTE = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c"];

function buildRows(series, groupBy) {
  if (!series?.length) return [];
  if (groupBy === "none") {
    return series[0].points.map((p) => ({
      date: p.date, avg: p.avg_modal, min: p.min_price, max: p.max_price, markets: p.markets_reporting,
    }));
  }
  const byDate = new Map();
  series.forEach((s) =>
    s.points.forEach((p) => {
      const row = byDate.get(p.date) || { date: p.date };
      row[s.name] = p.avg_modal;
      byDate.set(p.date, row);
    })
  );
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="tooltip">
      <strong>{fmtDate(label)}</strong>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.color }}>{p.name}: {fmtPrice(p.value)}</div>
      ))}
      {row.markets != null && <div className="muted">{row.markets} market(s) reporting</div>}
    </div>
  );
}

export default function TrendChart({ filters, refreshKey }) {
  const [groupBy, setGroupBy] = useState("none");
  const { data, error, loading, reload } = useApi("/api/trends", { ...filters, group_by: groupBy, top: 5 }, [refreshKey]);
  const series = data?.series ?? [];
  const rows = buildRows(series, groupBy);

  let coverageWarning = null;
  if (groupBy === "none" && rows.length > 1) {
    const latest = rows[rows.length - 1];
    const peak = Math.max(...rows.map((r) => r.markets));
    if (latest.markets < peak * 0.5) {
      coverageWarning = `Only ${latest.markets} market(s) have reported for ${fmtDate(latest.date)} so far (up to ${peak} on earlier days), so the latest average may not be comparable.`;
    }
  }

  return (
    <section className={`card ${loading ? "loading" : ""}`}>
      <div className="card-head">
        <h2>Price trend — {filters.commodity}</h2>
        <div className="seg">
          {[["none", "Overall"], ["market", "Top markets"], ["district", "Top districts"]].map(([v, l]) => (
            <button key={v} className={groupBy === v ? "active" : ""} onClick={() => setGroupBy(v)}>{l}</button>
          ))}
        </div>
      </div>
      <ErrorBox message={error} onRetry={reload} />
      {coverageWarning && <div className="warn">{coverageWarning}</div>}
      {!error && rows.length === 0 && !loading && <div className="empty">No data for these filters.</div>}
      {rows.length > 0 && (
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={shortDate} />
            <YAxis tickFormatter={(v) => Number(v).toLocaleString("en-IN")} domain={["auto", "auto"]} width={70} />
            <Tooltip content={<TrendTooltip />} />
            <Legend />
            {groupBy === "none" ? (
              <>
                <Line type="monotone" dataKey="avg" name="Avg modal" stroke="#2563eb" strokeWidth={2} dot />
                <Line type="monotone" dataKey="min" name="Lowest min" stroke="#16a34a" strokeDasharray="5 4" dot />
                <Line type="monotone" dataKey="max" name="Highest max" stroke="#dc2626" strokeDasharray="5 4" dot />
              </>
            ) : (
              series.map((s, i) => (
                <Line key={s.name} type="monotone" dataKey={s.name} name={s.name}
                      stroke={PALETTE[i % PALETTE.length]} strokeWidth={2} dot connectNulls />
              ))
            )}
          </LineChart>
        </ResponsiveContainer>
      )}
    </section>
  );
}
