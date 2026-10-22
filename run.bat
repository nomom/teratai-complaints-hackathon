@echo off
rem Teratai complaints agent: one-click setup and start on Windows.
rem Double-click this file, or run "run.bat" from a terminal in the repo root.
rem It installs uv if it is missing, installs the Python and web packages, creates .env from .env.example on the
rem first run, and starts the worker, the API and the React dashboard, each in its own window.
setlocal
cd /d "%~dp0"

rem 1. uv (installs Python 3.12 and the packages from uv.lock)
where uv >nul 2>&1
if errorlevel 1 (
    echo uv is not installed. Installing uv...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
where uv >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: uv could not be installed. Install it by hand with "pip install uv", then run this file again.
    pause
    exit /b 1
)

rem 2. Node.js (runs the React dashboard in web/). Vite needs Node 20.19 or newer.
where node >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Node.js is not installed. The dashboard needs it.
    echo Install the LTS version from https://nodejs.org or with "winget install OpenJS.NodeJS.LTS",
    echo then open a new terminal and run this file again.
    pause
    exit /b 1
)
node -e "const [a,b]=process.versions.node.split('.').map(Number); process.exit(a>20 || (a===20 && b>=19) ? 0 : 1)"
if errorlevel 1 (
    echo.
    echo ERROR: Node.js 20.19 or newer is needed. Install the LTS version from https://nodejs.org, then run this file again.
    node --version
    pause
    exit /b 1
)

rem 3. Python packages: creates or updates .venv from uv.lock
echo Installing Python packages...
uv sync
if errorlevel 1 (
    echo.
    echo ERROR: "uv sync" failed. Read the message above.
    pause
    exit /b 1
)

rem 4. Web packages: creates or updates web\node_modules from package-lock.json.
rem "call" is needed because npm is a .cmd script; without it, this file stops after npm.
echo Installing web packages...
pushd web
call npm install --no-audit --no-fund
if errorlevel 1 (
    popd
    echo.
    echo ERROR: "npm install" failed. Read the message above.
    pause
    exit /b 1
)
popd

rem 5. .env: copied from .env.example on the first run only
if not exist .env (
    copy .env.example .env >nul
    echo.
    echo Created .env from .env.example.
    echo To use the LLM, open .env and fill in ANTHROPIC_API_KEY, then run this file again.
    echo To run without the LLM, set LLM_PROVIDER= to an empty value. The rules and templates still work.
    echo.
    pause
)

rem 6. Start the three processes. --no-sync: the packages were installed in step 3.
rem --strictPort: if port 5173 is busy, the dashboard stops with an error instead of moving to another port.
echo Starting the worker, the API and the dashboard...
start "Teratai worker" cmd /k uv run --no-sync python -m app.worker
start "Teratai API" cmd /k uv run --no-sync python -m uvicorn app.api:app --port 8000
start "Teratai dashboard" /d web cmd /k npm run dev -- --strictPort

rem Give the dashboard a few seconds to start, then open it in the browser.
timeout /t 8 /nobreak >nul
start "" http://localhost:5173

echo.
echo Dashboard: http://localhost:5173
echo API docs:  http://localhost:8000/docs
echo.
echo Staff logins (password 1234): officer1 (approval queue), fraud1 (fraud queue), manager1 (everything)
echo Customers sign up with their customer ID, for example CUS-00150.
echo.
echo To stop: close the three windows named "Teratai worker", "Teratai API" and "Teratai dashboard".
echo.
pause
endlocal
