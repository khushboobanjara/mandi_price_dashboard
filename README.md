# Rajasthan Mandi Price Analysis Dashboard

A data-driven web application for tracking, analyzing, and comparing daily Wheat, Mustard, Bajra, Soybean and Gram (Chana) mandi prices across Rajasthan, India.

The platform collects mandi price data through an API, stores historical records in MySQL, and presents interactive market insights through a web dashboard.

## Project Overview

The Rajasthan Mandi Price Analysis Dashboard helps users understand agricultural market trends through daily price monitoring, market comparisons, historical analysis, and automated data collection.

### Key Features

- **Automated Data Collection:** Fetches Rajasthan Wheat, Mustard, Bajra, Soybean and Gram mandi prices (Rajasthan only; other states are rejected).
- **MySQL Database:** Stores historical mandi price records.
- **Duplicate Prevention:** Prevents duplicate price entries.
- **Automatic Refresh:** Scheduled data collection every 3 hours.
- **Manual Refresh:** Allows users to trigger data collection.
- **Interactive Dashboard:** Displays market insights and price analytics.
- **Price Trend Analysis:** Tracks changes in modal, minimum, and maximum prices.
- **Market Comparison:** Compares prices across different mandis.
- **Dynamic Filters:** Filter data by commodity, district, market, and date.
- **CSV Export:** Download filtered mandi price records.
- **Data Freshness Monitoring:** Displays the latest update time and API status.

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI |
| Frontend | HTML, CSS, JavaScript |
| Charts | Chart.js |
| Database | MySQL |
| ORM | SQLAlchemy |
| Data Processing | Pandas |
| API Integration | Requests |
| Scheduler | APScheduler |
| Testing | Pytest |

## Data Source

Mandi price data is retrieved through:

`https://api.dharun.dev/v1/mandi`

The provider attributes the underlying data to Agmarknet, published through India's data.gov.in platform.

**Scope:** Rajasthan  
**Commodities:** Wheat, Mustard, Bajra, Soybean, Gram (Chana, whole)  
**Price Unit:** Indian Rupees per quintal (100 kg)

Data availability and freshness depend on the API provider.

## Project Architecture

```
mandi_price_dashboard/
├── app/
│   ├── main.py            # FastAPI app, health checks, middleware, serves the frontend
│   ├── config.py, database.py, models.py, scheduler.py
│   ├── routes/dashboard.py     # /api/filters, kpis, trends, markets/compare, prices, export/csv, freshness
│   └── services/               # api_client, ingest, validation, analytics, queries
├── frontend/                   # plain HTML + CSS + vanilla JS + Chart.js (no build step)
│   ├── index.html, favicon.svg
│   ├── css/style.css
│   ├── js/ utils.js, api.js, charts.js, panels.js, app.js
│   └── vendor/chart.umd.js     # Chart.js 4.4.7, vendored (works offline)
├── scripts/ init_db.py, import_csv.py, run_dev.ps1, run_prod.ps1
├── sql/schema.sql
└── tests/
```

## Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd data_finding
```

### 2. Create a virtual environment

```powershell
python -m venv venv
venv\Scripts\activate
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure MySQL

Create the database:

```sql
CREATE DATABASE rajasthan_mandi;
```

### 5. Configure environment variables

Create a `.env` file in the project root.

Example:

```env
DATABASE_URL=mysql+pymysql://YOUR_USERNAME:YOUR_PASSWORD@localhost:3306/rajasthan_mandi
```

Use your actual database credentials locally. Never commit `.env` to GitHub.

### 6. Start the server (API + dashboard together)

```powershell
.\scripts\run_dev.ps1
```

or, without the helper script:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

Backend URL:

`http://localhost:8000`

API documentation:

`http://localhost:8000/docs`

### 7. Open the dashboard

The dashboard is served by FastAPI itself (no Node/Vite needed). Open:

`http://localhost:8000`



## Dashboard Analytics

The dashboard is designed to provide:

