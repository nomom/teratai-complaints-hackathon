# Tasks

## 1. Baseline

- [x] 1.1 On branch `a/matching-and-decisions`, run `uv run python -m unittest discover tests` and `uv run python -m scripts.run_batch --split train --oracle-category`; verify the tests pass and the run shows `NO_MATCH: 23`, `AMBIGUOUS_MATCH: 2` and `FINAL SCORE 98.63`
- [x] 1.2 Run `uv run python -m scripts.run_batch --split train` (no oracle) and note its final score as the team baseline for task 4.2; verify the number is recorded (baseline: FINAL SCORE 92.16, critical errors 20)

## 2. Hedged amount tolerance

- [x] 2.1 In `agent/matching.py`, set `APPROX_TOLERANCE = 0.20` and update its comment (e.g. "about RM250" may be RM227.11); verify the oracle run shows no `NO_MATCH` and `FINAL SCORE 99.65`
- [x] 2.2 Add a `Matching` test class to `tests/test_core.py` that supplies synthetic debits by patching `tools.find_debits` with `unittest.mock.patch`, covering the spec scenarios: "about RM100" keeps RM120.00 and drops RM123.25, an unhedged RM227.11 drops RM227.12, and RM101.00 outranks RM115.00; verify the tests pass
- [x] 2.3 Add real-data tests to the same class: CMP-00464 matches TXN-0090984 and CMP-00295 matches TXN-0146195 (the later of the duplicate pair); verify they pass, and fail when `APPROX_TOLERANCE` is temporarily set back to 0.05

## 3. Town names are not name evidence

- [x] 3.1 Add a cached `town_words()` to `agent/tools.py` that returns the lower-case words of every customer's `city`; verify with a test that it contains "melaka", "lepas" and "kota", and that a second call returns the same object
- [x] 3.2 In `agent/matching.py`, exclude `tools.town_words()` from the word fallback of `_name_hit` only, leaving the extracted-counterparty comparison unchanged; verify the oracle run still shows `FINAL SCORE 99.65`, `AMBIGUOUS_MATCH: 3` and `critical errors 0`
- [x] 3.3 Add tests for the spec scenarios: "Kedai Buku Ilmu Melaka" gets no name credit from a complaint mentioning "Butik Ayu Melaka", "Butik Ayu Melaka" does, and an extracted counterparty "Melaka Station" gets credit for "Melaka Station"; verify they pass
- [x] 3.4 Update the TODO list in the `agent/matching.py` module docstring (tolerance tuned; town words excluded from name matching); verify the docstring reflects the change

## 4. Integration check

- [x] 4.1 Run `uv run python -m unittest discover tests` and the oracle train run; verify all tests pass, `NO_MATCH` is absent, `critical errors 0` and `FINAL SCORE` is at least 99.65
- [x] 4.2 Run the normal train run (no oracle); verify its final score is not below the team baseline from task 1.2 and critical errors did not increase (result: 92.16 → 93.17, critical errors 20 → 20)
- [ ] 4.3 Commit with the before and after scores in the message (e.g. "Loosen hedged-amount match to 20%, ignore town names (98.63 → 99.65)"), push, and open or update the PR into `main` with both scores; verify the PR shows the scores

## Workflow follow-up

- After merge, tell B that the hedged-amount tolerance was tuned on rules extraction, and re-run the oracle check once the LLM extraction is on.
- Archive the change once the PR is merged.
- Tick step 1 in `tmp/person_a_todo.md`.
