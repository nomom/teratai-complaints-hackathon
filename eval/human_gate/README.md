# Human gate rehearsal

The 16:30 demo's human gate (10 points): judges send 3 complaints to our API **one at a time** and watch. Each case
must appear on its own, and you show its matched transaction, evidence, decision, route, reply and self-check. An
approval case must wait (`awaiting_approval`, `sent: false`) until someone approves it in our system, and a fraud case
must land in the fraud queue (README, "The live round").

Six complaints, fresh ids, built from training complaints with known answers. Each id is decided once, so set 2 is
for a second run:

| File | From | Category | Expected decision | Route |
|---|---|---|---|---|
| `HG1-A` | CMP-00060 | ATM_NOT_DISPENSED | REFUND RM1500.00, P2, EN | HUMAN_APPROVAL |
| `HG1-B` | CMP-00019 | SCAM_TRANSFER | INVESTIGATE, P1, EN | FRAUD_TEAM |
| `HG1-C` | CMP-00031 | DUPLICATE_CHARGE | REFUND RM71.62, P2, EN | AUTO_RESOLVE |
| `HG2-A` | CMP-00047 | FAILED_TRANSFER | REFUND RM2925.21, P2, MS | HUMAN_APPROVAL |
| `HG2-B` | CMP-00015 | SCAM_TRANSFER | INVESTIGATE, P1, MS | FRAUD_TEAM |
| `HG2-C` | CMP-00012 | ATM_NOT_DISPENSED | REFUND RM200.00, P2, MS | AUTO_RESOLVE |

## Roles

- **Judge** (a teammate, on another laptop on the same Wi-Fi, repo root): sends and checks through the API.
- **Presenter** (the serving laptop): the dashboard at http://localhost:5173. Staff logins use password `1234`:
  `officer1` (approval queue), `fraud1` (fraud queue), `manager1` (everything). Queues reload every 5 s.

`$U = "http://10.0.30.141:8000"` on the judge's laptop (PowerShell) shortens the commands below.

## Steps

1. **Presenter:** sign in as `officer1`, open the approval queue.
2. **Judge:** send the approval case.
   `curl.exe -X POST $U/complaints -H "Content-Type: application/json" --data "@eval/human_gate/HG1-A.json"`
   Expect `202` and `"status":"processing"`.
3. **Presenter:** within about 10 s, the case appears in the queue without a click. Open it: the matched transaction,
   the evidence (ATM journal: requested vs dispensed), the decision and why, the route, the drafted reply, the
   self-check.
4. **Judge:** `curl.exe $U/cases/HG1-A`. Expect `"case_state":"awaiting_approval"`, `"sent":false`,
   `"human_action":null`.
5. **Presenter:** try to edit the reply with an amount that isn't in the evidence (e.g. "We refunded RM9,999."),
   press Approve. It must be **refused** with the self-check's reasons, and nothing sent. Undo the edit.
6. **Presenter:** **Approve and send**.
7. **Judge:** `curl.exe $U/cases/HG1-A`. Expect `"case_state":"approved"`, `"sent":true`, and `human_action` with
   `"actor":"officer1"`. The decision fields stay the agent's own.
8. **Judge:** send the fraud case `HG1-B.json`. **Presenter:** it is **not** in officer1's queue; sign in as `fraud1`
   and show it in the fraud queue. **Judge:** `curl.exe $U/cases/HG1-B`: `"case_state":"with_fraud_team"`, `"sent":false`.
9. **Judge:** send `HG1-C.json`. **Judge:** `curl.exe $U/cases/HG1-C`: `"case_state":"auto_resolved"`, `"sent":true`.
   **Presenter:** sign in as `manager1` (officer and fraud roles have no Resolved page) and show it under
   **Resolved automatically**, with the reply that went out.
10. **Second run (set 2):** the same with `HG2-*`, but **reject** `HG2-A` in step 6; step 7 then expects
    `"case_state":"rejected"`, `"sent":false`, `human_action` with `"action":"reject"`. The replies are in Malay.

Anything that doesn't match: note the step and the response, and tell Claude.
