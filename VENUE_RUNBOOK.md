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

## 1. Where things stand (2026-10-22, 23:00)

| Thing | State |
|---|---|
| `origin/main` (`4b73e2a`, Clement) | React dashboard in `web/` replaces Streamlit (`app/ui.py` deleted); `run.bat` / `run.sh` start worker + API + dashboard. **Does not have** the organisers' latest changes (`docs/api.md`, `scoring/api_check.py`) |
| `b/api-contract` (`4aa8886`, B) | The organisers' upstream changes merged, plus the live-round API to the contract. Tested: `api_check.py`, 20 at once, LLM on: **100.0, 20/20 states, 9/9 probes, slowest 22.9 s**. **Not merged into main** (see 2) |
| Working folder | Someone's **uncommitted OpenRouter provider** (`agent/llm.py`, `agent/extract.py`, `.env.example`, `MODEL_EVAL.md`, `scripts/run_batch.py`, `tests/test_llm.py`). Not B's, never committed by B: ask the team whose it is |
| `submissions/Claude the Destroyer/predictions.csv` | Run 3 (LLM, 750/750, valid). Untracked. **Regenerate from the final main before submitting** |
| Model | OpenAI `gpt-5.6-luna` in `.env`: about 3.8 s and $0.0007 per complaint ([MODEL_EVAL.md](MODEL_EVAL.md)) |

## 2. Merge `b/api-contract` into main (before the venue tests)

The React dashboard and the contract both use `GET /cases/{id}` and `POST /complaints`, differently:

| Endpoint | React (Clement, with a login token) | Contract (organisers, no credentials) | Resolution |
|---|---|---|---|
| `GET /cases/{id}` | Full staff view (record + summary), role-filtered (403 for another team's case), customer view for customers | Contract view: `status`, decision, `self_check`, `case_state`, `sent`, `human_action` | **With an `Authorization` header: the role view, unchanged. Without one: the contract view.** Drop `/cases/{id}/record` (no longer needed) |
| `POST /complaints` | Staff form may leave `complaint_id` empty and expects one to be generated | `complaint_id` required: empty is a 422 | **Signed-in staff with an empty id: generate one** (`LIVE-xxxxxxxx`). No token: the contract rules (422) |
| Other | `/me/complaints`, `/cases/counts`, `/approve`, `/reject`, `/flag` (login) | `/cases/{id}/actions`, `/health` (no login) | Keep all |

Also on merge:
- `app/api.py` changed on both sides: resolve by hand. Keep Clement's endpoints and add the contract ones.
- Run **both** test suites: `uv run python -m unittest discover tests` (includes Clement's `tests/test_api.py` and B's `tests/test_api_contract.py`) and the React tests in `web/` (`npm test`).
- `TEAM.md` / `END_GOAL.md` still mention Streamlit: update to the React dashboard (`run.bat`, http://localhost:5173).
- `run.bat` starts the API with `--port 8000` only (listens on this laptop only). That's fine with a tunnel; for same-Wi-Fi access the API needs `--host 0.0.0.0` (see 4).
- Tell Clement first: the contract endpoints are open by design (the organisers' calls carry no credentials).

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
4. Record the URL and the `api_check` results here (section 8).

## 6. Before 15:00: freeze and submit

1. All merges done on `main`, tests pass, `api_check` passes against the URL.
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
| API URL given to the organisers | |
| `api_check` on localhost (20) | |
| `api_check` from another laptop | |
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

1. `git fetch`; read this file and section 8; check `git status` (whose uncommitted work is there).
2. If section 2 isn't merged yet: do the merge on a branch with the resolutions above, run both test suites, then merge.
3. Smoke-test the LLM with one complaint.
4. Have the user start the three processes (section 3) and the tunnel (section 4), in their own windows.
5. Run `api_check` on localhost, then against the public URL; have a teammate run it from another laptop.
6. Fill in section 8. Before 15:00: section 6 (regenerate predictions, submission branch, PR text with hash and URL).
