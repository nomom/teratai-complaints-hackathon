# Teratai Bank Complaints Agent Hackathon

**Two days. One problem. Build an AI agent that handles bank customer complaints end to end**: it reads the complaint, finds the transaction, applies the bank's policy, decides the refund and drafts the reply. A human signs off on the risky calls.

> Teratai Bank is fictional and every record in this repo is synthetic. Payment-rail names (DuitNow, IBG, JomPAY) are used for realism only.

---

## The challenge

Teratai Bank receives complaints through app chat, email, call-centre notes, branch forms and social media. They arrive in English, in Malay, and in a mix of both. Today a complaints officer reads each one, searches the customer's transactions, checks the policy, decides what the bank owes and writes the reply. It is slow, and the backlog keeps growing.

Your team builds the agent that does this work. For every complaint it must produce:

| Field | Values | What it means |
|---|---|---|
| `category` | 7 types (below) | What the complaint is about |
| `matched_txn_id` | `TXN-…` or empty | The transaction the complaint refers to, found in `transactions.csv` |
| `outcome` | `REFUND` / `DECLINE` / `INVESTIGATE` / `INFO_ONLY` | The decision under the bank's policy |
| `refund_amount_myr` | e.g. `45.90` | How much the bank pays back (0 unless REFUND) |
| `priority` | `P1` / `P2` / `P3` | How urgent the case is |
| `reply_language` | `EN` / `MS` | The language the reply must be written in |
| `route` | `AUTO_RESOLVE` / `HUMAN_APPROVAL` / `FRAUD_TEAM` | Who acts next |
| `reply_text` | free text | The reply to the customer |

Two examples:

> **CMP-00165** (app chat): *"Hai, saya telah dicaj dua kali di GoRide hari Selasa lepas sebanyak RM46.66. Saya hanya membuat satu pembelian. Sila bantu."*
> The agent works out that "last Tuesday" means 18 Aug. It finds two identical GoRide charges 1 minute 50 seconds apart, neither reversed. Result: DUPLICATE_CHARGE, matched TXN-0115572 (the later charge), REFUND RM46.66, P2, reply in Malay, AUTO_RESOLVE.

> **CMP-00387** (call-centre note): *"Customer called. Disputes a card transaction of about RM2,200 at LUXEGOODS LONDON last Saturday; says the card is in their possession."*
> The agent finds the RM2,213.95 charge on 19 Sep and sees it was approved with a one-time password (3DS-OTP). Result: UNAUTHORISED_CARD, INVESTIGATE, no refund now, P1, route to the fraud team. The reply goes in the customer's preferred language (English), because staff wrote the note.

## The seven complaint types

