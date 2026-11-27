import { useEffect, useState } from "react";

const BASE = import.meta.env.VITE_API_BASE || "";

export class ApiError extends Error {}

function qs(params = {}) {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.append(k, v);
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

async function request(method, path, params, signal) {
  let res;
  try {
    res = await fetch(BASE + path + qs(params), { method, signal });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError("Cannot reach the API. Is the backend running on port 8000?");
  }
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* body was not JSON */
    }
    const err = new ApiError(detail || `API error ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const get = (path, params, signal) => request("GET", path, params, signal);
export const post = (path) => request("POST", path);
export const exportUrl = (params) => BASE + "/api/export/csv" + qs(params);

/** Fetch on mount and whenever path/params/extraDeps change. Keeps old data while reloading. */
export function useApi(path, params, extraDeps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [tick, setTick] = useState(0);
  const key = JSON.stringify(params);

  useEffect(() => {
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    get(path, params, ctrl.signal)
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((err) => {
        if (err.name === "AbortError") return;
        setState((s) => ({ data: s.data, error: err.message, loading: false }));
      });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key, tick, ...extraDeps]);

  return { ...state, reload: () => setTick((t) => t + 1) };
}
