# Start the FastAPI backend. Interactive docs at http://localhost:8000/docs
$ErrorActionPreference = 'Stop'
$vpy = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $vpy)) { throw 'Virtual environment missing. Run .\setup.ps1 first.' }
Push-Location (Join-Path $PSScriptRoot 'backend')
try {
    & $vpy -m uvicorn app.main:app --reload --port 8000
} finally {
    Pop-Location
}
