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

```bash
python -m unittest discover tests                    # core: stdlib only, no install needed
python -m scripts.run_batch --split train            # full train run + score + per-category table (seconds, offline)

pip install -r requirements.txt                      # for the LLM and the app
python -m app.worker                                 # terminal 1: reacts to new complaints
streamlit run app/ui.py                              # terminal 2: submit / approval queue / fraud queue
uvicorn app.api:app --port 8000                      # optional: HTTP intake, docs at /docs
```

LLM on: set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` in your shell (see `.env.example`). With it off, the rules and templates run and everything still works.

## Where we start (offline, no LLM): train score 92.16

```
true category           n  category     txn  outcome  refund   prio   lang
ATM_NOT_DISPENSED     213       67%     67%      67%     67%    67%    93%
DUPLICATE_CHARGE      249      100%     96%      96%     96%   100%    97%
FAILED_TRANSFER       277      100%     96%      96%     96%   100%    97%
FEE_DISPUTE           270      100%    100%     100%    100%   100%    93%
SCAM_TRANSFER         213       91%    100%      91%    100%    91%    97%
SERVICE_QUALITY       244      100%    100%     100%    100%   100%    87%
UNAUTHORISED_CARD     284      100%     99%      99%     99%   100%    98%
```

Biggest gaps, in points:

1. **B:** 70 ATM complaints classed as SERVICE_QUALITY ("the machine did not dispense", "wang tidak keluar"). The LLM extractor should fix this.
2. **B:** 20 scams classed as FAILED_TRANSFER ("deceived by an online acquaintance", "skim pelaburan"). These are **critical errors** (missed fraud, each costs 2× its share of the score).
3. **B:** about 90 reply-language misses (EN/MS on app chat, email and branch forms). Mixed-language detection needs work.
4. **A:** 23 `NO_MATCH` flags and about 4% wrong transactions on duplicates and failed transfers. Read `submissions/our-team/predictions_train_details.csv`.

## To do, by person

Tick items off in your PRs. Highest value first.

### A: matching and decisions
Goal: txn, outcome and refund near 100% with `run_batch --split train --oracle-category`.

- [ ] Fix the 23 `NO_MATCH` cases: open `predictions_train_details.csv`, run `python starter/evidence_pack.py <id>`, find what broke (date phrase, amount tolerance, card last-4)
- [ ] Fix the ~4% wrong transactions on DUPLICATE_CHARGE and FAILED_TRANSFER (several similar candidates: weigh date, amount and name better)
- [ ] Grow `dates.py` with the phrases you find ("minggu lepas", "awal bulan", "last weekend", ...)
- [ ] Check `fee_due()` edge cases: card opened 29 Feb, customer turning 60 the month of the fee, a fee with no matching product
- [ ] Unit tests for boundaries: refund RM500.00 vs RM500.01, age 65 on the received date, duplicates exactly 10 minutes apart

### B: LLM layer
Goal: category and language near 100%; replies a bank would send; a self-check judges can't sneak past.

- [ ] **Scams classed as FAILED_TRANSFER (20, critical errors).** Add rule keywords now ("deceived", "acquaintance", "skim pelaburan", "melabur"), then confirm the LLM gets them
- [ ] ATM complaints classed as SERVICE_QUALITY (70): "machine did not dispense", "wang tidak keluar"
- [ ] Reply language (~90 misses): improve `detect_language()` for EN/MS/MIXED, or let the LLM decide. The preferred-language rule stays in code
- [ ] Turn the LLM on (`LLM_PROVIDER=anthropic`), run 100–200 train complaints, compare against the rules, record tokens and cost per complaint
- [ ] Few-shot examples in the extraction prompt, picked from the confused categories
- [ ] Better replies per category in EN and MS: tone, SLA timeline, short (judges read 10)
- [ ] Harden `checks.py`: wrong refund amount, refund promised on a decline, wrong language. Try to break it like a judge would

### C: platform and demo
Goal: the live round works without a hitch; test predictions in early.

- [ ] `pip install -r requirements.txt`, run the worker + UI (+ API) for the first time, fix what breaks (they haven't been run yet)
- [ ] Push one complaint down each path: auto-resolved refund, decline → approval queue, refund > RM500 → approval queue, fraud → fraud queue. Approve and reject update the audit log
- [ ] Re-run the self-check on an officer's edited reply before it is sent (`TODO(C)` in `store.approve`)
- [ ] Case page clearly shows why it decided, timing per step, and cost (engineering score)
- [ ] *Optional, decide at Checkpoint 2:* a React frontend (see "Frontend: Streamlit or React" below)
- [ ] Live-round test set: ~10 tricky complaints written fresh (Malay, mixed, call-centre note, 65+, > RM500, scam, ambiguous)
- [ ] Test predictions early: `run_batch --split test --team <team-name>`, branch `team/<team-name>`, PR well before 15:00 Day 2. Re-run as A and B improve
- [ ] Ask the organisers what `received_at` judges will use
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
| Approve / reject | `POST /cases/{id}/approve` / `POST /cases/{id}/reject` with `{officer, reply_text?, note?}` |
| Queue counts | `GET /stats` |

CORS already allows `http://localhost:5173` (Vite) and `http://localhost:3000`. Set `CORS_ORIGINS` (comma-separated) for other origins. A React demo needs three processes: `python -m app.worker`, `uvicorn app.api:app --port 8000`, and `npm run dev` in `web/`.

If C doesn't know React well, spend that day on Streamlit styling, the live-round test set and demo rehearsal instead.

## Rules of the road

- **Code decides money.** No LLM output ever sets outcome, refund, priority or route.
- **Branches:** `a/...`, `b/...`, `c/...` → PR into `main`. Run the tests and a train run before merging, and post the score in the PR.
- **Test predictions early.** `python -m scripts.run_batch --split test --team <team-name>` writes `submissions/<team-name>/predictions.csv`. Submit from branch `team/<team-name>` before 15:00 on Day 2.
- **No keys in the repo.** No hand-labelling of test complaints.

## Open questions for the organisers

- Live round: what `received_at` will judges use? Transactions end in September 2026, so the UI defaults to `2026-09-30 18:00`.
