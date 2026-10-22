# Team guide

**What we're building towards: [END_GOAL.md](END_GOAL.md).**

One app, three owners. Every path (live demo, inbox, 750-complaint batch) runs the same `agent.pipeline.process_complaint()`.

```
inbox/*.json ─► app/worker.py ─► agent/pipeline.py ─► app/store.py (SQLite) ─► app/ui.py (queues)
  ▲  (API + UI drop files here)     │
  │                                 ├─ 1 UNDERSTAND  agent/extract.py   (B: LLM, rules fallback)
app/api.py                          ├─ 2 FIND        agent/matching.py  (A: code) + agent/dates.py
                                    ├─ 3 DECIDE      agent/policy.py    (A: code)
scripts/run_batch.py ───────────────┤─ 4 DRAFT       agent/reply.py     (B: LLM, template fallback)
  (predictions.csv + score)         ├─ 5 CHECK       agent/checks.py    (B: code)
                                    └─ 6 ROUTE       agent/policy.route + pipeline (A/C)
```

## Who owns what

| Person | Owns | Measure of done |
|---|---|---|
| **A: matching and decisions** | `agent/dates.py`, `agent/matching.py`, `agent/policy.py`, `agent/tools.py` | `run_batch --split train --oracle-category` near 100 on txn/outcome/refund |
| **B: LLM layer** | `agent/llm.py`, `agent/extract.py`, `agent/reply.py`, `agent/checks.py` | category and language near 100%; replies that read well; self-check catches bad replies |
| **C: platform and delivery** | `agent/pipeline.py`, `app/*`, `scripts/run_batch.py`, the demo | live round works end to end; test predictions submitted early |

The contracts between you are in `agent/schemas.py` (`Extraction`, `Decision`, `CaseRecord`). Change a field only after telling the other two.

## Setup

