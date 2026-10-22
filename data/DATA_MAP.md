# Data map

How the CSVs in this folder link together, and how the agent walks them for one complaint. Column-by-column details are in [docs/data_dictionary.md](../docs/data_dictionary.md).

## Files and links

```
                         ┌──────────────────────────────┐
                         │ customers.csv        (3,000) │
                         │──────────────────────────────│
                         │ PK customer_id               │
                         │    full_name                 │
                         │    date_of_birth  ── age 65+ / 60+ rules
                         │    state, city, segment      │
                         │    preferred_language ── reply language
                         │    email, customer_since     │
                         └──────────────┬───────────────┘
                 ┌──────────────────────┼─────────────────────────┐
                 │ 1:N                  │ 1:N                     │ 1:N
┌────────────────▼─────────────┐ ┌──────▼──────────────────────┐  │
│ complaints.csv       (2,500) │ │ accounts.csv        (4,903) │  │
│──────────────────────────────│ │─────────────────────────────│  │
│ PK complaint_id              │ │ PK account_id               │  │
│ FK customer_id               │ │ FK customer_id              │  │
│    received_at ── anchor for │ │    product ─────────────────┼──┼──► fee_schedule.product
│       dates + 45-day window  │ │    open_date ── CC fee      │  │
│    channel ── call-centre    │ │       waived in 1st year    │  │
│       note → preferred lang  │ │    status                   │  │
│    subject, text             │ │    card_last4               │  │
└───────┬──────────────────────┘ └──────┬──────────────────────┘  │
        │ 1:1                           │ 1:N                     │
┌───────▼──────────────────────┐ ┌──────▼─────────────────────────▼──────┐
│ labels_train.csv     (1,750) │ │ transactions.csv            (156,366) │
│ test_ids.csv           (750) │ │───────────────────────────────────────│
│──────────────────────────────│ │ PK txn_id                             │
│ complaint_id, category,      │ │ FK account_id, customer_id            │
│ matched_txn_id ──────────────┼─► txn_time, direction (DR/CR)          │
│ outcome, refund_amount_myr,  │ │    amount_myr                         │
│ priority, reply_language,    │ │    channel  Card POS | Card e-Commerce│
│ route                        │ │             DuitNow | IBG | ATM |     │
└──────────────────────────────┘ │             JomPAY | Fee | Reversal…  │
                                 │    merchant_or_counterparty           │
                                 │    counterparty_account/_bank         │
                                 │    merchant_country, card_last4       │
                                 │    auth_method  None | 3DS-OTP |      │
                                 │                 Chip+PIN | Contactless│
                                 │    status  Completed | Failed         │
                                 │    description ── "Reversal of TXN-…" │
                                 │                   "Monthly service…"  │
                                 └──────┬─────────────────┬──────────────┘
                                        │ 1:0..1          │ self-reference
                         ┌──────────────▼─────────────┐   │ (Reversal CR row names
                         │ atm_journal.csv   (18,240) │   │  the original txn in
                         │────────────────────────────│   │  its description)
                         │ FK txn_id (ATM Withdrawal) │   └──► transactions.txn_id
                         │    atm_id, atm_location    │
                         │    requested_myr           │
                         │    dispensed_myr           │
                         │    journal_status          │
                         └────────────────────────────┘

 ─── Rules (lookup tables, not linked by ID) ─────────────────────────────────
 ┌─────────────────────────┐ ┌─────────────────────────┐ ┌──────────────────────┐
 │ complaint_policy.csv (7)│ │ policy_parameters.csv(7)│ │ fee_schedule.csv  (6)│
 │ category → how to find  │ │ AUTO_REFUND_LIMIT  500  │ │ fee_code, fee_name,  │
 │ the txn, decision rule, │ │ VULNERABLE_AGE      65  │ │ product, amount_myr, │
 │ base_priority           │ │ DEBIT_FEE_WAIVER_AGE 60 │ │ waiver_rule          │
 └─────────────────────────┘ │ DUPLICATE_WINDOW  10min │ └──────────────────────┘
 ┌─────────────────────────┐ │ MATCH_WINDOW_DAYS   45  │
 │ sla_policy.csv       (3)│ │ ROUTING, REPLY_LANGUAGE │
 │ priority → ack hours,   │ └─────────────────────────┘
 │ resolve business days   │
 └─────────────────────────┘
```

**Legend:** PK = primary key, FK = foreign key, (n) = row count, 1:N = one row links to many.

## How the agent walks the data for one complaint

```
complaints ──customer_id──► customers  (name, age, preferred language)
     │                          │
     │                          └──► accounts  (products, cards, open dates)
     │
     └─ received_at − 45 days ──► transactions (DR rows for this customer)
                                     │  filter by channel, amount, date, name, card
                                     ▼
                                  matched txn ──► atm_journal       (ATM cases)
                                     │        ──► Reversal rows     (failed transfers, duplicates)
                                     │        ──► fee_schedule      (fee disputes, via account product)
                                     ▼
                         complaint_policy + policy_parameters ──► outcome, refund, priority, route
                                                       sla_policy ──► due date
```

In code, every lookup goes through `agent/tools.py` (`get_customer`, `get_accounts`, `find_debits`, `get_reversal`, `get_atm_journal`, `get_fee_schedule`).
