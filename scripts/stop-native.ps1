# Stops ProfilePilot's native (no-Docker) processes: API (:8000), web (:3000),
# the worker (matched by command line), and PostgreSQL.

$root = Split-Path -Parent $PSScriptRoot

foreach ($port in 8000, 3000) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Write-Output "Stopping process on port $port (PID $($c.OwningProcess))"
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match "app\.main" -and $_.CommandLine -notmatch "uvicorn" } |
    ForEach-Object {
        Write-Output "Stopping worker (PID $($_.ProcessId))"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

$pg = "$root\.runtime\pg16\pgsql"
$pgdata = "$root\.runtime\pgdata"
if (Test-Path $pgdata) {
    Write-Output "Stopping PostgreSQL..."
    & "$pg\bin\pg_ctl.exe" -D $pgdata stop -m fast
}