One [uv](https://docs.astral.sh/uv/) project for the whole repo: `pyproject.toml` and `uv.lock` at the root pin the exact packages (`anthropic`, `openai`, `fastapi`, `uvicorn`, `streamlit`) and Python 3.12, so all three laptops run the same thing. Install uv once with `pip install uv`, or `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`.

**Everyone, from the repo root:**

```powershell
uv sync                                              # creates/updates .venv (git-ignored) from uv.lock
uv run python -m unittest discover tests             # tests
uv run python -m scripts.run_batch --split train     # train run + score + per-category table; ends with FINAL SCORE 98.89 (LLM off)
```

`uv run` uses the root `.venv` without activating it. After a `git pull` that changes `uv.lock`, run `uv sync` again. To add a package: `uv add <package>`, then commit `pyproject.toml` and `uv.lock` together.

**The app (Person C runs it; anyone can):**

```powershell
uv run python -m app.worker                          # terminal 1: reacts to new complaints
uv run python -m streamlit run app/ui.py             # terminal 2: dashboard, http://localhost:8501
uv run python -m uvicorn app.api:app --port 8000     # optional, terminal 3: API, docs at http://localhost:8000/docs
```

Prefer an activated shell? `.\.venv\Scripts\Activate.ps1` (Windows) or `source .venv/bin/activate` (macOS/Linux), then drop the `uv run` prefix.

**LLM on:** copy `.env.example` to `.env` at the repo root and fill in your provider and key. The worker, API, dashboard and batch load it on startup; restart them after editing it. `.env` is git-ignored, so never rename it or paste keys anywhere else. With no provider set, the rules and templates run and everything still works.

```ini
# .env: Anthropic (model defaults to claude-opus-5-5)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# or OpenAI (LLM_MODEL is required)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
LLM_MODEL=<openai-model-id>
```

A variable set in the shell wins over `.env`, so `$env:LLM_PROVIDER = ""` turns the LLM off for one run (e.g. to reproduce the offline score). Tests never read `.env` and never call a real LLM.

If the LLM call fails (bad key, missing model), the pipeline falls back to the rules and templates and records `rules (llm failed: …)` as the extraction source in the case trace, so check the trace if results look rule-based.

**Common snags**

- **The activate script is blocked:** use `uv run` and skip activation, or run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
- **Don't run `uv init` again,** in the root or in a subfolder: the root project already covers the whole repo.
- **`ModuleNotFoundError: agent` or `app`:** run commands from the repo root.
- **The dashboard says "Not processed yet":** the worker (terminal 1) isn't running.
- **A typed complaint finds no transaction:** keep the received time near the transaction date (the form defaults to 2026-09-30). Test first with the examples in [END_GOAL.md](END_GOAL.md).
- **Code changes don't show up:** restart the worker after pulling.

## Where we are (offline, no LLM): train score 98.89, zero critical errors

Started at 92.16. B's rule fixes (ATM and scam phrasings, language detection) took category and reply language to 100%.

```
true category           n  category     txn  outcome  refund   prio   lang
ATM_NOT_DISPENSED     213      100%    100%     100%    100%   100%   100%
DUPLICATE_CHARGE      249      100%     96%      96%     96%   100%   100%
FAILED_TRANSFER       277      100%     96%      96%     96%   100%   100%
FEE_DISPUTE           270      100%    100%     100%    100%   100%   100%
SCAM_TRANSFER         213      100%    100%     100%    100%   100%   100%
SERVICE_QUALITY       244      100%    100%     100%    100%   100%   100%
UNAUTHORISED_CARD     284      100%     99%      99%     99%   100%   100%
```

The remaining gap is all transaction matching:

1. **A:** 23 `NO_MATCH` flags and about 4% wrong transactions on duplicates and failed transfers. Read `submissions/our-team/predictions_train_details.csv`.
2. **B:** the rules are tuned on training phrasings. The live round uses fresh wording, which is where the LLM has to earn its place.

## To do, by person

Tick items off in your PRs. Highest value first.

### A: matching and decisions
Goal: txn, outcome and refund near 100% with `run_batch --split train --oracle-category`.

- [ ] Fix the 23 `NO_MATCH` cases: open `predictions_train_details.csv`, run `python starter/evidence_pack.py <id>`, find what broke (date phrase, amount tolerance, card last-4)
- [ ] Fix the ~4% wrong transactions on DUPLICATE_CHARGE and FAILED_TRANSFER (several similar candidates: weigh date, amount and name better)
- [x] *(done by B, please review)* A candidate needs at least one real clue (amount, card, date, name, fee, twin), else `NO_MATCH`. Before, "My DuitNow transfer failed, please help" with no amount or date matched the customer's only transfer and auto-refunded it: no date phrase resolves to the whole window, which had counted as a date clue. No change on train or test predictions; regression test in `tests/test_core.py`
- [ ] Grow `dates.py` with the phrases you find ("minggu lepas", "awal bulan", "last weekend", ...)
- [ ] Check `fee_due()` edge cases: card opened 29 Feb, customer turning 60 the month of the fee, a fee with no matching product
- [ ] Unit tests for boundaries: refund RM500.00 vs RM500.01, age 65 on the received date, duplicates exactly 10 minutes apart

### B: LLM layer
Goal: category and language near 100%; replies a bank would send; a self-check judges can't sneak past.

- [x] **Scams classed as FAILED_TRANSFER (20, critical errors):** rule keywords added. When the LLM is on, only strong scam phrases ("safe account", "skim pelaburan", "online acquaintance"...) override its category; everyday words like "parcel" or "police" never do. Keywords match whole words only ("invest" no longer matches "investigate")
- [x] ATM complaints classed as SERVICE_QUALITY (70): "withdrew", "mengeluarkan", "did not dispense", "duit tak keluar"
- [x] Reply language (91 misses → 0): bigger EN/MS word lists; English counts only in lowercase, so names like "Shah Alam Branch" don't make Malay text MIXED. Tests in `tests/test_extract.py`
- [x] LLM measured (OpenAI `gpt-5.6-luna`). 200 train complaints: **99.25 with the LLM, 99.25 rules only**, zero critical errors, no LLM failures. 14 newly written live-round-style complaints: **LLM 14/14, rules 4/14** (rules miss ATM/fraud/fee without keywords, vague and off-topic messages). Per complaint: 2 calls, ~2,100 input + ~200 output tokens, ~4.5 s (0.5 s each with 8 workers)
- [x] Few-shot examples in the extraction prompt, picked from the confused categories (plus one vague and one off-topic message)
- [x] Language comes from `detect_language()` (the LLM called colloquial mixed text MS); hedge words before an amount ("dalam RM2200") are also read by code. Disagreements are logged in the case's `crosscheck`
- [x] Cross-check (`agent/crosscheck.py`): when the LLM's category differs from a keyword the rules matched, one "second look" call picks between the two. It sees both options unlabelled, plus what each would match in the customer's transactions, and must quote the message. A quote that isn't in the message, low confidence, or leaving a fraud category without high confidence → `CROSSCHECK_UNRESOLVED`, the officer decides
- [ ] Measure the cross-check's second look: in 214 real-LLM complaints it never triggered (LLM and rules agreed, or the rules had no keyword). Needs adversarial cases to measure fixes vs flips
- [x] Replies: the drafter only sees customer-safe facts and a plain explanation from code (`reply.customer_why`), never the internal reasons or the customer's age; Markdown is stripped; fraud replies say "under review", never "confirmed fraud"; no refund talk on service complaints. Templates use the same explanations in EN and MS
- [ ] SLA timeline in replies (`tools.sla(priority)`)
- [x] `checks.py` also rejects: transaction IDs outside this case's evidence (the starter check allows any of the customer's), the customer's age or date of birth, declaring fraud before review, refund talk with no money decision. 0 of 200 real-LLM first drafts were rejected
- [ ] Keep trying to break `checks.py` like a judge would (edited replies especially)
- [x] LLM reliability: timeouts, SDK retries, a per-complaint call/token budget, and every failure recorded by kind (`timeout`, `refusal`, `bad_json`, ...) with a fallback to rules/templates. Tests in `tests/test_llm.py` use fake clients (no key, no cost)
- [x] Intents: vague complaints get a follow-up question (the case stays open as `AWAITING_CUSTOMER` with no decision until the customer replies), off-topic messages get a polite answer (`ANSWERED`). Possible fraud never waits; after 2 unanswered follow-ups an officer takes over
- [x] Intent on real phrasing: 0 of 214 real complaints wrongly marked `NEEDS_DETAILS` or `OUT_OF_SCOPE`
- [ ] A date phrase in a customer's follow-up reply ("yesterday") is read relative to the original message time, not the reply time

