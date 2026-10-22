# Proposal

## Why

Transaction matching misses 23 training complaints (`NO_MATCH`) because a hedged amount ("about RM250", "dalam RM100") must be within 5% of the real transaction, and customers round further than that (up to 23% on training). Each miss loses 75 of the complaint's 100 points, since outcome and refund only count with the right transaction. Widening that limit lets in more candidates. The name clue, though, gives +2 to any shop whose name shares a town word with the complaint ("Melaka", "Ipoh"), so a wider limit makes it easier for a nearby-amount shop in the same town to win.

## What Changes

- Raise the hedged-amount tolerance in `agent/matching.py` from 5% to 20% of the stated amount. Exact (unhedged) amounts still must match to the cent.
- The name clue no longer counts a word that is only a town or city name (taken from the `city` column of `data/customers.csv`). Merchant-identifying words ("butik", "foodku", "shoplah") still count. An extracted counterparty that matches the transaction's name still counts in full.
- No change to scoring weights, the card and amount throw-out checks, tie-breaking, `AMBIGUOUS_MATCH`/`NO_MATCH` flags, or `agent/schemas.py`.

Measured on training with `--oracle-category` (rules extraction, LLM off):

| | Now | After |
|---|---|---|
| `NO_MATCH` | 23 | 0 |
| matched_txn_id / outcome / refund | 98.5% | 99.9% |
| Final score | 98.63 | 99.65 |
| Critical errors | 0 | 0 |

Removing town words changes no training result by itself (328 candidates got name points from a town word alone, and only one of them, CMP-01550, was a wrong pick). Its value is safety on the test set and the live round, where the wider amount limit admits more same-town candidates.

## Capabilities

### New Capabilities
- `transaction-matching`: how a complaint is matched to the one debit it refers to: which candidates are considered, which clues rule a candidate out, which clues score, and when the match is flagged.

### Modified Capabilities
<!-- none: no specs exist yet -->

## Impact

- **Code:** `agent/matching.py` only (`APPROX_TOLERANCE`, `_name_hit`). Town words are read through `agent/tools.py` from data already loaded.
- **Tests:** new unit tests for the hedged-amount boundary and the town-word rule in `tests/`.
- **Contracts:** none. `Extraction`, `Decision` and `CaseRecord` are unchanged, so B and C need no changes.
- **Not fixed by this change:** CMP-01550 (23.2% off, outside 20%) and CMP-02357 (the customer quotes the fee they expected, not the fee charged) stay wrong.
- **Re-check later:** the tolerance was tuned on rules extraction. Re-run the oracle check once B's LLM extraction is on, since it may mark hedged amounts differently.