- Average modal price
- Lowest minimum price
- Highest maximum price
- Reporting market count
- Price percentage change
- Historical price trends
- Market-wise and district-wise comparisons
- Filtered mandi price records
- Commodity-wise comparison (latest prices, history in ₹ or rebased index)
- District-wise analysis for one commodity, and a district × commodity matrix
- MSP comparison: price vs Minimum Support Price per commodity, and which markets/districts are below it
- CSV reports: commodity summary, district analysis, MSP comparison, price history

Commodities with no data are shown as "no data" (never zero or guessed), and an MSP is shown only when one
is on record for the price date.

## MSP (Minimum Support Price)

MSP is stored in the `msp_rates` table (created and seeded automatically on startup, or with
`python -m scripts.init_db`). A price is compared with the MSP of the marketing season its date falls in:
rabi crops (Wheat, Mustard, Gram) 1 Apr–31 Mar, kharif crops (Bajra, Soybean) 1 Oct–30 Sep.
Built-in values: RMS 2024-25 to 2027-28 (rabi) and KMS 2025-26, 2026-27 (kharif; Bajra = hybrid, Soybean = yellow).
When a new MSP is announced, add one row, no code change:

```sql
INSERT INTO msp_rates (commodity, season, applies_from, applies_to, msp, source)
VALUES ('Bajra', 'KMS 2027-28', '2027-10-01', '2028-09-30', 0 /* announced value */, 'CCEA approval, <date>');
```

Rows in the table override the built-in values for the same commodity and season. MSP applies to government
procurement; mandi prices are shown against it for reference.

## Data accuracy rules

- Rajasthan only; rows for other states are rejected.
- A row must belong to the commodity that was requested (Gram never receives Gram Dal, Black Gram or Wheat rows).
- API spellings ("Soyabean", "Bajra(Pearl Millet/Cumbu)", "Bengal Gram(Gram)(Whole)") are stored under one canonical name.
- Prices outside a wide plausible range per commodity (possible ₹/kg or ₹/ton unit errors) are rejected.
- Duplicates are prevented by a unique hash of date, state, district, market, commodity, variety and grade.
- A commodity the API has nothing for is noted in the refresh log without failing the refresh; an API error makes it "partial".

## API Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /` | The dashboard |
| `GET /docs` | Interactive API docs (disable with `DOCS_ENABLED=false`) |
| `GET /health` | Full status: database, scheduler, data freshness, version, uptime |
| `GET /health/live` | Liveness probe (never touches MySQL) |
| `GET /health/ready` | Readiness probe (503 if MySQL or scheduler is down) |
| `GET /api/filters`, `/api/kpis`, `/api/trends`, `/api/markets/compare` | Dashboard analytics (KPIs and trends now include MSP) |
| `GET /api/commodities` | The five commodities with data availability |
| `GET /api/compare/commodities`, `/api/compare/trends` | Cross-commodity comparison and history (ignore the `commodity` filter) |
| `GET /api/districts/analysis` (needs `commodity`), `/api/districts/matrix` | District-wise analysis |
| `GET /api/msp`, `/api/msp/breakdown` (needs `commodity`) | MSP comparison |
| `GET /api/export/report?kind=commodity_summary\|district_analysis\|msp\|history` | CSV reports |
| `GET /api/prices` | Sortable, paginated price records |
| `GET /api/export/csv` | CSV export of the current filters |
| `GET /api/freshness`, `/api/refresh/status`, `/api/fetch-logs` | Data freshness and refresh history |
| `POST /api/refresh` | Manual refresh (409 if one is running, 429 during the cooldown) |

## Testing

Run the test suite:

```powershell
python -m pytest tests -v
```

Tests that need no database server run against in-memory SQLite (see `tests/conftest.py`).

## Future Enhancements

- Machine learning-based mandi price forecasting
- Seasonal price trend analysis
- Commodity demand and supply analysis
- Market-wise price alerts
- District-level agricultural insights
- Advanced statistical reporting
- Cloud deployment and production monitoring

## Project Objective

The objective is to build a reliable agricultural market analytics platform that transforms mandi price data into meaningful insights and supports better data-driven decision