### C: platform and demo
Goal: the live round works without a hitch; test predictions in early.

- [ ] `uv sync` (see Setup), run the worker + UI (+ API) for the first time, fix what breaks (they haven't been run yet)
- [ ] Push one complaint down each path: auto-resolved refund, decline → approval queue, refund > RM500 → approval queue, fraud → fraud queue. Approve and reject update the audit log
- [x] *(done by B, please review)* `store.approve` re-runs the self-check on the exact reply going out, edited or not. A failing reply is not sent: `ReplyCheckFailed` (API: `422` with the problems; dashboard: an error under the button), and an `approval_blocked` audit entry. The agent's original draft stays in the case record
- [ ] Case page clearly shows why it decided, timing per step, and cost (engineering score)
- [ ] *Optional, decide at Checkpoint 2:* a React frontend (see "Frontend: Streamlit or React" below)
- [ ] **Live-round intake:** judges hand us `complaints.csv` rows (`complaint_id, customer_id, received_at, channel, subject, text`, IDs `LIVE-01`…, received on 30 Sep 2026), which must go in with no code changes. The API already takes all six fields; the Streamlit form needs `complaint_id` and `subject` fields, and ideally a "paste a CSV row" box (or a script that drops a CSV file's rows into `inbox/`)
- [ ] Live-round test set: ~10 tricky complaints written fresh **as CSV rows in that format** (Malay, mixed, call-centre note, 65+, > RM500, scam, ambiguous). Rehearse feeding them in
- [ ] Test predictions early: `run_batch --split test --team <team-name>`, then a PR from our fork to the original repo titled `Submission: <team-name>`, well before 15:00 Day 2. Re-run as A and B improve

#### Optional: the "Best Ops Platform" award (only once the core works)
A separate award, see [docs/bonus_platform.md](docs/bonus_platform.md) and the summary in [END_GOAL.md](END_GOAL.md). In order:

- [ ] **Never overwrite the agent's decision.** `store.approve` currently replaces `reply_text` with the officer's edit. Keep the agent's fields as they were and store what staff did (`final_action`, final reply) separately. The `predictions.csv` export must stay the agent's output
- [x] **Self-check on edited replies** (done, see above)
- [ ] **Audit with old → new values and a reason** for every action that changes the agent's decision
- [ ] **Roles:** seeded `users` (`officer`, `fraud`, `manager`, with `approval_limit_myr`); each sees only their queue, sorted by priority and SLA due time
- [ ] **Two-tier approval:** over the officer's limit or sensitive → `ESCALATED`, waits for the manager. Fraud analyst actions: acknowledge → log investigation / recall → record outcome
- [ ] Separate screens per role (resolution desk, fraud workbench, manager console with override rate and SLA)
- [ ] Demo script for 8 minutes, rehearsed

### Shared milestones
- [ ] **Day 1, 16:00, Checkpoint 1:** classifies and finds the right transaction for 20 training complaints (the skeleton already does)
- [ ] **Day 2, 12:00, Checkpoint 2:** full workflow on 50 training complaints with the LLM on; training score posted (B: LLM on; C: app runs)
- [ ] **Day 2, 15:00:** predictions submitted, code freeze

## Frontend: Streamlit or React

Streamlit (`app/ui.py`) is the safety net and must work first. A React app is optional polish, worth it only if C knows React well.

1. **Day 1:** Streamlit works end to end (C's first three to-dos).
2. **Day 1 evening, optional:** build React (Vite) in `web/` against the existing API. Keep Streamlit as the fallback.
3. **Day 2, 12:00:** demo React only if submit, approve and the fraud queue all work reliably in it. Otherwise demo Streamlit.

The React app is only a client of `app/api.py`. The agent, worker and store don't change, so A and B aren't affected.

| UI need | Endpoint |
|---|---|
| Submit a complaint | `POST /complaints` → `{complaint_id}`, then poll `GET /cases/{id}` until it returns 200 |
| Approval / fraud queue | `GET /cases?status=PENDING_APPROVAL` / `GET /cases?status=FRAUD_QUEUE` |
| Case detail (decision, evidence, trace, audit log) | `GET /cases/{id}` |
| Approve / reject | `POST /cases/{id}/approve` / `POST /cases/{id}/reject` with `{officer, reply_text?, note?}`. Approve returns `422` with `detail.problems` when the reply fails the self-check (nothing is sent) |
| Queue counts | `GET /stats` |
| Awaiting customer / customer's answer | `GET /cases?status=AWAITING_CUSTOMER` / `POST /cases/{id}/messages` with `{text}` |

Statuses: open `AWAITING_CUSTOMER`, `PENDING_APPROVAL`, `FRAUD_QUEUE`; closed `RESOLVED`, `APPROVED`, `REJECTED`, `ANSWERED` (see `agent/schemas.py`). An `AWAITING_CUSTOMER` case has no decision yet: `outcome`, `route`, `matched_txn_id` and `refund_amount_myr` are `null`, so show "-". The message thread is in the case's `audit` list.

CORS already allows `http://localhost:5173` (Vite) and `http://localhost:3000`. Set `CORS_ORIGINS` (comma-separated) for other origins. A React demo needs three processes: `python -m app.worker`, `uvicorn app.api:app --port 8000`, and `npm run dev` in `web/`.

If C doesn't know React well, spend that day on Streamlit styling, the live-round test set and demo rehearsal instead.

## Rules of the road

- **Code decides money.** No LLM output ever sets outcome, refund, priority or route.
- **Branches:** `a/...`, `b/...`, `c/...` → PR into `main`. Run the tests and a train run before merging, and post the score in the PR.
- **Test predictions early.** `python -m scripts.run_batch --split test --team <team-name>` writes `submissions/<team-name>/predictions.csv`. Submit with a PR from our fork to `DM-Data-Science/teratai-complaints-hackathon`, titled `Submission: <team-name>`, before 15:00 on Day 2. It only needs the predictions file.
- **Keep up with the original repo.** It may get clarifications (never data changes). To bring them in: `git fetch upstream`, then `git merge upstream/main` on `main` and push (or use GitHub's **Sync fork** button). The `upstream` remote points at `DM-Data-Science/teratai-complaints-hackathon`; add it with `git remote add upstream https://github.com/DM-Data-Science/teratai-complaints-hackathon.git` if your clone lacks it.
- **No keys in the repo.** No hand-labelling of test complaints.

## Questions for the organisers

Ask by [opening an issue](https://github.com/DM-Data-Science/teratai-complaints-hackathon/issues) on the original repo; every team sees the answers.

- ~~Live round: what `received_at` will judges use?~~ Answered: 30 Sep 2026, in `complaints.csv` row format (README, "The live round"). The UI's default `2026-09-30 18:00` fits.
