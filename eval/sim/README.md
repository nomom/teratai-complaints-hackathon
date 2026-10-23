# Simulated live round

A rehearsal of the organisers' hidden test, built from the 14 hand-written complaints in `eval/live_round.csv`
(prompts were partly tuned on them, so this checks the system end to end rather than being a blind test).

| File | What |
|---|---|
| `sim_complaints.csv` | 11 complaints (SIM-01 to SIM-11), one or more per category, messy EN / MS / call-centre wording |
| `sim_labels.csv` | Their answers, worked out by hand from `data/complaint_policy.csv`, `policy_parameters.csv` and the transaction data |
| `SIM-12.json` to `SIM-14.json` | A vague message and two off-topic ones: no category fits, so they aren't scored; send them by hand |

**Run it like the organisers** (from any laptop on the same Wi-Fi; Python 3, standard library only, from the repo root):

```powershell
python scoring/api_check.py http://10.0.30.141:8000 --complaints eval/sim/sim_complaints.csv --labels eval/sim/sim_labels.csv --all --out sim.json
```

Expect SCORE 100.0, 11/11 states and 9/9 probes. **Each id is decided once:** a second run returns the stored cases
straight away. For a fresh run, change the ids in both CSVs (e.g. `SIM2-01`), or reset the case store.

**Send the unscored ones and watch the dashboard:**

```powershell
curl.exe -X POST http://10.0.30.141:8000/complaints -H "Content-Type: application/json" --data "@eval/sim/SIM-12.json"
curl.exe http://10.0.30.141:8000/cases/SIM-12
```

Labelling notes:
- SIM-02: the customer is 72, so the priority goes up one level to P1.
- SIM-09: contactless isn't named in the card rule, and the training labels never show it. Only an unauthenticated
  (`None`) card charge is refunded, so we label it INVESTIGATE (fraud team). Its reply is in MS because it's a
  call-centre note: the customer's preferred language applies.
- SIM-10: the customer was 55 on the charge date, under the age-60 waiver, so the RM12 was due: DECLINE.
