import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "../api.js";
import { fmtDate, fmtPct, fmtPrice } from "../utils.js";
import ErrorBox from "./ErrorBox.jsx";

function CompareTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="tooltip">
      <strong>{r.name}</strong>
      {r.market && <div className="muted">{r.district}</div>}
      <div>Avg modal: {fmtPrice(r.avg_modal)}</div>
      <div>Min {fmtPrice(r.min_price)} · Max {fmtPrice(r.max_price)}</div>
      <div>Spread: {fmtPrice(r.spread)}</div>
      <div>vs average: {fmtPct(r.diff_vs_avg_pct)}</div>
    </div>
  );
}

export default function MarketComparison({ filters, refreshKey, dateRange }) {
  const [level, setLevel] = useState("market");
  const [day, setDay] = useState("");
  const params = { commodity: filters.commodity, district: filters.district, market: filters.market, level, date: day, limit: 15 };
  const { data, error, loading, reload } = useApi("/api/markets/compare", params, [refreshKey]);
  const rows = (data?.rows ?? []).map((r) => ({ ...r, name: level === "market" ? r.market : r.district }));

  return (
    <section className={`card ${loading ? "loading" : ""}`}>
      <div className="card-head">
        <h2>{level === "market" ? "Market" : "District"} comparison — {filters.commodity}</h2>
        <div className="controls">
          <input type="date" value={day} min={dateRange?.min ?? undefined} max={dateRange?.max ?? undefined}
                 onChange={(e) => setDay(e.target.value)} title="Leave empty for the latest date" />
          <div className="seg">
            <button className={level === "market" ? "active" : ""} onClick={() => setLevel("market")}>Markets</button>
            <button className={level === "district" ? "active" : ""} onClick={() => setLevel("district")}>Districts</button>
          </div>
        </div>
      </div>
      <ErrorBox message={error} onRetry={reload} />
      {data?.date && (
        <p className="muted small">
          {fmtDate(data.date)} · average modal {fmtPrice(data.average_modal)} · top {rows.length} by modal price
        </p>
      )}
      {!error && rows.length === 0 && !loading && <div className="empty">No prices on this date for these filters.</div>}
      {rows.length > 0 && (
        <ResponsiveContainer width="100%" height={Math.max(240, rows.length * 30 + 60)}>
          <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 70, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" tickFormatter={(v) => Number(v).toLocaleString("en-IN")} />
            <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 12 }} />
            <Tooltip content={<CompareTooltip />} />
            <Bar dataKey="avg_modal" name="Avg modal">
              {rows.map((r) => (
                <Cell key={r.name} fill={(r.diff_vs_avg_pct ?? 0) >= 0 ? "#2563eb" : "#f59e0b"} />
              ))}
              <LabelList dataKey="avg_modal" position="right" formatter={fmtPrice} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
      <p className="muted small">Blue = at or above the average for the day, amber = below.</p>
    </section>
  );
}
