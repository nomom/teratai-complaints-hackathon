# End goal

What we hand in at 15:00 on Day 2, and what the judges see at 15:15. Who does what is in [TEAM.md](TEAM.md).

**Four deliverables:** a working app, a predictions file, a repo, and an 8-minute demo.

---

## 1. A working app

It runs on a laptop as two processes: `python -m app.worker` and the dashboard (Streamlit, or React if we switch). Officers use the dashboard. In the live round, judges type complaints into the same intake form.

| Screen | What it does |
|---|---|
| **Submit complaint** | Form: customer ID, channel, received time, complaint text (English, Malay or mixed). The decision appears within seconds |
| **Approval queue** | Declines, refunds over RM500 and flagged cases wait here until an officer approves, edits or rejects the reply |
| **Fraud queue** | Scams, and unauthorised card use approved with OTP or chip and PIN |
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

Nothing that needs approval reaches the customer without it. "Sent" is a status in the case store and audit log; no real email goes out.

### What it looks like in the live round

These are real training complaints, retyped the way a judge would type them.

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
- The customer must exist in `customers.csv` (intake has already identified them).
- The transaction must exist in `transactions.csv`, within the 45 days before the received time. Transactions end in September 2026, so the form's received time defaults to 2026-09-30.

---

## 2. The predictions file

- `submissions/<team-name>/predictions.csv`: one row for each of the 750 test complaints, with all 9 columns including the reply
- Produced by the same workflow as the app (`python -m scripts.run_batch --split test --team <team-name>`), never by hand
- Pushed on branch `team/<team-name>` with a pull request **before 15:00 on Day 2**
- Training score: **92.16** today with the LLM off. Target: **mid-to-high 90s** with zero critical errors (no wrongful refunds, no missed fraud)

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
| 3:00–6:00 | **Live round:** judges type new complaints; we show the decision, the reasons and the queue it lands in, then approve one |
| 6:00–7:00 | The self-check catching a bad reply |
| 7:00–8:00 | Numbers: training score, accuracy per field, cost and seconds per complaint |

## How the judges score us

| Weight | What they judge | What earns it |
|---|---|---|
| 30% | Leaderboard accuracy | Right transaction first (it gates 75 of the 100 points per complaint), then outcome and refund to the sen |
| 25% | Agent design and guardrails | Reacts on its own, routes correctly, nothing risky goes out unapproved, the self-check works |
| 25% | Business value and demo | Replies a bank would send (tone, right language, no invented facts), a clear demo |
| 20% | Engineering | Clean architecture, every decision explainable, low cost and fast per complaint |
