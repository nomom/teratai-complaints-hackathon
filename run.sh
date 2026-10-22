#!/usr/bin/env bash
# Teratai complaints agent: one-command setup and start on macOS and Linux.
# Run "./run.sh" from a terminal (or "bash run.sh").
# It installs uv if it is missing, installs the packages, creates .env from .env.example on the first run,
# and starts the worker, the API and the dashboard in this terminal. Ctrl+C stops all three.
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

# 2. Packages: creates or updates .venv from uv.lock
echo "Installing packages..."
uv sync

# 3. .env: copied from .env.example on the first run only
if [ ! -f .env ]; then
    cp .env.example .env
    echo
    echo "Created .env from .env.example."
    echo "To use the LLM, open .env and fill in ANTHROPIC_API_KEY, then run this file again."
    echo "To run without the LLM, set LLM_PROVIDER= to an empty value. The rules and templates still work."
    echo
    read -r -p "Press Enter to continue..."
fi

# 4. Start the three processes. --no-sync: the packages were installed in step 2.
# When this script ends (Ctrl+C or an error), stop every process it started.
trap 'echo; echo "Stopping..."; kill $(jobs -p) 2>/dev/null; wait 2>/dev/null' EXIT
trap 'exit 130' INT TERM

echo "Starting the worker, the API and the dashboard..."
uv run --no-sync python -m app.worker &
uv run --no-sync python -m uvicorn app.api:app --port 8000 &
uv run --no-sync python -m streamlit run app/ui.py --server.headless true --server.port 8501 &

# Give the dashboard a few seconds to start, then open it in the browser.
sleep 8
if command -v open >/dev/null 2>&1; then
    open http://localhost:8501
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open http://localhost:8501 >/dev/null 2>&1 || true
fi

echo
echo "Dashboard: http://localhost:8501"
echo "API docs:  http://localhost:8000/docs"
echo
echo "Staff logins (password 1234): officer1 (approval queue), fraud1 (fraud queue), manager1 (everything)"
echo "Customers sign up with their customer ID, for example CUS-00150."
echo
echo "To stop: press Ctrl+C in this terminal."
echo

# Stay in the foreground until one process stops or Ctrl+C is pressed.
wait -n 2>/dev/null || wait
