@echo off
rem Teratai complaints agent: start the live-round system on the venue Wi-Fi (see VENUE_RUNBOOK.md).
rem Like run.bat, but: a fresh case store (runtime\live.db, no backfill of the 2,500 training complaints), and the API
rem listens on all interfaces so the organisers can reach it on the same Wi-Fi at http://<this laptop's IP>:8000.
rem Run run.bat once first if the packages aren't installed yet. Close the three windows to stop.
setlocal
cd /d "%~dp0"

rem Inherited by the three windows below: the worker and the API must use the same case store.
set "CASE_DB=runtime/live.db"
set "BACKFILL=0"

echo Starting the worker, the API (on all interfaces) and the dashboard...
start "Teratai worker (live)" cmd /k uv run --no-sync python -m app.worker
start "Teratai API (live)" cmd /k uv run --no-sync python -m uvicorn app.api:app --host 0.0.0.0 --port 8000
start "Teratai dashboard" /d web cmd /k npm run dev -- --strictPort

timeout /t 8 /nobreak >nul
start "" http://localhost:5173

echo.
echo Case store: %CASE_DB%   (backfill off)
echo API URL for the organisers (Wi-Fi address of this laptop):
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi' -ErrorAction SilentlyContinue | ForEach-Object { '   http://' + $_.IPAddress + ':8000' }"
echo Check it from another laptop on the same Wi-Fi: open that URL followed by /health, expect {"ok":true}
echo Dashboard: http://localhost:5173
echo.
echo Keep this laptop plugged in, awake and on the same Wi-Fi: if it reconnects, the address can change.
echo.
pause
endlocal
