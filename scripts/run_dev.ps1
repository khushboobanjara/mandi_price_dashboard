# Development server with auto-reload. Run from the project root:  .\scripts\run_dev.ps1
$ErrorActionPreference = "Stop"
if (-not (Test-Path .\venv\Scripts\Activate.ps1)) { throw "Create the virtualenv first: python -m venv venv" }
. .\venv\Scripts\Activate.ps1
$env:APP_ENV = "development"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
