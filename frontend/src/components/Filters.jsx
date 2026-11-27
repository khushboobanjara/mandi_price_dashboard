const COMMODITIES = ["Wheat", "Mustard"];

export default function Filters({ filters, setFilters, options, onReset }) {
  const set = (patch) => setFilters((f) => ({ ...f, ...patch }));
  const o = options.data;
  const districts = o?.districts ?? [];
  const markets = o?.markets ?? [];
  const range = o?.date_range ?? {};

  return (
    <section className="card filters">
      <label>
        Commodity
        <select value={filters.commodity} onChange={(e) => set({ commodity: e.target.value, district: "", market: "" })}>
          {COMMODITIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
      <label>
        District
        <select value={filters.district} onChange={(e) => set({ district: e.target.value, market: "" })}>
          <option value="">All districts</option>
          {districts.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </label>
      <label>
        Market
        <select value={filters.market} onChange={(e) => set({ market: e.target.value })}>
          <option value="">All markets</option>
          {markets.map((m) => (
            <option key={m.market + m.district} value={m.market}>{m.market} ({m.district})</option>
          ))}
        </select>
      </label>
      <label>
        From
        <input type="date" value={filters.date_from} min={range.min ?? undefined} max={filters.date_to || range.max || undefined}
               onChange={(e) => set({ date_from: e.target.value })} />
      </label>
      <label>
        To
        <input type="date" value={filters.date_to} min={filters.date_from || range.min || undefined} max={range.max ?? undefined}
               onChange={(e) => set({ date_to: e.target.value })} />
      </label>
      <button className="btn" onClick={onReset}>Reset</button>
    </section>
  );
}
