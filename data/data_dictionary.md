# Data dictionary

All files are UTF-8 CSV with a header row. Times are Malaysia time (UTC+8), formatted `YYYY-MM-DD HH:MM[:SS]`. Amounts are in Malaysian ringgit with two decimals. Teratai Bank is fictional and all data is synthetic.

## complaints.csv: the work queue (2,500 rows)

| Column | Meaning |
|---|---|
| `complaint_id` | `CMP-00001` … `CMP-02500` |
| `customer_id` | The customer who complained (intake has already identified them) |
| `received_at` | When the complaint arrived. Relative dates in the text ("yesterday", "hari Jumaat lepas", "last week") are relative to this |
| `channel` | `App chat`, `Email`, `Call centre note`, `Branch form` or `Social media DM`. Call-centre notes are written by staff, in English, in the third person |
| `subject` | Email subject line. Empty for other channels |
| `text` | The complaint in English, Malay or a mix. Amounts may be exact ("RM1,250.00") or approximate ("about RM1,200", "lebih kurang RM1,200"). Merchant and recipient names may be partial or lower-case |

The complaint never contains the transaction ID. Your agent has to find it.

## customers.csv (3,000 rows)

| Column | Meaning |
|---|---|
| `customer_id` | `CUS-00001` … |
| `full_name` | Customer name |
| `date_of_birth` | Needed for the vulnerable-customer rule (65+) and the debit-card fee waiver (60+) |
| `state`, `city` | Home location |
| `segment` | `Retail` or `Premier` |
| `preferred_language` | `EN` or `MS`. Used for the reply when the complaint mixes languages or is a call-centre note |
| `email` | Fictional address |
| `customer_since` | Relationship start date |

## accounts.csv (4,903 rows)

| Column | Meaning |
|---|---|
| `account_id` | `ACC-000001` … |
| `customer_id` | Owner |
| `product` | `Basic Savings`, `Savings Plus`, `Current Account`, `Credit Card Classic`, `Credit Card Platinum` |
| `open_date` | Matters for the credit-card annual fee (waived in the first year) |
| `status` | `Active` |
| `card_last4` | The debit card on a savings account, or the credit card number's last 4 digits. Empty for current accounts |

## transactions.csv (156,366 rows, April to September 2026)

| Column | Meaning |
|---|---|
| `txn_id` | `TXN-0000001` …, in time order |
| `txn_time` | When it was posted |
| `account_id`, `customer_id` | Whose account |
| `direction` | `DR` (money out) or `CR` (money in) |
| `amount_myr` | Always positive |
| `channel` | `Card POS`, `Card e-Commerce`, `DuitNow Transfer`, `IBG Transfer`, `ATM Withdrawal`, `JomPAY Bill`, `Fee`, `Salary Credit`, `DuitNow Received`, `Reversal` |
| `merchant_or_counterparty` | Merchant (cards), recipient name (transfers), ATM location (ATM), biller (JomPAY) or `Teratai Bank` (fees) |
| `counterparty_account` | Masked recipient account for transfers, e.g. `xxxxxx4821` |
| `counterparty_bank` | Recipient's bank for transfers |
| `merchant_country` | ISO country code for card transactions (`MY` for domestic) |
| `card_last4` | Card used (cards and ATM) |
| `auth_method` | `Chip+PIN`, `Contactless`, `3DS-OTP` (one-time password), `None` (card not present, no strong authentication), `App approval` (transfers and bills), `N/A` |
| `status` | `Completed` or `Failed` |
| `description` | Free text. Fees say which fee (`Monthly service charge Jun 2026`, `Debit card annual fee`, `Credit card annual fee`). Reversals say `Reversal of TXN-…` |

A reversal is a `CR` row with channel `Reversal` whose description names the original transaction.

## atm_journal.csv (18,240 rows)

One row per ATM withdrawal: what the machine recorded.

| Column | Meaning |
|---|---|
| `txn_id` | The ATM Withdrawal transaction |
| `atm_id`, `atm_location` | The machine |
| `requested_myr` | Amount requested (and debited) |
| `dispensed_myr` | Cash the machine actually paid out |
| `journal_status` | `OK`, `PARTIAL_DISPENSE` or `DISPENSE_FAULT` |

## fee_schedule.csv (6 rows)

| Column | Meaning |
|---|---|
| `fee_code` | Internal code |
| `fee_name` | Matches the start of the fee transaction's description |
| `product` | The account product the fee applies to |
| `amount_myr` | The correct fee |
| `waiver_rule` | When the fee must not be charged |

## complaint_policy.csv, policy_parameters.csv, sla_policy.csv

The bank's rules. `complaint_policy.csv` has one row per category: what it covers, how to find the transaction, the decision rule and the base priority. `policy_parameters.csv` holds the thresholds and the routing and reply-language rules. `sla_policy.csv` gives acknowledge and resolve targets per priority (use them for due dates in your case records; they are not scored).

## labels_train.csv (1,750 rows) and test_ids.csv (750 rows)

`labels_train.csv` has the correct answer for 70% of the complaints: `complaint_id, category, matched_txn_id, outcome, refund_amount_myr, priority, reply_language, route`. `matched_txn_id` is empty for `SERVICE_QUALITY`. `refund_amount_myr` is `0.00` unless the outcome is `REFUND`.

`test_ids.csv` lists the other 30%. You are scored on these. Their answers are held by the organisers.
