# Bonus: the ops platform

**This is an optional bonus, judged as a separate award ("Best Ops Platform"). It does not change the main ranking or the leaderboard.** Build it only once your core agent works. A team that nails accuracy and skips this is not penalised.

The core brief asks your agent to *route* risky cases to a human and *wait* for sign-off ([README.md](../README.md)). The case record already carries everything an officer needs: the decision, the matched transaction, the evidence, the drafted reply and the route. This bonus turns that into a real back-office system: the people a case is routed to sign in, see only their cases, and act on them.

## The idea

Your agent writes each case to a database instead of (or as well as) a file. On top of that database you build a small web app where bank staff resolve the cases the agent couldn't close on its own:

```
agent ──► case record in DB ──► queue ──► staff sign in ──► act ──► DB updated ──► customer
                                   │
          AUTO_RESOLVE ────────────┤ (no human; shown for audit only)
          HUMAN_APPROVAL ──────────┤ officer (first tier): approve / edit / reject / send back
          FRAUD_TEAM ──────────────┘ fraud analyst (first tier): acknowledge / investigate / record outcome
                                   │
                                   └─ over a limit or sensitive ──► manager (admin): second-tier approval
```

## Roles

There are two frontline teams and a manager who oversees and second-tier-approves for both.

| Role | Sees | Can do |
|---|---|---|
| **Complaints officer** (first tier) | `HUMAN_APPROVAL` queue | Approve as-is, edit the reply then approve, reject/decline, or send back to the agent — up to their refund approval limit. Anything above the limit is escalated to the manager. |
| **Fraud analyst** (first tier) | `FRAUD_TEAM` queue | Acknowledge, record investigation / recall attempt, set an outcome. The customer gets the holding reply, not a resolution. Sensitive or high-value calls are escalated to the manager. |
| **Manager** (admin) | Both queues, the escalation queue, the audit log and metrics | Everything the two tiers can see, plus **second-tier approval for both**: clears escalated cases, reassigns, and oversees. The manager is the only one who sees both frontline queues. |

Keep auth simple: seeded users and a `role` column are enough. The point is that a fraud analyst sees only fraud cases and an officer sees only approval cases — not production-grade identity. Don't let sign-in eat your two days.

### Two-tier approval

The core rule is that refunds over RM 500 need approval ([README.md](../README.md)). Split that into two tiers:

- **First tier** — the officer (approval queue) or analyst (fraud queue) clears cases up to their `approval_limit_myr` (e.g. RM 5,000).
- **Second tier** — anything above the limit, or flagged sensitive, is escalated to the **manager (admin)**, who approves or rejects it. The same manager handles escalations from both queues.

A case escalated to the second tier must still **wait** for the manager — it is not sent on the first-tier action alone.

## What the platform must do (MVP)

1. **Sign in and see your queue.** A signed-in user sees only the cases their role is responsible for, sorted by priority and SLA due time.
2. **Act on a case.** Approve / edit / reject / send back (approver) or acknowledge / investigate / record outcome (fraud). Every action that changes the agent's decision captures a one-line **reason**.
3. **Re-run the self-check on edits.** If a human edits `reply_text`, re-run the self-check (`starter/check_reply.py`) before "send" unlocks. A human-edited reply that invents a transaction ID or amount is blocked exactly as the agent's would be. See [README.md](../README.md) point 5.
4. **Write the action back.** The action, the actor and the timestamp are stored. Nothing marked `HUMAN_APPROVAL` or `FRAUD_TEAM` reaches the customer until a human has acted.
5. **Keep an audit trail.** An append-only log of who did what, when, and old value → new value.

## Two interfaces, one platform (advice)

The fraud and approval teams do different jobs, so give them different screens rather than one generic case view. They share the same database, audit log and self-check — only the layout and the verbs differ.

**Complaints officer — a resolution desk.** The job is to get a correct reply to the customer quickly. Lead with the drafted `reply_text` (editable), the decision and refund amount, and an evidence panel to verify the matched transaction. Primary actions: **approve / edit & approve / reject / send back**. Show the officer's remaining approval headroom, and when a refund exceeds the limit, replace "approve" with "escalate to manager." Cases here are short-lived — one decision and they close.

