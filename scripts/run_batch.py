"""Owner: C. Run the pipeline over many complaints and write predictions.csv (the leaderboard file).

    python -m scripts.run_batch --split train --limit 200        # quick check, scored automatically
    python -m scripts.run_batch --split train --oracle-category  # A: matching + policy only, true categories
    python -m scripts.run_batch --split test --team <team-name>  # the submission
    add --store to also write the cases into the app's database
"""
import argparse
import csv
import os
import random
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent import tools
from agent.pipeline import process_complaint

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["complaint_id", "category", "matched_txn_id", "outcome", "refund_amount_myr", "priority", "reply_language",
          "route", "reply_text"]


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["train", "test", "all"], default="train")
    ap.add_argument("--limit", type=int, help="first N complaints of the split")
    ap.add_argument("--sample", type=int, help="random N complaints of the split (seeded)")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("BATCH_WORKERS", 8)))
    ap.add_argument("--team", default=os.environ.get("TEAM_NAME", "our-team"))
    ap.add_argument("--out", help="predictions path (default: submissions/<team>/predictions[_train].csv)")
    ap.add_argument("--oracle-category", action="store_true", help="train only: use the true category")
    ap.add_argument("--store", action="store_true", help="also save cases to the app database")
    args = ap.parse_args()

    db = tools.get_db()
    labels = {r["complaint_id"]: r for r in read_csv(ROOT / "data" / "labels_train.csv")}
    test_ids = [r["complaint_id"] for r in read_csv(ROOT / "data" / "test_ids.csv")]
    ids = {"train": list(labels), "test": test_ids, "all": list(db.complaints)}[args.split]
    if args.sample:
        ids = random.Random(7).sample(ids, min(args.sample, len(ids)))
    if args.limit:
        ids = ids[:args.limit]

    store = None
    if args.store:
        from app import store

    def run(cid):
        oracle = labels[cid]["category"] if args.oracle_category and cid in labels else None
        try:
            rec = process_complaint(db.complaints[cid], oracle_category=oracle)
        except Exception as e:  # noqa: BLE001 -- one bad complaint must not kill the run
            print(f"  ERROR {cid}: {type(e).__name__}: {e}", file=sys.stderr)
            return None
        if store:
            store.save_case(rec)
        return rec

    t0 = time.time()
    with ThreadPoolExecutor(args.workers) as pool:
        records = [r for r in pool.map(run, ids) if r]
    took = time.time() - t0

    suffix = "" if args.split == "test" else f"_{args.split}"
    out = Path(args.out) if args.out else ROOT / "submissions" / args.team / f"predictions{suffix}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        for r in records:
            w.writerow(r.prediction_row())

    toks = Counter()
    for r in records:
        toks.update({k: v for k, v in r.llm_usage.items() if isinstance(v, int)})
    print(f"wrote {out}: {len(records)}/{len(ids)} complaints in {took:.1f}s "
          f"({1000 * took / max(len(ids), 1):.0f} ms each), LLM calls {toks['calls']}, "
          f"tokens in/out {toks['input_tokens']}/{toks['output_tokens']}")
    flags = Counter(f for r in records for f in r.decision.flags)
    print(f"flags: {dict(flags)}  routes: {dict(Counter(r.decision.route for r in records))}")

    scored = [r for r in records if r.complaint.complaint_id in labels]
    if scored:
        breakdown(scored, labels)
        sub_labels = out.with_name(out.stem + "_labels.csv")
        with open(sub_labels, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, list(next(iter(labels.values())).keys()))
            w.writeheader()
            for r in scored:
                w.writerow(labels[r.complaint.complaint_id])
        print(flush=True)
        subprocess.run([sys.executable, str(ROOT / "scoring" / "score.py"), str(out), str(sub_labels),
                        "--details", str(out.with_name(out.stem + "_details.csv"))])


def breakdown(records, labels):
    """Per true category: how often each field is right. Shows who should work on what."""
    rows = defaultdict(Counter)
    for r in records:
        t = labels[r.complaint.complaint_id]
        p = r.prediction_row()
        c = rows[t["category"]]
        c["n"] += 1
        c["category"] += p["category"] == t["category"]
        txn_ok = p["matched_txn_id"] == t["matched_txn_id"]
        c["txn"] += txn_ok
        c["outcome"] += txn_ok and p["outcome"] == t["outcome"]
        c["refund"] += txn_ok and abs(float(p["refund_amount_myr"]) - float(t["refund_amount_myr"])) < 0.005
        c["priority"] += p["priority"] == t["priority"]
        c["lang"] += p["reply_language"] == t["reply_language"]
    print(f"\n{'true category':<20}{'n':>5}{'category':>10}{'txn':>8}{'outcome':>9}{'refund':>8}{'prio':>7}{'lang':>7}")
    for cat, c in sorted(rows.items()):
        n = c["n"]
        print(f"{cat:<20}{n:>5}" + "".join(f"{c[k] / n:>{w}.0%}" for k, w in
              [("category", 10), ("txn", 8), ("outcome", 9), ("refund", 8), ("priority", 7), ("lang", 7)]))


if __name__ == "__main__":
    main()
