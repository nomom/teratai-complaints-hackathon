#!/usr/bin/env bash
# Teratai complaints agent: one-command setup and start on macOS and Linux.
# Run "./run.sh" from a terminal (or "bash run.sh").
# It installs uv if it is missing, installs the Python and web packages, creates .env from .env.example on the
# first run, and starts the worker, the API and the React dashboard in this terminal. Ctrl+C stops all three.
set -euo pipefail
cd "$(dirname "$0")"

# 1. uv (installs Python 3.12 and the packages from uv.lock)
if ! command -v uv >/dev/null 2>&1; then
    echo "uv is not installed. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
if ! command -v uv >/dev/null 2>&1; then
    echo
    echo "ERROR: uv could not be installed. Install it by hand with \"pip install uv\", then run this file again."
    exit 1
fi

# 2. Node.js (runs the React dashboard in web/). Vite needs Node 20.19 or newer.
if ! command -v node >/dev/null 2>&1; then
    echo
    echo "ERROR: Node.js is not installed. The dashboard needs it."
    echo "Install the LTS version from https://nodejs.org (macOS: \"brew install node\"), then run this file again."
    exit 1
fi
if ! node -e "const [a,b]=process.versions.node.split('.').map(Number); process.exit(a>20 || (a===20 && b>=19) ? 0 : 1)"; then
    echo
    echo "ERROR: Node.js 20.19 or newer is needed (you have $(node --version)). Install the LTS version from https://nodejs.org."
    exit 1
fi

# 3. Python packages: creates or updates .venv from uv.lock
echo "Installing Python packages..."
uv sync

# 4. Web packages: creates or updates web/node_modules from package-lock.json
echo "Installing web packages..."
(cd web && npm install --no-audit --no-fund)

# 5. .env: copied from .env.example on the first run only
if [ ! -f .env ]; then
    cp .env.example .env
    echo
    echo "Created .env from .env.example."
    echo "To use the LLM, open .env and fill in ANTHROPIC_API_KEY, then run this file again."
    echo "To run without the LLM, set LLM_PROVIDER= to an empty value. The rules and templates still work."
    echo
    read -r -p "Press Enter to continue..."
fi

# 6. Start the three processes. --no-sync: the packages were installed in step 3.
# --strictPort: if port 5173 is busy, the dashboard stops with an error instead of moving to another port.
# When this script ends (Ctrl+C or an error), stop every process it started.
trap 'echo; echo "Stopping..."; kill $(jobs -p) 2>/dev/null; wait 2>/dev/null' EXIT
trap 'exit 130' INT TERM

echo "Starting the worker, the API and the dashboard..."
uv run --no-sync python -m app.worker &
uv run --no-sync python -m uvicorn app.api:app --port 8000 &
(cd web && exec npm run dev -- --strictPort) &

# Give the dashboard a few seconds to start, then open it in the browser.
sleep 8
if command -v open >/dev/null 2>&1; then
    open http://localhost:5173
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open http://localhost:5173 >/dev/null 2>&1 || true
fi

echo
echo "Dashboard: http://localhost:5173"
echo "API docs:  http://localhost:8000/docs"
echo
echo "Staff logins (password 1234): officer1 (approval queue), fraud1 (fraud queue), manager1 (everything)"
echo "Customers sign up with their customer ID, for example CUS-00150."
echo
echo "To stop: press Ctrl+C in this terminal."
echo

# Stay in the foreground until one process stops or Ctrl+C is pressed.
wait -n 2>/dev/null || wait
