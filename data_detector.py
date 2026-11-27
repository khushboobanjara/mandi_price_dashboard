
import os
import time
import requests
import pandas as pd

from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ==========================================
# 1. CONFIGURATION
# ==========================================

load_dotenv()

API_KEY = os.getenv("DATA_GOV_API_KEY")

RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"

BASE_URL = "https://api.data.gov.in/resource"

URL = f"{BASE_URL}/{RESOURCE_ID}"

OUTPUT_FOLDER = "output"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# ==========================================
# 2. VALIDATE API KEY
# ==========================================

if not API_KEY:
    raise ValueError(
        "API key not found. Add DATA_GOV_API_KEY to your .env file."
    )


# ==========================================
# 3. CREATE REQUEST SESSION
# ==========================================

session = requests.Session()

retry_strategy = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    respect_retry_after_header=True
)

adapter = HTTPAdapter(max_retries=retry_strategy)

session.mount("https://", adapter)


# ==========================================
# 4. FETCH DATA FROM API
# ==========================================

def fetch_mandi_data(state, commodity, limit=100):

    params = {
        "api-key": API_KEY,
        "format": "json",
        "limit": limit,
        "offset": 0,
        "filters[state]": state,
        "filters[commodity]": commodity
    }

    print("\n" + "=" * 55)
    print(f"Fetching {commodity} prices for {state}")
    print("=" * 55)

    try:

        response = session.get(
            URL,
            params=params,
            timeout=(15, 90)
        )

        print("HTTP Status:", response.status_code)

        response.raise_for_status()

        data = response.json()

        records = data.get("records", [])

        if not records:
            print("No records returned.")
            print("API response:", data)
            return pd.DataFrame()

        df = pd.DataFrame(records)

        print("Records received:", len(df))
        print("Columns:", df.columns.tolist())

        return df

    except requests.exceptions.HTTPError:

        print("HTTP Error:", response.status_code)
        print("Server response:", response.text[:500])

    except requests.exceptions.Timeout:

        print("Request timed out.")
        print("The API server took too long to respond.")

    except requests.exceptions.ConnectionError as error:

        print("Connection error.")
        print(error)

    except requests.exceptions.RequestException as error:

        print("Request failed:", error)

    except ValueError:

        print("Invalid JSON response from API.")

    return pd.DataFrame()


# ==========================================
# 5. CLEAN AND STANDARDIZE DATA
# ==========================================

def clean_data(df):

    if df.empty:
        return df

    df.columns = df.columns.str.strip().str.lower()

    numeric_columns = [
        "min_price",
        "max_price",
        "modal_price"
    ]

    for column in numeric_columns:

        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

    if "arrival_date" in df.columns:

        df["arrival_date"] = pd.to_datetime(
            df["arrival_date"],
            errors="coerce",
            dayfirst=True
        )

    return df


# ==========================================
# 6. CALCULATE PRICE ANALYSIS
# ==========================================

def analyze_prices(df, state, commodity):

    if df.empty:
        print("No data available for analysis.")
        return

    print("\nPRICE ANALYSIS")
    print("-" * 55)

    if "modal_price" not in df.columns:
        print("Modal price column not available.")
        return

    prices = df["modal_price"].dropna()

    if prices.empty:
        print("No valid modal prices.")
        return

    print("State:", state)
    print("Commodity:", commodity)

    print("Average modal price:", round(prices.mean(), 2))
    print("Median modal price:", round(prices.median(), 2))
    print("Minimum modal price:", prices.min())
    print("Maximum modal price:", prices.max())

    if "market" in df.columns:

        market_prices = (
            df.groupby("market")["modal_price"]
            .mean()
            .sort_values(ascending=False)
        )

        print("\nTop 5 markets:")
        print(market_prices.head(5))

        print("\nLowest 5 markets:")
        print(market_prices.tail(5))

    if "arrival_date" in df.columns:

        daily = (
            df.dropna(subset=["arrival_date"])
            .groupby("arrival_date")["modal_price"]
            .mean()
            .sort_index()
        )

        daily_change = daily.pct_change() * 100

        print("\nDaily average modal prices:")
        print(daily)

        print("\nDaily percentage changes:")
        print(daily_change.round(2))


# ==========================================
# 7. FETCH ALL FOUR COMBINATIONS
# ==========================================

def main():

    combinations = [
        ("Rajasthan", "Wheat"),
        ("Rajasthan", "Mustard"),
        ("Uttar Pradesh", "Wheat"),
        ("Uttar Pradesh", "Mustard")
    ]

    all_data = []

    for state, commodity in combinations:

        df = fetch_mandi_data(
            state=state,
            commodity=commodity,
            limit=100
        )

        if df.empty:
            continue

        df = clean_data(df)

        df["requested_state"] = state
        df["requested_commodity"] = commodity

        filename = (
            f"{state.replace(' ', '_')}_"
            f"{commodity.lower()}_prices.csv"
        )

        output_path = os.path.join(
            OUTPUT_FOLDER,
            filename
        )

        df.to_csv(output_path, index=False)

        print("\nSaved:", output_path)

        analyze_prices(df, state, commodity)

        all_data.append(df)

        time.sleep(2)

    # ======================================
    # 8. COMBINE ALL DATA
    # ======================================

    if all_data:

        combined_df = pd.concat(
            all_data,
            ignore_index=True
        )

        combined_path = os.path.join(
            OUTPUT_FOLDER,
            "all_mandi_prices.csv"
        )

        combined_df.to_csv(
            combined_path,
            index=False
        )

        print("\n" + "=" * 55)
        print("ALL DATA FETCHED SUCCESSFULLY")
        print("=" * 55)

        print("Total records:", len(combined_df))
        print("Combined file:", combined_path)

    else:

        print("\nNo data could be fetched.")
        print("Check API availability, key and resource ID.")


# ==========================================
# 9. RUN PROJECT
# ==========================================

if __name__ == "__main__":
    main()
