# Start the Vite dev server. Open http://localhost:5173
# (Use "localhost", not "127.0.0.1" — Vite binds the loopback name, which
# resolves to IPv6 ::1 on Windows.)
$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot 'frontend')
try {
    if (-not (Test-Path 'node_modules')) { throw 'node_modules missing. Run .\setup.ps1 first.' }
    npm run dev
} finally {
    Pop-Location
}
