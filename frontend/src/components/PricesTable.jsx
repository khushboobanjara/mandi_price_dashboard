import { useEffect, useState } from "react";
import { useApi } from "../api.js";
import { fmtDate, fmtPrice } from "../utils.js";
import ErrorBox from "./ErrorBox.jsx";

const COLUMNS = [
  ["date", "Date", true], ["district", "District", true], ["market", "Market", true],
  ["variety", "Variety", false], ["grade", "Grade", false],
  ["min_price", "Min", true], ["max_price", "Max", true], ["modal_price", "Modal", true],
];

export default function PricesTable({ filters, refreshKey }) {
  const [sortBy, setSortBy] = useState("date");
  const [order, setOrder] = useState("desc");
  const [page, setPage] = useState(1);
  const filterKey = JSON.stringify(filters);

  useEffect(() => setPage(1), [filterKey, sortBy, order]);

  const { data, error, loading, reload } = useApi(
    "/api/prices", { ...filters, sort_by: sortBy, order, page, page_size: 25 }, [refreshKey]);

  const toggleSort = (key) => {
    if (key === sortBy) setOrder((o) => (o === "asc" ? "desc" : "asc"));
    else { setSortBy(key); setOrder("desc"); }
  };

  return (
    <section className={`card ${loading ? "loading" : ""}`}>
      <div className="card-head">
        <h2>Price records</h2>
        {data && <span className="muted">{data.total.toLocaleString("en-IN")} records</span>}
      </div>
      <ErrorBox message={error} onRetry={reload} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {COLUMNS.map(([key, label, sortable]) => (
                <th key={key} className={sortable ? "sortable" : ""} onClick={sortable ? () => toggleSort(key) : undefined}>
                  {label}{sortBy === key ? (order === "asc" ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data?.items.map((r) => (
              <tr key={r.id}>
                <td>{fmtDate(r.date)}</td><td>{r.district}</td><td>{r.market}</td>
                <td>{r.variety}</td><td>{r.grade}</td>
                <td className="num">{fmtPrice(r.min_price)}</td>
                <td className="num">{fmtPrice(r.max_price)}</td>
                <td className="num">{fmtPrice(r.modal_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && <div className="empty">No records for these filters.</div>}
      </div>
      {data && data.pages > 1 && (
        <div className="pager">
          <button className="btn small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>← Prev</button>
          <span>Page {data.page} of {data.pages}</span>
          <button className="btn small" disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)}>Next →</button>
        </div>
      )}
    </section>
  );
}
