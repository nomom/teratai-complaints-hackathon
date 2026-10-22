# Scoring

## Predictions file

One row per complaint in `test_ids.csv` (extra rows are ignored), UTF-8 CSV with this header:

```
complaint_id,category,matched_txn_id,outcome,refund_amount_myr,priority,reply_language,route,reply_text
```

| Column | Allowed values |
|---|---|
| `category` | `DUPLICATE_CHARGE`, `FAILED_TRANSFER`, `ATM_NOT_DISPENSED`, `UNAUTHORISED_CARD`, `SCAM_TRANSFER`, `FEE_DISPUTE`, `SERVICE_QUALITY` |
| `matched_txn_id` | A `TXN-…` ID, or empty for `SERVICE_QUALITY` |
| `outcome` | `REFUND`, `DECLINE`, `INVESTIGATE`, `INFO_ONLY` |
| `refund_amount_myr` | Number with two decimals; `0.00` unless REFUND |
| `priority` | `P1`, `P2`, `P3` |
| `reply_language` | `EN`, `MS` |
| `route` | `AUTO_RESOLVE`, `HUMAN_APPROVAL`, `FRAUD_TEAM` |
| `reply_text` | The reply you would send (quote it; it may contain commas and line breaks) |

`submissions/baseline/predictions.csv` (written by `python starter/baseline.py`) shows the format.

## Leaderboard score

Each complaint earns up to 100 points:

| Field | Points | Rule |
|---|---|---|
| `matched_txn_id` | 25 | Exact match (empty = empty) |
| `outcome` | 25 | Exact match, **and** the transaction must be right |
| `refund_amount_myr` | 25 | Within RM0.005, **and** the transaction must be right |
| `category` | 10 | Exact match |
| `priority` | 10 | Exact match |
| `reply_language` | 5 | Exact match |

**Critical errors** are counted separately:
- **Wrongful refund:** you predict a refund above zero when the correct outcome is DECLINE or INVESTIGATE.
- **Missed fraud:** the correct outcome is INVESTIGATE and you predict anything else.

**Final score = mean points × (1 − 2 × critical error rate)**, never below 0. Example: a mean of 90 with 3% critical errors gives 90 × 0.94 = 84.6.

`route` and `reply_text` aren't in the automatic score. Judges check routing in the live round and read a sample of 10 replies per team.

Score yourself on the training labels at any time:

```bash
python scoring/score.py submissions/<team>/predictions.csv data/labels_train.csv --details details.csv
```

`--details` writes one line per complaint showing which fields were wrong.

## Final ranking

| Weight | Criterion |
|---|---|
| 30% | Leaderboard score on the test set |
| 25% | Agent design and guardrails, checked in the live round: routing and approvals, reacting to new complaints on its own, the self-check catching bad replies |
| 25% | Business value and demo: reply quality (tone, correct language, no invented facts), clarity, would a bank use it |
| 20% | Engineering: architecture, observability (show why it decided), cost and speed per complaint |

### The live round

During your demo the judges give you 2 or 3 new complaints in the same format as a row of `complaints.csv` (`complaint_id, customer_id, received_at, channel, subject, text`, with IDs `LIVE-01`… and `received_at` on 30 Sep 2026). The customers and transactions they refer to are already in the data. Your intake must accept them without code changes. We look for the right decision and the right route. Cases that need approval must wait for approval, and fraud cases must land with the fraud team. The reply must pass your own self-check.
