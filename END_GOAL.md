# End goal

What we hand in at 15:00 on Day 2, and what the judges see at 15:15. Who does what is in [TEAM.md](TEAM.md).

**Four deliverables:** a working app, a predictions file, a repo, and an 8-minute demo.

---

## 1. A working app

It runs on a laptop as three processes: `python -m app.worker`, the API (`uvicorn app.api:app`) and the React dashboard in `web/`. Officers use the dashboard. In the live round, judges hand us 2 or 3 new complaints as `complaints.csv` rows, and we feed them in through the same intake with no code changes.

| Screen | What it does |
|---|---|
| **Submit complaint** | Form: customer ID, channel, received time, complaint text (English, Malay or mixed). The decision appears within seconds |
| **Approval queue** | Declines, refunds over RM500 and flagged cases wait here until an officer approves, edits or rejects the reply |
| **Fraud queue** | Scams, and unauthorised card use approved with OTP or chip and PIN |
| **Awaiting customer** | Complaints too general to act on: the agent asked the customer for details, and their reply reopens the case |
| **All cases** | Every case with its status; open any one to see how it was decided |

Every case page shows:

- **Decision:** category, matched transaction, outcome, refund, priority, route
- **Why:** plain-English reasons, e.g. *"Identical charge TXN-… 110s earlier, neither reversed"*
- **Self-check:** VERIFIED, or FLAGGED with the problem
- **Reply:** drafted in the right language (English or Malay)
- **Evidence:** the transaction rows, ATM journal or fee schedule the decision used
- **Trace:** each step, how long it took, LLM tokens used
- **Audit log:** who did what and when (agent processed, officer approved, reply sent)

### Who acts on each case

| Case | Route | What happens |
|---|---|---|
| Refund of RM500 or less, or a service complaint | AUTO_RESOLVE | The reply goes out at once, no sign-off |
| Any decline, or a refund over RM500 | HUMAN_APPROVAL | Waits in the approval queue for an officer |
| Fraud: a scam, or a card payment approved with OTP or chip and PIN | FRAUD_TEAM | Waits in the fraud queue |
| Anything flagged (no match, ambiguous match, failed self-check) | HUMAN_APPROVAL | Waits for an officer, even if it would otherwise auto-resolve |
| The agent's reply fails the self-check, and fails again after one rewrite | HUMAN_APPROVAL | Waits for an officer with a standard reply in the box and the rejected drafts on record ("redraft once, then flag it for a human") |
| A complaint too general to act on ("my account has a problem") | none yet | The agent asks the customer for details. The case stays open with **no decision** (`AWAITING_CUSTOMER`) until they reply, then it is decided like any other. After 2 rounds without enough detail, an officer takes over. Possible fraud never waits |
| Not a banking complaint ("what's the weather?") | AUTO_RESOLVE | The agent answers politely that this channel handles account complaints (`ANSWERED`); no officer needed |

Nothing that needs approval reaches the customer without it. Messages are recorded in the case's audit log (`question_sent`, `customer_replied`, `reply_sent`); no real email goes out.

### Case status

A case's status says where it is, separately from what was decided.

| Open | Closed |
|---|---|
| `AWAITING_CUSTOMER`: we asked for details; no decision yet | `RESOLVED`: decided, and the reply went out automatically |
| `PENDING_APPROVAL`: decided; an officer must sign off | `APPROVED` / `REJECTED`: an officer acted |
| `FRAUD_QUEUE`: decided INVESTIGATE; the fraud team takes it | `ANSWERED`: not a banking complaint; nothing to decide |

`predictions.csv` needs a value in every column, so a case still awaiting the customer exports as no transaction, `INFO_ONLY`, `AUTO_RESOLVE`.

### What it looks like in the live round

The judges give us 2 or 3 complaints written for the event, each in the same format as a row of `complaints.csv` (see the README, "The live round"):

```
complaint_id,customer_id,received_at,channel,subject,text
LIVE-07,CUS-01234,2026-09-30 10:15,App chat,,"Hi, I was charged twice at ShopLah Online today for RM89.90..."
```

IDs run `LIVE-01`, `LIVE-02`, ...; `received_at` is on 30 Sep 2026, the last day of the data; the customer and transaction already exist. We take each one in through the intake (form, `POST /complaints`, or a file in `inbox/`). The system processes it on its own and shows the case record with its evidence, route and reply. Cases needing approval wait for us to approve them on screen.

The examples below are real training complaints in that shape, useful for rehearsal.

**A fraud case, which lands in the fraud queue** (CUS-02323, call-centre note, received 2026-09-23 21:55)
> *"Customer called. Disputes a card transaction of about RM2,200 at LUXEGOODS LONDON last Saturday; says the card is in their possession."*

