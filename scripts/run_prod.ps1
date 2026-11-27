# Production-style server (no reload). Run from the project root:  .\scripts\run_prod.ps1
# IMPORTANT: keep a SINGLE worker. The 3-hour APScheduler job and the refresh lock live inside the process,
# so multiple workers would each run their own scheduler and refresh the upstream API several times.
$ErrorActionPreference = "Stop"
. .\venv\Scripts\Activate.ps1
$env:APP_ENV = "production"
$env:DOCS_ENABLED = "false"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --log-level info
