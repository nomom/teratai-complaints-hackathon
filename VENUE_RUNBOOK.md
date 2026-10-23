# Venue runbook (Day 2, 2026-10-23)

Everything to set up and test at the venue so the organisers can reach our API, written the night before
(2026-10-22, 23:00) so no context is lost. Requirements: [README](README.md) "The live round", [docs/api.md](docs/api.md),
[docs/scoring.md](docs/scoring.md). Team plan: [TEAM.md](TEAM.md), [END_GOAL.md](END_GOAL.md).

**Day 2 timeline**

| Time | What |
|---|---|
| 12:00 | **Checkpoint 2:** `scoring/api_check.py` passes against our API, and the organisers reach it from their laptop |
| 15:00 | **Agent and API freeze.** PR `Submission: Claude the Destroyer` with `predictions.csv`, the **freeze commit hash** and the **API URL**. The API must be running |
| 15:00–15:45 | **Hidden test:** their script sends 20 unseen, messy complaints to our API at once (120 s each). Don't touch anything |
| until 16:30 | UI and ops platform may still change; the agent and API may not |
| 16:30 | **Demo**, about 10 min, including the **human gate**: judges send 3 complaints to our API, one at a time, and watch |

## 1. Where things stand (2026-10-22, 23:15)

| Thing | State |
|---|---|
| `main` | Everything merged: the React dashboard (Clement), the organisers' latest changes (`docs/api.md`, `scoring/api_check.py`), and the live-round API (B). `run.bat` / `run.sh` start worker + API + React dashboard (http://localhost:5173) |
| Tests | 114 Python tests (offline) and 31 React tests pass. `api_check.py` against the merged API, LLM on: **100.0, 10/10 states, 9/9 probes**; earlier with 20 at once: **100.0, 20/20, 9/9, slowest 22.9 s** |
| Working folder | Someone's **uncommitted OpenRouter provider** (`agent/llm.py`, `agent/extract.py`, `.env.example`, `MODEL_EVAL.md`, `scripts/run_batch.py`, `tests/test_llm.py`). Not B's, never committed by B: ask the team whose it is |
| `submissions/Claude the Destroyer/predictions.csv` | Run 3 (LLM, 750/750, valid). Untracked. **Regenerate from the final main before submitting** |
| Model | OpenAI `gpt-5.6-luna` in `.env`: about 3.8 s and $0.0007 per complaint ([MODEL_EVAL.md](MODEL_EVAL.md)) |

## 2. How the API serves both the dashboard and the organisers (merged 2026-10-22)

