# OpsGenie AI — one-shot setup (Windows PowerShell).
#
#   .\setup.ps1
#
# Creates the Python venv, installs both dependency sets, trains the three
# models and seeds the database. Takes a few minutes on a laptop; after this,
# .\start-backend.ps1 and .\start-frontend.ps1 are all you need.

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Step($n, $text) { Write-Host "`n[$n] $text" -ForegroundColor Cyan }

Step 1 'Checking prerequisites'
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { throw 'python not found on PATH. Install Python 3.11+ and re-run.' }
$node = (Get-Command node -ErrorAction SilentlyContinue)
if (-not $node) { throw 'node not found on PATH. Install Node 18+ and re-run.' }
Write-Host "    python $(python --version 2>&1)"
Write-Host "    node   $(node --version)"

Step 2 'Creating the Python virtual environment'
$venv = Join-Path $root 'backend\.venv'
if (-not (Test-Path $venv)) { python -m venv $venv }
$vpy = Join-Path $venv 'Scripts\python.exe'

Step 3 'Installing backend dependencies'
& $vpy -m pip install --quiet --upgrade pip
& $vpy -m pip install --quiet -r (Join-Path $root 'backend\requirements.txt')

Step 4 'Copying .env templates (existing files are left alone)'
foreach ($pair in @(
    @{ src = 'backend\.env.example';  dst = 'backend\.env' },
    @{ src = 'frontend\.env.example'; dst = 'frontend\.env' }
)) {
    $dst = Join-Path $root $pair.dst
    if (-not (Test-Path $dst)) { Copy-Item (Join-Path $root $pair.src) $dst }
}

Step 5 'Training the four ML models (synthetic data, a few seconds)'
Push-Location (Join-Path $root 'backend')
try { & $vpy -m app.ml.train_all } finally { Pop-Location }

Step 6 'Seeding the database'
Push-Location (Join-Path $root 'backend')
try { & $vpy (Join-Path $root 'data\seed.py') --force } finally { Pop-Location }

Step 7 'Installing frontend dependencies'
Push-Location (Join-Path $root 'frontend')
try { npm install --no-fund --no-audit } finally { Pop-Location }

Step 8 'Verifying with the test suite'
& $vpy -m pytest -q

Write-Host "`nSetup complete." -ForegroundColor Green
Write-Host @'

Start the two servers in separate terminals:

  .\start-backend.ps1     ->  http://localhost:8000/docs
  .\start-frontend.ps1    ->  http://localhost:5173

Then open http://localhost:5173 and press the Simulation Control Panel
buttons in order. See DEMO.md for the presenter script.
'@