→ UNAUTHORISED_CARD · TXN-0143340 · **INVESTIGATE** · RM0.00 · P1 · reply in English (staff note, so the customer's preferred language) · **FRAUD_TEAM**
Why: approved with 3DS-OTP. The case waits in the fraud queue.

**A small refund, which resolves on its own** (CUS-00566, app chat, received 2026-08-24 09:25)
> *"Hai, saya telah dicaj dua kali di GoRide hari Selasa lepas sebanyak RM46.66. Saya hanya membuat satu pembelian. Sila bantu."*

→ DUPLICATE_CHARGE · TXN-0115572 (the later charge) · **REFUND RM46.66** · P2 · reply in Malay · **AUTO_RESOLVE**
Why: an identical charge 1 min 50 s earlier, neither reversed. The reply is sent straight away.

**A large refund, which waits for an officer** (CUS-02394, email, received 2026-07-20 22:32)
> *"The machine did not dispense all of the cash when I withdrew about RM1,500 last Friday, but the whole amount was deducted."*

→ ATM_NOT_DISPENSED · TXN-0088211 · **REFUND RM550.00** · P2 · reply in English · **HUMAN_APPROVAL**
Why: the ATM journal shows RM1,500 requested and RM950 dispensed. The refund is over RM500, so it waits until an officer clicks Approve.

**The self-check catching a bad reply:** an officer edits a reply to say *"We have refunded RM600.00 for transaction TXN-0088299"*. It is FLAGGED (invented ID and amount) and is not sent.

### Limits judges should know
- The customer must exist in `customers.csv` (intake has already identified them). The organisers guarantee this for live complaints.
- The transaction must exist in `transactions.csv`, within the 45 days before the received time. Live complaints are received on 30 Sep 2026, which the form uses as its default.

---

## 2. The predictions file

- `submissions/<team-name>/predictions.csv`: one row for each of the 750 test complaints, with all 9 columns including the reply
- Produced by the same workflow as the app (`python -m scripts.run_batch --split test --team <team-name>`), never by hand
- Submitted as a pull request **from our fork** (`nomom/teratai-complaints-hackathon`) to the original repo (`DM-Data-Science/teratai-complaints-hackathon`), titled `Submission: <team-name>`, **before 15:00 on Day 2**. The PR only needs the predictions file; our code stays in the fork
- Always the agent's own output, never officer-corrected, even if we build the ops platform below
- Training score: **99.91** today with the LLM off (it started at 92.16). Target: keep it there, and holding up on fresh wording in the live round, with zero critical errors (no wrongful refunds, no missed fraud)

---

## 3. The repo

- Clean `main`: the code, [TEAM.md](TEAM.md), this file, tests that pass
- One command reproduces the training score: `python -m scripts.run_batch --split train`
- No API keys committed, no hand-labelled answers

---

## 4. The 8-minute demo

| Time | What we show |
|---|---|
| 0:00–1:00 | The problem, and our design in one slide: **the LLM does language, code does money and rules** |
| 1:00–3:00 | Our three examples above, one down each route, plus a Malay or mixed-language one |
| 3:00–6:00 | **Live round:** judges give us 2 or 3 new complaints (`complaints.csv` rows); we feed them in, show the decision, the reasons and the queue each lands in, then approve one |
| 6:00–7:00 | The self-check catching a bad reply |
| 7:00–8:00 | Numbers: training score, accuracy per field, cost and seconds per complaint |

## How the judges score us

| Weight | What they judge | What earns it |
|---|---|---|
| 30% | Leaderboard accuracy | Right transaction first (it gates 75 of the 100 points per complaint), then outcome and refund to the sen |
| 25% | Agent design and guardrails | Reacts on its own, routes correctly, nothing risky goes out unapproved, the self-check works |
| 25% | Business value and demo | Replies a bank would send (tone, right language, no invented facts), a clear demo |
| 20% | Engineering | Clean architecture, every decision explainable, low cost and fast per complaint |

## Optional: the "Best Ops Platform" award

A separate award ([docs/bonus_platform.md](docs/bonus_platform.md)); it doesn't affect the ranking or the leaderboard. Only after the core agent works. It turns the case store into a back office:

- **Roles:** complaints officers see only the approval queue, fraud analysts only the fraud queue, and a manager sees both plus escalations. Seeded users with a `role` are enough
- **Two-tier approval:** officers and analysts clear cases up to their approval limit; anything over it, or sensitive, waits for the manager
- **Fitted screens:** a resolution desk for officers (reply first), an investigation workbench for analysts (transaction, auth method, timeline), an oversight console for the manager (SLA, override rate)
- **Integrity:** the agent's decision is never overwritten. Staff actions are stored separately, every edited reply goes through the self-check again, and the audit log records old → new values with a reason

Where we stand: the case store, the queues, the audit log and the separation of status from decision already exist. Gaps are listed under C's optional to-dos in [TEAM.md](TEAM.md).