| Category | Typical complaint | What decides it |
|---|---|---|
| `DUPLICATE_CHARGE` | "I was charged twice at …" | Two identical card charges no more than 10 minutes apart, neither reversed → refund the later one |
| `FAILED_TRANSFER` | "My DuitNow transfer failed but the money was deducted" | Status Failed and not reversed → refund. Already reversed, or actually completed → decline |
| `ATM_NOT_DISPENSED` | "The ATM didn't give me the cash" | The ATM journal shows less dispensed than requested → refund the difference |
| `UNAUTHORISED_CARD` | "I didn't make this payment" | No strong authentication → refund. Approved with OTP or chip and PIN → fraud team investigates |
| `SCAM_TRANSFER` | "A 'police officer' told me to move my money to a safe account" | Always the fraud team, P1, to attempt a recall |
| `FEE_DISPUTE` | "Why was I charged this fee?" | The fee schedule and its waivers (product, age, card's first year) → refund what was wrongly charged |
| `SERVICE_QUALITY` | "I waited two hours at the branch" | No money involved: apologise and explain the next step |

The full decision rules are in [`data/complaint_policy.csv`](data/complaint_policy.csv). The rules that apply to every complaint:

- **Priority:** P1 for scams and unauthorised card use; P2 for duplicates, failed transfers and ATM cases; P3 for fees and service. A customer aged **65 or over** on the day the complaint arrives moves **one level up**.
- **Reply language:** the language the complaint is written in. If it mixes English and Malay, or it is a call-centre note written by staff, use the customer's `preferred_language`.
- **Routing:** INVESTIGATE goes to the **fraud team**. Every DECLINE, and every refund **over RM 500**, needs **human approval** before anything reaches the customer. Everything else is auto-resolved.

## What your agent must do

This is an agent hackathon, not a classification contest. A model that only labels CSV rows won't win. Your solution must:

1. **React to events.** A new complaint starts the workflow on its own (a watched folder, a queue or an API, your choice). In the live round, your intake must accept one new complaint in the format described under *The live round* below.
2. **Use tools.** It looks things up through tools or functions (customer, accounts, transactions, ATM journal, fee schedule). It does not paste whole tables into a prompt.
3. **Act.** It writes a case record: the decision, the evidence it used and the drafted reply.
4. **Keep a human in charge.** Cases that need approval wait in an approval queue, and fraud cases land in a fraud queue. Nothing that needs approval goes out without it.
5. **Check itself.** Code, not the LLM, checks that every transaction ID and amount in the reply appears in the evidence. Anything that fails the check is flagged.

The design that wins: **the LLM does language** (understanding the complaint, writing the reply), and **code does money and rules** (finding the transaction, applying the policy, working out the refund).

## The data

Everything is CSV in [`data/`](data/). All times are Malaysia time (UTC+8). Column-by-column details are in [`docs/data_dictionary.md`](docs/data_dictionary.md).

| File | Rows | What |
|---|---|---|
| `complaints.csv` | 2,500 | The complaints: channel, received time, subject, free text. Only the customer is identified |
| `customers.csv` | 3,000 | Name, date of birth, location, segment, preferred language |
| `accounts.csv` | 4,903 | Savings, current and credit-card accounts, with card last-4 digits |
| `transactions.csv` | 156,366 | April to September 2026: card, transfer, ATM, bill, fee and reversal transactions |
| `atm_journal.csv` | 18,240 | What each ATM actually dispensed |
| `fee_schedule.csv` | 6 | Fees by product, with waiver rules |
| `complaint_policy.csv` | 7 | The decision rules per category |
| `policy_parameters.csv` | 7 | Thresholds and rules: refund approval limit, vulnerable age, matching window, routing, reply language |
| `sla_policy.csv` | 3 | Acknowledge and resolve targets by priority |
| `labels_train.csv` | 1,750 | Correct answers for 70% of complaints. Use them to build and test |
| `test_ids.csv` | 750 | The complaints you are scored on. Their answers are held by the organisers |

## Scoring and judging

**Leaderboard (automatic).** Submit predictions for the 750 test complaints. Each complaint scores up to 100:

| Field | Points |
|---|---|
| `matched_txn_id` | 25 |
| `outcome` | 25, only if the transaction is right |
| `refund_amount_myr` | 25, exact to the sen, only if the transaction is right |
| `category` | 10 |
| `priority` | 10 |
| `reply_language` | 5 |

A decision about the wrong transaction earns nothing, so finding the right transaction is the heart of the task. The keyword baseline in `starter/` scores **31.9**. The answer key scores 100.

**Critical errors** are penalised on top: paying a refund the bank doesn't owe, and failing to send a fraud case to the fraud team. Each 1% of critical errors costs 2% of your score. Run the same scorer on the training labels at any time (see *Getting started*).

**Final ranking:**

| Weight | Criterion | How it is judged |
|---|---|---|
| 30% | Accuracy | Leaderboard score on the test set |
| 25% | Agent design and guardrails | **Live round**: judges type new complaints into your system during the demo. We check the routing and approval step, that it reacts on its own, and that its self-check catches bad replies |
| 25% | Business value and demo | Reply quality (tone, correct language, no invented facts; judges read 10 of your replies), clarity, and whether a bank would use it |
| 20% | Engineering | Architecture, observability (can you show why it decided what it did?), cost and speed per complaint |

### The live round

During your demo, a judge gives you 2 or 3 new complaints written for the event. Each one has the same fields as a row of `complaints.csv`. A made-up example of the format:

```
complaint_id,customer_id,received_at,channel,subject,text
LIVE-07,CUS-01234,2026-09-30 10:15,App chat,,"Hi, I was charged twice at ShopLah Online today for RM89.90..."
```

The customer and the transaction already exist in the data. `received_at` is 30 Sep 2026, the last day of the data. Your system must take the complaint in without code changes (for example, a file dropped into a watched folder or a POST to your API). It must process it on its own and show the case record with its evidence, the route and the reply. Cases that need approval must wait for a human to approve them.

## Schedule

**Day 1**

| Time | |
|---|---|
| 09:00 | Kick-off: the problem, data, rules and scoring |
| 09:30 | Walkthrough of the starter kit and the baseline |
| 10:00 | Teams design their workflow |
| 10:30 | Build |
| 13:00 | Lunch |
| 16:00 | **Checkpoint 1:** the agent classifies and finds the right transaction for 20 training complaints |
| 17:30 | Day 1 close (the room stays open) |

**Day 2**

| Time | |
|---|---|
| 09:00 | Stand-ups, 5 minutes per team |
| 12:00 | **Checkpoint 2:** the full workflow (decision, reply, approval and write-back) runs on 50 training complaints, and your training score is posted |
| 13:00 | Lunch |
| 15:00 | **Predictions due** and code freeze |
| 15:15 | Demos: 8 minutes per team, including the live round |
| 16:45 | Judges deliberate while the leaderboard is published |
| 17:15 | Awards |

The 750 test complaints are in `complaints.csv` from the start, so you can run them whenever you are ready. Don't leave a 750-complaint LLM run for the last hour.

## Getting started

Teams of 3 to 5. Use any language, agent framework and LLM your team can access. The starter kit needs only Python 3.10+, with no packages to install. On macOS or Linux, use `python3` where the commands below say `python`.

```bash
git clone https://github.com/DM-Data-Science/teratai-complaints-hackathon.git
cd teratai-complaints-hackathon

# 1. See one complaint with its evidence: an ATM that paid out RM950 of a RM1,500 withdrawal
python starter/evidence_pack.py CMP-00244

# 2. Run the keyword baseline and score it on the training labels: 31.9 is the score to beat
python starter/baseline.py
python scoring/score.py submissions/baseline/predictions.csv data/labels_train.csv

# 3. Check drafted replies against the evidence (the self-check every agent needs)
python starter/check_reply.py CMP-00244 "We have refunded RM550.00 for transaction TXN-0088211."   # VERIFIED
python starter/check_reply.py CMP-00244 "We have refunded RM600.00 for transaction TXN-0088299."   # FLAGGED: invented ID and amount
```

More in [`docs/build_guide.md`](docs/build_guide.md): a reference workflow, where to use the LLM and where to use code, and common pitfalls.

## Bonus: the ops platform

An optional, separately judged award ("Best Ops Platform") for teams that turn the case record into a real back-office system: complaints officers and fraud analysts sign in to interfaces fitted to their job and see only their cases, a manager handles second-tier approval across both queues, and every action is written back and audited. It does not affect the main ranking or the leaderboard. See [`docs/bonus_platform.md`](docs/bonus_platform.md).

## Submitting

1. Fork this repo (one fork per team) and build in your fork.
2. Run your workflow on all 750 complaints in `test_ids.csv`.
3. Save `submissions/<team-name>/predictions.csv` with these columns: `complaint_id, category, matched_txn_id, outcome, refund_amount_myr, priority, reply_language, route, reply_text`. The format is in [`docs/scoring.md`](docs/scoring.md).
4. Open a pull request from your fork to this repo, titled `Submission: <team-name>`, before **15:00 on Day 2**. The PR only needs the predictions file; your code can stay in your fork.

Building the [bonus ops platform](docs/bonus_platform.md)? Your `predictions.csv` is still the agent's autonomous output, exported from your database and scored exactly as above — the platform does not change what you submit.

If this repo changes before the event (clarifications only, never the data), sync your fork with GitHub's **Sync fork** button.

## Ground rules

- **Your workflow produces the answers.** No hand-labelling of the test set. The live round shows whether your system really works; a big gap between your leaderboard score and the live round will be questioned. This holds even if you build the [bonus ops platform](docs/bonus_platform.md): the scored `predictions.csv` is always the agent's autonomous decision, never the human-corrected one.
- **Use any tools.** That includes any LLM, framework or cloud service. You may use the training labels however you like: few-shot examples, evaluation, fine-tuning.
- **Data stays synthetic.** Don't add real customer data, and keep API keys out of the repo.
- **Ask early.** If a rule is unclear, [open an issue](https://github.com/DM-Data-Science/teratai-complaints-hackathon/issues) in this repo. Every team can see the answers.

## Repo layout

```
data/          the CSVs (complaints, customers, accounts, transactions, ATM journal, policies, training labels, test IDs)
docs/          data dictionary, scoring details, build guide, bonus ops platform
starter/       evidence pack builder, reply checker, keyword baseline (Python, standard library only)
scoring/       score.py: the scorer used for the leaderboard
submissions/   one folder per team
```
