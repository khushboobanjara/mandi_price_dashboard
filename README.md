# Rajasthan Mandi Price Analysis Dashboard

A data-driven web application for tracking, analyzing, and comparing daily Wheat and Mustard mandi prices across Rajasthan, India.

The platform collects mandi price data through an API, stores historical records in MySQL, and presents interactive market insights through a web dashboard.

## Project Overview

The Rajasthan Mandi Price Analysis Dashboard helps users understand agricultural market trends through daily price monitoring, market comparisons, historical analysis, and automated data collection.

### Key Features

- **Automated Data Collection:** Fetches Rajasthan Wheat and Mustard mandi prices.
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
**Commodities:** Wheat and Mustard  
**Price Unit:** Indian Rupees per quintal (100 kg)

Data availability and freshness depend on the API provider.

## Project Architecture

```text
data_finding/
│
├── app/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   │
│   ├── routes/
│   │
│   ├── services/
│   │
│   └── scheduler.py
│
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   ├── js/
│   │   └── dashboard.js
│   └── assets/
│
├── tests/
│
├── data/
├── output/
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

*Adjust the structure above to match the actual files in your project.*

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

### 6. Start the backend

```powershell
uvicorn app.main:app --reload --port 8000
```

Backend URL:

`http://localhost:8000`

API documentation:

`http://localhost:8000/docs`

### 7. Open the dashboard

If the frontend is served through FastAPI, open:

`http://localhost:8000`

Otherwise, follow the frontend instructions in the project configuration.

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

## API Endpoints

The following are example endpoint categories. Refer to `/docs` for the actual implemented routes.

| Endpoint | Purpose |
|---|---|
| `/docs` | Interactive API documentation |
| `/health` | Application health check |
| `/api/prices` | Retrieve mandi price records |
| `/api/analytics` | Retrieve price analytics |
| `/api/refresh` | Trigger manual data refresh |
| `/api/export` | Export filtered records |

## Testing

Run the test suite:

```powershell
python -m pytest tests -v
```

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