**Fraud analyst — an investigation workbench.** The customer only ever gets the holding reply, so do *not* centre this screen on reply prose. Lead with the suspicious transaction and its `auth_method` (3DS-OTP, chip & PIN, or none — the fact that decides unauthorised-card cases), related transactions on the account, and a **case timeline**. Primary actions: **acknowledge → log investigation / recall attempt → record outcome** (confirmed fraud / not fraud / recall succeeded / recall failed). These cases are long-lived and stateful, so status and history matter more than a single approve button.

**Manager — an oversight + escalation console.** One dashboard across both queues (throughput, SLA, override rate) plus a **second-tier approval queue** that merges escalations from both teams. Each escalation shows what the first tier already did and why it was escalated; the manager approves or rejects with a reason. This is the only screen that spans both case types.

Keep the shared mechanics identical everywhere: the self-check re-runs on any reply edit, every action is appended to the audit log, and the agent's original decision is never overwritten.

## Integrity: the agent's decision vs the human's action

Store these as two separate things:

- **`agent_decision`** — immutable, exactly what the agent produced. **This is what the leaderboard scores.**
- **`final_action`** — what staff actually did and what reached the customer.

The exported `submissions/<team-name>/predictions.csv` and the scorer are unchanged: they always reflect the **agent's autonomous output**, never the human-corrected version. This keeps the ground rule intact — your workflow produces the answers, no hand-labelling ([README.md](../README.md), Ground rules). The gap between `agent_decision` and `final_action` is not scored; it is one of the most interesting things you can show a judge.

## Suggested data model

Use any database and schema you like; this is a starting point.

| Table | Key columns |
|---|---|
| `cases` | `complaint_id`, agent fields (`category`, `matched_txn_id`, `outcome`, `refund_amount_myr`, `priority`, `reply_language`, `route`, `reply_text`), `evidence` (JSON), `self_check` (pass/flag), `status` (`pending` / `escalated` / `approved` / `rejected` / `sent` / `investigating` / `closed`), `assigned_to`, `sla_due_at` |
| `case_events` | `complaint_id`, `actor`, `action`, `field`, `old_value`, `new_value`, `reason`, `created_at` — append-only |
| `users` | `username`, `role` (`officer` / `fraud` / `manager`), `approval_limit_myr` (manager has no limit) |

Keep the agent's original fields immutable on `cases`; record every change as a row in `case_events`.

## Stretch ideas

- **SLA clocks.** `data/sla_policy.csv` has acknowledge/resolve targets by priority. Show each case's due time and flag overdue cases; sort queues by SLA + priority.
- **Evidence panel.** Render the evidence pack (`starter/evidence_pack.py`) beside the case so the approver verifies the matched transaction without leaving the screen.
- **Admin dashboard.** Auto-resolve rate, approval turnaround, **override rate** (how often humans change the agent), self-check catches, critical-error near-misses.
- **Outbound log.** Record each "sent" message with timestamp and who authorised it — the proof nothing reached the customer without approval.
- **Notifications.** Alert a role when a new case lands in its queue.

## How it's judged

A separate optional award, judged on top of the main demo and independent of the 30/25/25/20 ranking:

- **Does the human gate actually hold?** Approval-needed cases wait; fraud cases land with the fraud team; escalations wait for the manager; nothing is sent without a human.
- **Role separation.** Officers, analysts and the manager each see only what they should, through interfaces fitted to their job.
- **Two-tier approval.** First tier clears within its limit; over-limit or sensitive cases escalate to the manager and wait.
- **Guardrail on edits.** The self-check re-runs on human-edited replies.
- **Auditability.** You can show who did what and why, and the agent-vs-human gap.
- **Would a bank actually use it.** Clarity and realism of the workflow.

## What to show

In your demo, drive three cases end to end:

1. A `HUMAN_APPROVAL` case **within** the officer's limit — officer approves (or edits, triggering the self-check) and it sends.
2. A `HUMAN_APPROVAL` case **over** the limit — officer escalates, the manager second-tier-approves, then it sends.
3. A `FRAUD_TEAM` case — the analyst acknowledges and logs the investigation on the fraud workbench; the customer sees only the holding reply.

Show the audit log and the agent-vs-human record across them. The leaderboard submission (`predictions.csv`) is produced and scored exactly as in the core brief.
