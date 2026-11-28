"""Standalone collector: fetch Rajasthan mandi prices for the five supported commodities and
MERGE them into data/mandi_prices.csv (it never overwrites history; the API only returns the newest day).

Run:  python fatch_mandi_data.py   then   python -m scripts.import_csv
The dashboard itself refreshes every 3 hours without this script; this is for manual CSV snapshots.
"""
import sys
from pathlib import Path

import pandas as pd
import requests

from app.commodities import COMMODITIES, normalize_commodity

URL = "https://api.dharun.dev/v1/mandi"
STATE = "Rajasthan"          # the whole project is Rajasthan-only
CSV_PATH = Path("data/mandi_prices.csv")
KEY = ["date", "state", "district", "market", "commodity", "variety", "grade"]


def fetch(commodity):
    """Try each known upstream spelling until one returns rows for exactly this commodity."""
    for api_name in commodity.api_names:
        try:
            response = requests.get(URL, params={"state": STATE, "commodity": api_name, "limit": 100}, timeout=30)
            response.raise_for_status()
            records = response.json().get("data", [])
        except (requests.exceptions.RequestException, ValueError) as error:
            print(f"  {api_name}: request failed - {error}")
            continue
        mine = [r for r in records
                if normalize_commodity(r.get("commodity")) == commodity.name
                and str(r.get("state", STATE)).strip().casefold() == STATE.casefold()]
        print(f"  {api_name}: {len(records)} received, {len(mine)} usable")
        if mine:
            for r in mine:
                r["commodity"] = commodity.name   # canonical name, same as the database
            return mine
    return []


def main():
    new_records = []
    for commodity in COMMODITIES:
        print(f"Fetching {commodity.label} - {STATE}")
        got = fetch(commodity)
        if not got:
            print(f"  no data available for {commodity.label} right now")
        new_records.extend(got)

    if not new_records:
        print("No records received.")
        return 1

    df = pd.DataFrame(new_records)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for col in ("variety", "grade"):
        if col not in df:
            df[col] = ""
        df[col] = df[col].fillna("")

    if CSV_PATH.exists():
        old = pd.read_csv(CSV_PATH, dtype=str).fillna("")
        df = pd.concat([old, df.astype(str)], ignore_index=True)
    # newest fetch wins for the same market/day/variety/grade; no duplicate rows ever
    df = df.drop_duplicates(subset=KEY, keep="last")

    CSV_PATH.parent.mkdir(exist_ok=True)
    df.to_csv(CSV_PATH, index=False)

    print("\n========== DATA SUMMARY ==========")
    print("Total records:", len(df))
    print("Date range:", df["date"].min(), "to", df["date"].max())
    print("\nCommodity counts:")
    print(df.groupby(["state", "commodity"]).size())
    print(f"\nSaved: {CSV_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
