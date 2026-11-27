
import requests
import pandas as pd
from pathlib import Path

URL = "https://api.dharun.dev/v1/mandi"

combinations = [
    ("Rajasthan", "Wheat"),
    ("Rajasthan", "Mustard"),
]

all_records = []

for state, commodity in combinations:
    print(f"\nFetching {commodity} - {state}")

    params = {
        "state": state,
        "commodity": commodity,
        "limit": 100
    }

    try:
        response = requests.get(URL, params=params, timeout=30)
        response.raise_for_status()

        result = response.json()
        records = result.get("data", [])

        all_records.extend(records)

        print("Records received:", len(records))

    except requests.exceptions.RequestException as error:
        print("Request failed:", error)

if all_records:
    df = pd.DataFrame(all_records)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    df = df.drop_duplicates()

    Path("data").mkdir(exist_ok=True)

    df.to_csv("data/mandi_prices.csv", index=False)

    print("\n========== DATA SUMMARY ==========")
    print("Total records:", len(df))
    print("Date range:", df["date"].min(), "to", df["date"].max())

    print("\nState and commodity counts:")
    print(df.groupby(["state", "commodity"]).size())

    print("\nSaved: data/mandi_prices.csv")
else:
    print("No records received.")