| Endpoint | With a login token (the React dashboard) | Without a token (the organisers, the judges) |
|---|---|---|
| `GET /cases/{id}` | Role view, as before: full record + summary for staff (404 until the worker stores it, 403 outside the role's queue); customer view for customers | Contract view: `status` (`processing` / `done` / `error`), decision, `self_check`, `case_state`, `sent`, `human_action`; 404 if never seen |
| `POST /complaints` | Signed-in staff may leave `complaint_id` empty: `LIVE-xxxxxxxx` is made up | All of `complaint_id`, `customer_id`, `received_at`, `text` required (422); duplicate id returns the existing case (200) |
| `POST /cases/{id}/actions`, `GET /health` | – | Open, as `docs/api.md` requires |
| `/cases`, `/cases/counts`, `/approve`, `/reject`, `/flag`, `/me/complaints`, `/stats` | Login, unchanged | 401 |

A token that is sent but invalid is a 401, never treated as "no login". `run.bat` starts the API without
`--host 0.0.0.0`: fine behind a tunnel; for same-Wi-Fi access start the API by hand (section 4, option B).
Clement: please review (`app/api.py`, `app/UserAccessControl/deps.py`, and the offline guard added to the top of
`tests/test_access_control.py`, `tests/test_api.py`, `tests/test_worker.py`: without it the suite read `.env` and called
the real LLM).

## 2b. Load and concurrency (measured 2026-10-22 night, `scripts/load_test.py`)

The API only validates and queues (`inbox/`, a durable file queue); the worker decides in the background, several at
a time; clients poll `GET /cases/{id}`. Settings: `WORKERS` (default 16 complaints at once), `MAX_BACKLOG` (default
200 waiting; beyond it `POST /complaints` answers `503` + `Retry-After: 15` instead of accepting work that would miss
the 120 s), `API_THREADS` (default 100 requests in flight). The case store runs in SQLite WAL mode (reads don't wait
for writes); the customer list is read once.

| Test (laptop, all at once) | Before hardening | After hardening |
|---|---|---|
| 50 complaints, LLM on | slowest **35.1 s**, median 20.8 s, 1.4/s, 50/50 right | slowest **20.7 s**, median 12.3 s, **2.4/s**, 50/50 right, no rate limits |
| 2,000 complaints, rules only, 128 clients | POST median 1.6 s (max 3.8 s), slowest done 6.0 s, 30/s | POST median **1.2 s** (max 2.9 s), slowest done **5.0 s**, **38/s** |
| 500 complaints, rules only, 64 clients | POST median 194 ms, slowest done 3.6 s | POST median 96 ms, slowest done 3.4 s |
| Worker stalled, 260 posted | (no limit: all accepted, then time out) | **200 accepted, 60 refused with 503 + Retry-After**; queue drained in ~13 s after restart |

In every run: 0 server errors, 0 lost complaints, every decided case correct against the labels; the API stays healthy.
Rough capacity with the LLM: about 2.4 complaints/s, so a burst of ~250 still finishes within 120 s (the live round
sends 20). The load test also found a race in the parallel worker (a file finished between listing and hand-out was
taken twice and logged as a false failure, 2 in 1,000); fixed and tested.

Run it yourself (any URL; it uses fresh ids, so it doesn't touch existing cases):
`uv run python -m scripts.load_test <URL> --n 50 --threads 50` (LLM on costs about $0.0007 per complaint).

## 3. Start the system for the live round

On the laptop that will serve the organisers. **Run these in your own windows, not from Claude Code** (its background
processes can be stopped when memory runs low, which happened on 2026-10-22). Close Excel and other heavy apps.

```powershell
git switch main; git pull; uv sync
# A fresh case store, so the judges' cases aren't buried among 2,500 old ones; set before run.bat so its windows inherit it
$env:CASE_DB = "runtime/live.db"; $env:BACKFILL = "0"
.\run.bat                                   # worker, API (port 8000), React dashboard (http://localhost:5173)
```

Check the LLM is really on: submit one complaint, open its "How the agent decided" section: the source must be `llm`,
not `rules (llm failed: ...)`. Or:

```powershell
uv run python -c "from agent import llm; print(llm.PROVIDER, llm.MODEL, llm.enabled())"
```

## 4. Make the API reachable

**Option A: tunnel (recommended; works whatever the venue Wi-Fi does).**
```powershell
winget install --id Cloudflare.cloudflared         # once (a download: confirm first)
cloudflared tunnel --url http://localhost:8000     # prints https://<something>.trycloudflare.com
```
The address changes every time the tunnel restarts: start it once, put that address in the PR, never close it. (ngrok:
`ngrok http 8000`, needs a free account.)

**Option B: same venue Wi-Fi.**
1. Start the API listening on all interfaces (instead of run.bat's API window):
   `uv run python -m uvicorn app.api:app --host 0.0.0.0 --port 8000`
2. In an **administrator** PowerShell, run once (a security setting: you run it):
   `New-NetFirewallRule -DisplayName "Teratai API" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow`
3. `ipconfig` → Wi-Fi IPv4 (ignore `vEthernet (WSL ...)`). The URL is `http://<that IP>:8000`.

Risks: many venues block laptops from reaching each other, and the IP can change after reconnecting.

## 5. Test it the way the organisers will

1. **On the serving laptop:**
   `uv run python scoring/api_check.py http://localhost:8000 --n 20`
   Expect all probes PASS, all 20 done, slowest well under 120 s.
2. **From another laptop (a teammate's) or a phone:** open `<URL>/health` in a browser (expect `{"ok":true}`), then
   on the teammate's laptop: `python scoring/api_check.py <URL> --n 20`.
3. **Human gate rehearsal:** send one complaint through the URL and watch it appear in the dashboard:
   `curl.exe -X POST <URL>/complaints -H "Content-Type: application/json" --data "@examples/live_complaint_example.json"`
   (that example is already a training complaint; for repeats change `complaint_id`, e.g. `LIVE-T1`, `LIVE-T2`).
4. **The live round through the tunnel:** `uv run python -m scripts.load_test <URL> --n 20 --threads 20`
   (20 at once over the public URL, as the hidden test does; about $0.015 with the LLM). Expect 20/20 done, 20/20
   correct, slowest well under 120 s. Do this before 12:00, so there is time to switch to LAN or a hotspot.
5. Record the URL and the results here (section 8).

## 6. Before 15:00: freeze and submit

1. Everything merged on `main`, both test suites pass, `api_check` passes against the URL.
2. Regenerate the predictions from the final `main` (LLM on, about 6½ min, about $0.52):
   `uv run python -m scripts.run_batch --split test --team "Claude the Destroyer"`
   Check `750/750`, no `LLM failures by kind` line, `intents: {'COMPLAINT': 750}`.
3. Commit it on a submission branch (`team/claude-the-destroyer`), push to the fork, open the PR to
   `DM-Data-Science/teratai-complaints-hackathon` titled `Submission: Claude the Destroyer`. PR description:
   the freeze commit hash (`git rev-parse HEAD` on main at 15:00) and the API URL.
4. **From 15:00 to the end of the demo:** don't restart the worker, the API or the tunnel; laptop on power, sleep off,
   don't reconnect the Wi-Fi. Watch the worker window for `FAILED` lines.

## 7. Demo (16:30)

Human gate checklist per complaint: the case appears on its own; right transaction, decision and refund; right route;
an approval case waits until we approve it (`case_state: awaiting_approval`, `sent: false`); a fraud case lands in the
fraud queue; reply in the right language and consistent; self-check visible. Plan in [END_GOAL.md](END_GOAL.md),
section 4. Optional: `scripts/demo_bad_drafts.py` (instead of the worker, briefly) shows the self-check catching the
agent's own bad draft.

## 8. Results at the venue (fill in)

| Check | Result |
|---|---|
| API URL given to the organisers | `http://10.0.30.141:8000` (venue Wi-Fi `DM-office 3`, `run_live.bat`; no firewall change needed: Python312 already allowed on Public) |
| `api_check` (20) on the Wi-Fi URL from the serving laptop | **100.0**, 20/20 states, 0 critical, 9/9 probes, median 8.5 s, slowest 12.6 s (2026-10-23 morning) |
| `api_check` from another laptop | |
| `load_test --n 20` on the Wi-Fi URL | 20/20 done and correct, POST max 318 ms, slowest 10.4 s; 40/40 cases LLM-read, no LLM failures |
| Checkpoint 2 confirmed by the organisers | |
| Freeze commit hash | |
| PR link | |

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `/health` works on the laptop, not from elsewhere | API not on `--host 0.0.0.0`, firewall rule missing, or venue isolates clients: use the tunnel |
| Cases stay `processing` | Worker not running, or it and the API use different `CASE_DB`: set `CASE_DB` before starting both |
| Decisions look rule-based, messy complaints wrong | LLM off or failing: check `.env`, and a case's extraction source (`rules (llm failed: <kind>)`) |
| 401 on `GET /cases/{id}` without a token | The merge in section 2 isn't in: that endpoint must answer without credentials |
| Duplicate `POST` gives a different decision | Not expected: the API returns the existing case and the worker never reprocesses one |
| Background processes vanish | Memory: close heavy apps; start the three processes from your own terminals |

## For Claude, when the team says "we're at the venue"

1. `git fetch`; `git pull` on main; read this file and section 8; check `git status` (whose uncommitted work is there).
2. Run both test suites: `uv run python -m unittest discover tests` and `npm test` in `web/` (after `npm ci`).
3. Smoke-test the LLM with one complaint.
4. Have the user start the three processes (section 3) and the tunnel (section 4), in their own windows.
5. Run `api_check` on localhost, then against the public URL; have a teammate run it from another laptop.
6. Fill in section 8. Before 15:00: section 6 (regenerate predictions, submission branch, PR text with hash and URL).
