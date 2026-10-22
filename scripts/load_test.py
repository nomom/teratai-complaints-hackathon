"""Load test for the live-round API: how it behaves when many complaints arrive at once.

    python -m scripts.load_test http://localhost:8000 --n 200
    python -m scripts.load_test http://localhost:8000 --n 50 --threads 50 --timeout 120

Sends N copies of real training complaints at once (fresh ids, so they are new cases with known answers), measures how
fast POST /complaints answers, then polls GET /cases/{id} until each is done (as scoring/api_check.py does) and reports:
POST latency, HTTP errors, time to done, how many finished within the live round's 120 s, throughput, and accuracy
against the training labels. Standard library only; no credentials, like the organisers' calls.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import random
import statistics
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["complaint_id", "customer_id", "received_at", "channel", "subject", "text"]
CHECK = ("matched_txn_id", "outcome", "refund_amount_myr", "category")


def http(method, url, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:  # noqa: BLE001 -- refused, reset, timeout: count it, don't stop
        return None, type(e).__name__


def pct(values, p):
    if not values:
        return float("nan")
    v = sorted(values)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("--n", type=int, default=100, help="complaints to send at once")
    ap.add_argument("--threads", type=int, default=64, help="concurrent clients")
    ap.add_argument("--timeout", type=int, default=120, help="seconds a complaint may take (live round: 120)")
    ap.add_argument("--poll", type=float, default=2.0, help="seconds between GETs per complaint (api_check: 2)")
    a = ap.parse_args()
    base = a.base_url.rstrip("/")

    labels = {r["complaint_id"]: r for r in csv.DictReader(open(ROOT / "data" / "labels_train.csv", encoding="utf-8"))}
    pool = [c for c in csv.DictReader(open(ROOT / "data" / "complaints.csv", encoding="utf-8"))
            if c["complaint_id"] in labels]
    run = uuid.uuid4().hex[:6].upper()
    picks = [(f"LOAD-{run}-{i:04d}", c) for i, c in enumerate(random.Random(7).choices(pool, k=a.n))]

    def one(item):
        new_id, c = item
        body = {**{k: c[k] for k in FIELDS}, "complaint_id": new_id}
        t0 = time.perf_counter()
        status, _ = http("POST", f"{base}/complaints", body, timeout=a.timeout)
        post_s = time.perf_counter() - t0
        out = {"id": new_id, "src": c["complaint_id"], "post_status": status, "post_s": post_s, "gets": 0}
        if status is None or status >= 300:
            return out
        while time.perf_counter() - t0 < a.timeout:
            s, case = http("GET", f"{base}/cases/{new_id}", timeout=30)
            out["gets"] += 1
            if s is None or s >= 500:
                out["get_error"] = s
            elif s == 200 and isinstance(case, dict) and case.get("status") in ("done", "error"):
                out.update(done_s=time.perf_counter() - t0, case=case)
                return out
            time.sleep(a.poll)
        return out

    print(f"Sending {a.n} complaints to {base} at once ({a.threads} clients), {a.timeout}s allowed each ...", flush=True)
    t_start = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=a.threads) as ex:
        results = list(ex.map(one, picks))
    wall = time.perf_counter() - t_start

    posts = [r["post_s"] for r in results]
    post_codes = Counter(str(r["post_status"]) for r in results)
    done = [r for r in results if "done_s" in r]
    done_s = [r["done_s"] for r in done]
    errors = sum(1 for r in done if r["case"].get("status") == "error")
    get_errors = sum(1 for r in results if r.get("get_error") is not None)
    right = sum(1 for r in done if r["case"].get("status") == "done" and all(
        str(r["case"].get(f, "")) == labels[r["src"]][f] for f in CHECK))
    print(f"\nPOST /complaints   status codes {dict(post_codes)}")
    print(f"                   latency median {statistics.median(posts) * 1000:.0f} ms, p95 {pct(posts, 95) * 1000:.0f} ms,"
          f" max {max(posts) * 1000:.0f} ms")
    print(f"done within {a.timeout}s  {len(done)}/{a.n}   (status error: {errors}; GET 5xx or failures: {get_errors})")
    if done_s:
        print(f"time to done       median {statistics.median(done_s):.1f}s, p95 {pct(done_s, 95):.1f}s, "
              f"slowest {max(done_s):.1f}s")
    print(f"throughput         {len(done) / wall:.2f} complaints/s over {wall:.1f}s; "
          f"{sum(r['gets'] for r in results)} GETs")
    print(f"correct (txn, outcome, refund, category vs labels): {right}/{len(done)}")


if __name__ == "__main__":
    main()
