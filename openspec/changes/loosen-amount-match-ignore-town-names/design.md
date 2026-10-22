# Design

## Context

Matching (`agent/matching.py`, `find_transaction`) works in two stages for each candidate debit in the 45-day window:

1. **Throw-out checks.** A debit whose amount contradicts the stated amount, or whose card differs from the stated card, is dropped.
2. **Scoring.** Survivors earn points per clue (exact amount +5, hedged amount up to +4, card +2, date +1/+3, name +2, fee type/month, duplicate twin). The highest total wins; ties on the whole number are flagged `AMBIGUOUS_MATCH`.

The hedged-amount check is `diff <= stated * APPROX_TOLERANCE` with `APPROX_TOLERANCE = 0.05`. The name clue (`_name_hit`) first compares the extracted counterparty with the debit's name. If that fails, it falls back to splitting the debit's name into words of 4+ letters (minus a small stop list) and checks whether any appears in the complaint text.

Merchant names in the data usually end with, or start with, the customer's town: "Kedai Buku Ilmu Melaka", "Bayan Lepas Station". The `city` column of `customers.csv` has 38 distinct town words. One of them, "lepas", is also common Malay ("minggu lepas" = last week) and appears in 197 complaints.

## Goals / Non-Goals

**Goals:**
- Hedged amounts up to 20% off reach the scoring stage.
- The name fallback only credits words that identify the merchant or payee, not where it is.
- Training score, flags and critical errors are no worse than with the tolerance change alone.

**Non-Goals:**
- Turning the amount check into a soft score instead of a throw-out check.
- Fixing CMP-01550 (23.2% off) or CMP-02357 (expected fee quoted as the amount).
- Changing the extracted-counterparty comparison, scoring weights or the 4-letter rule.
- Changing `agent/extract.py` (B's) or `agent/schemas.py`.

## Decisions

### 1. Tolerance 0.20

Measured on training (`--oracle-category`, rules extraction):

| Tolerance | NO_MATCH | Final |
|---|---|---|
| 0.05 | 23 | 98.63 |
| 0.10 | 9 | 99.27 |
| 0.15 | 1 | 99.61 |
| **0.20** | **0** | **99.65** |
| 0.25 | 0 | 99.70 |

0.20 is the smallest value that clears every `NO_MATCH`. 0.25 gains 0.05 by admitting one 23.2% outlier, at the cost of a gate 25% wider for every hedged complaint in the test set and the live round.

Alternative considered: making the amount a scored clue instead of a throw-out check. It is a larger behaviour change, and on its own it does not fix CMP-01550, because the wrong candidates still out-score the right one (8 vs 7) while town words earn name points.

### 2. Town words come from `customers.csv`

The town list is derived at runtime from the `city` column of the loaded customer data, split into lower-case words.

Alternatives considered:
- **A hard-coded list** in `matching.py`. It drifts from the data and has to be maintained by hand.
- **Strip the last words of each merchant name.** This fails for names where the town comes first ("Bayan Lepas Station") and for two-word towns ("Kota Bharu").

The organisers guarantee that live-round customers exist in `customers.csv`, so their towns are always covered.

### 3. The lookup goes through `agent/tools.py`

Add a cached `town_words()` to `tools.py`. It is built once from `get_db().customers`, like the other lookups. `tools.py` is the module's own data-access layer ("every lookup goes through here"), and caching avoids re-scanning about 3,000 customers for every candidate.

### 4. Only the word fallback is filtered

Town words are added to the existing stop list in the word fallback only. When the extracted counterparty matches the debit's name, it still gives full name credit, even for a name like "Melaka Station". This keeps the change confined to the loose part of the check.

## Risks / Trade-offs

- **The tolerance is tuned on rules extraction.** The LLM may mark hedges differently. → Re-run `run_batch --split train --oracle-category` once B's LLM extraction is on; the tolerance is one constant to adjust.
- **A wider gate means more candidates and possibly more ties.** → Measured: `AMBIGUOUS_MATCH` stays at 3, and ties already route to an officer.
- **A town word can also identify a shop** (for example "Jaya" in a shop name). → Checked: 0 of 1,757 card, transfer and ATM names lose all their identifying words. A shop that loses its town word keeps at least one other word.
- **ATM complaints naming only the town** ("the ATM in Kuantan") lose name credit for every Kuantan ATM. → Their date and amount still score, and with all candidates in one town, the town never distinguished them anyway. Measured: no training result changes.

## Migration Plan

No data or contract migration. Roll back by reverting the commit. Before merging, run the unit tests and the oracle train run, and post the score in the PR (TEAM.md rule).
