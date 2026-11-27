import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { exportUrl, get, post, useApi } from "./api.js";
import Filters from "./components/Filters.jsx";
import Header from "./components/Header.jsx";
import KpiCards from "./components/KpiCards.jsx";
import MarketComparison from "./components/MarketComparison.jsx";
import PricesTable from "./components/PricesTable.jsx";
import TrendChart from "./components/TrendChart.jsx";

const DEFAULTS = { commodity: "Wheat", district: "", market: "", date_from: "", date_to: "" };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export default function App() {
  const [filters, setFilters] = useState(DEFAULTS);
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState(null);

  const options = useApi("/api/filters", { commodity: filters.commodity, district: filters.district }, [refreshKey]);
  const freshness = useApi("/api/freshness", {}, [refreshKey]);
  const exportHref = useMemo(() => exportUrl(filters), [filters]);

  // If the 3-hourly scheduler stored new data, reload every panel automatically.
  const lastSeen = useRef(null);
  useEffect(() => {
    const stamp = freshness.data?.last_successful_refresh_at;
    if (stamp === undefined) return;
    if (lastSeen.current !== null && lastSeen.current !== stamp) setRefreshKey((k) => k + 1);
    lastSeen.current = stamp;
  }, [freshness.data]);
  useEffect(() => {
    const id = setInterval(() => freshness.reload(), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const runRefresh = useCallback(async () => {
    setRefreshing(true);
    setRefreshMsg(null);
    try {
      const before = (await get("/api/refresh/status")).last_refresh?.id ?? 0;
      let needNew = true;
      try {
        await post("/api/refresh");
      } catch (e) {
        if (e.status !== 409) throw e;
        needNew = false; // already running: just wait for it to finish
      }
      let result = null;
      for (let i = 0; i < 60 && !result; i++) {
        await sleep(2000);
        const s = await get("/api/refresh/status");
        const lr = s.last_refresh;
        if (!s.running && lr && lr.status !== "running" && (!needNew || lr.id > before)) result = lr;
      }
      if (!result) {
        setRefreshMsg({ type: "warn", text: "Refresh is still running. The dashboard will update when it finishes." });
      } else if (result.status === "success") {
        setRefreshMsg({ type: "ok", text: `Refresh finished: ${result.records_fetched} fetched, ${result.records_inserted} new, ${result.records_updated} updated, ${result.records_rejected} rejected.` });
      } else {
        setRefreshMsg({
          type: result.status === "partial" ? "warn" : "error",
          text: `Refresh ${result.status}: ${result.error_message ?? "see server log"}`,
        });
      }
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setRefreshMsg({ type: "error", text: e.message });
    } finally {
      setRefreshing(false);
    }
  }, []);

  return (
    <div className="page">
      <Header freshness={freshness} onRefresh={runRefresh} refreshing={refreshing} refreshMsg={refreshMsg} exportHref={exportHref} />
      <Filters filters={filters} setFilters={setFilters} options={options} onReset={() => setFilters(DEFAULTS)} />
      <KpiCards filters={filters} refreshKey={refreshKey} />
      <div className="grid-2">
        <TrendChart filters={filters} refreshKey={refreshKey} />
        <MarketComparison filters={filters} refreshKey={refreshKey} dateRange={options.data?.date_range} />
      </div>
      <PricesTable filters={filters} refreshKey={refreshKey} />
      <footer className="muted small">
        Percentage changes compare only markets that reported on both dates. Data refreshes automatically every 3 hours.
      </footer>
    </div>
  );
}
