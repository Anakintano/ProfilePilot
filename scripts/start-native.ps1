# Starts ProfilePilot natively on Windows (no Docker) — Postgres, API, worker, web.
# Run from anywhere: powershell -File scripts/start-native.ps1
# Stop everything with scripts/stop-native.ps1 (kills by port).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pg = "$root\.runtime\pg16\pgsql"
$pgdata = "$root\.runtime\pgdata"

if (-not (Test-Path $pgdata)) {
    Write-Error "PostgreSQL data directory not found at $pgdata — run the one-time setup in README.md first."
}

Write-Output "Starting PostgreSQL..."
& "$pg\bin\pg_ctl.exe" -D $pgdata -l "$root\.runtime\pg.log" -o "-p 5432" start
& "$pg\bin\pg_isready.exe" -h localhost -p 5432

$env:DATABASE_URL = "postgresql://profilepilot:profilepilot@localhost:5432/profilepilot"
$env:REDIS_URL = "redis://localhost:6379/0"  # not running natively; rate limiting fails open by design
$env:AUTH_MODE = "dev"
$env:STORAGE_MODE = "local"
$env:STORAGE_DIR = "$root\.runtime\uploads"
$env:MIGRATIONS_DIR = "$root\db\migrations"
$env:CORS_ORIGINS = "http://localhost:3000"
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000"

Write-Output "Starting API on :8000..."
Start-Process -WindowStyle Hidden -WorkingDirectory "$root\services\api" `
    -FilePath "$root\services\api\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"

Write-Output "Starting worker..."
Start-Process -WindowStyle Hidden -WorkingDirectory "$root\services\worker" `
    -FilePath "$root\services\worker\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "app.main"

Write-Output "Starting web on :3000..."
Start-Process -WindowStyle Hidden -WorkingDirectory "$root\apps\web" `
    -FilePath "npm.cmd" -ArgumentList "run", "dev"

Write-Output ""
Write-Output "All services starting. Web: http://localhost:3000  API: http://localhost:8000/health"
Write-Output "(API/worker/web run hidden in the background — use Task Manager or stop-native.ps1 to stop them.)"
