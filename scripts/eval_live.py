"""Model evaluation on newly written, live-round-style complaints (eval/live_round.csv). See MODEL_EVAL.md.

    python -m scripts.eval_live --price-in 0.20 --price-out 1.20     (USD per 1M tokens, from the provider's page)

Runs every complaint twice, with the LLM in .env and with rules only, and compares both with the expected answer
(intent; for complaints, category and matched transaction). Prints each case, then accuracy, speed, tokens and cost.
Each complaint is processed one at a time, so the seconds are the latency a customer would see.
"""
from __future__ import annotations

import argparse
import csv
import statistics
import time
from pathlib import Path

from agent import llm, tools
from agent.pipeline import process_complaint

ROOT = Path(__file__).resolve().parent.parent


def correct(rec, row) -> bool:
    if row["expect_intent"] != "COMPLAINT":
        return rec.extraction.intent == row["expect_intent"]
    return rec.category == row["expect_category"] and rec.decision.matched_txn_id == row["expect_txn"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default=str(ROOT / "eval" / "live_round.csv"))
    ap.add_argument("--price-in", type=float, help="USD per 1M input tokens")
    ap.add_argument("--price-out", type=float, help="USD per 1M output tokens")
    args = ap.parse_args()
    if not llm.enabled():
        raise SystemExit("No LLM configured: set LLM_PROVIDER, the key and LLM_MODEL in .env first.")

    rows = list(csv.DictReader(open(args.set, newline="", encoding="utf-8")))
    tools.get_db()
    provider = llm.PROVIDER
    score = {"llm": 0, "rules": 0}
    secs, tok_in, tok_out, failures = [], 0, 0, []
    for row in rows:
        c = {k: row[k] for k in ("complaint_id", "customer_id", "received_at", "channel", "subject", "text")}
        out = {}
        for name, prov in (("llm", provider), ("rules", "")):
            llm.PROVIDER, llm._client = prov, None
            t0 = time.perf_counter()
            out[name] = process_complaint(c)
            if name == "llm":
                secs.append(time.perf_counter() - t0)
            score[name] += correct(out[name], row)
        llm.PROVIDER, llm._client = provider, None
        u = out["llm"].llm_usage
        tok_in, tok_out = tok_in + u.get("input_tokens", 0), tok_out + u.get("output_tokens", 0)
        failures += u.get("failures", [])
        marks = " ".join(f"{n} {'OK ' if correct(r, row) else 'BAD'}" for n, r in out.items())
        r = out["llm"]
        print(f"{row['complaint_id']:8} {marks} | {secs[-1]:4.1f}s | {r.extraction.intent} {r.category} "
              f"{r.decision.matched_txn_id or '-'} {r.decision.outcome or '-'} -> {r.status} | {row['note']}")

    n = len(rows)
    print(f"\nmodel: {provider} {llm.MODEL}")
    print(f"correct: LLM {score['llm']}/{n}, rules only {score['rules']}/{n}")
    print(f"latency per complaint (LLM): median {statistics.median(secs):.1f}s, range {min(secs):.1f}-{max(secs):.1f}s")
    print(f"tokens per complaint: input {tok_in / n:.0f}, output {tok_out / n:.0f}; LLM failures: {failures or 'none'}")
    if args.price_in is not None and args.price_out is not None:
        each = (tok_in * args.price_in + tok_out * args.price_out) / 1e6 / n
        print(f"cost: ${each:.5f} per complaint, ${each * 750:.2f} per 750 (no caching discount assumed)")


if __name__ == "__main__":
    main()
