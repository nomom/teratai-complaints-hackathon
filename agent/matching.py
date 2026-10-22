"""Owner: A. Find the transaction a complaint refers to. 25 points directly, and gates 50 more.

Approach: take the customer's debits in the 45-day window for the category's channels, drop the ones that
contradict a hard clue (amount, card), then score the rest on soft clues (date, name). Ties are flagged, not hidden.

Done: approximate-amount tolerance tuned on training (20%); town words no longer count as a name match.

TODO(A):
  - better name matching (partial, ATM location, biller)
  - DUPLICATE_CHARGE: when several twin pairs exist, use the date/amount to pick the pair
  - FEE_DISPUTE: "I thought the fee is only RM10" quotes the expected fee, not the charged one (CMP-02357)
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from . import tools
from .dates import resolve_dates
from .schemas import Extraction

CHANNELS = {
    "DUPLICATE_CHARGE": {"Card POS", "Card e-Commerce"},
    "UNAUTHORISED_CARD": {"Card POS", "Card e-Commerce"},
    "FAILED_TRANSFER": {"DuitNow Transfer", "IBG Transfer"},
    "SCAM_TRANSFER": {"DuitNow Transfer", "IBG Transfer"},
    "ATM_NOT_DISPENSED": {"ATM Withdrawal"},
    "FEE_DISPUTE": {"Fee"},
}
FEE_PREFIX = {"MONTHLY_SERVICE": "Monthly service charge", "DEBIT_ANNUAL": "Debit card annual fee",
              "CC_ANNUAL": "Credit card annual fee"}
APPROX_TOLERANCE = 0.20      # "about RM250" may be RM227.11; tuned on train (0.05 left 23 NO_MATCH)


@dataclass
class Match:
    txn: dict | None
    candidates: list = field(default_factory=list)   # [(score, txn_id)] best first
    reasons: list = field(default_factory=list)
    flags: list = field(default_factory=list)


def _name_hit(t, ex: Extraction, text: str) -> bool:
    name = t["merchant_or_counterparty"].lower()
    if ex.counterparty and (ex.counterparty.lower() in name or name in ex.counterparty.lower()):
        return True
    # No extracted name: does a distinctive word of this merchant appear in the complaint text?
    # Town words don't count: "Melaka" is in every Melaka shop's name, and "lepas" (Bayan Lepas) also means "last".
    words = [w for w in re.findall(r"[a-z0-9]+", name)
             if len(w) >= 4 and w not in {"bank", "berhad", "sdn", "bhd"} and w not in tools.town_words()]
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def _has_twin(t, pool):
    """An identical earlier charge (same card, merchant, amount) within the duplicate window."""
    win = dt.timedelta(minutes=int(tools.param("DUPLICATE_WINDOW_MINUTES")))
    for o in pool:
        if (o["txn_id"] != t["txn_id"] and o["card_last4"] == t["card_last4"]
                and o["merchant_or_counterparty"] == t["merchant_or_counterparty"]
                and abs(o["amount"] - t["amount"]) < 0.005 and dt.timedelta(0) < t["time"] - o["time"] <= win):
            return o
    return None


def find_transaction(complaint: dict, ex: Extraction) -> Match:
    if ex.category == "SERVICE_QUALITY":
        return Match(None, reasons=["Service complaint: no transaction involved"])

    recv = tools.received(complaint)
    since = recv - dt.timedelta(days=int(tools.param("MATCH_WINDOW_DAYS")) + 1)
    pool = tools.find_debits(complaint["customer_id"], since, recv, CHANNELS.get(ex.category))
    text = (complaint.get("subject", "") + " " + complaint["text"]).lower()
    dates = resolve_dates(ex.date_phrase or text, recv)

    scored = []
    for t in pool:
        s, why = 0.0, []
        if ex.amount is not None:
            diff = abs(t["amount"] - ex.amount)
            if diff < 0.005:
                s += 5; why.append("exact amount")
            elif ex.amount_approx and diff <= ex.amount * APPROX_TOLERANCE:
                s += 4 - diff / ex.amount; why.append("approx amount")
            else:
                continue                                  # amount contradicts: not this one
        if ex.card_last4:
            if t["card_last4"] and t["card_last4"] != ex.card_last4:
                continue
            if t["card_last4"] == ex.card_last4:
                s += 2; why.append("card")
        if dates.contains(t["time"].date()):
            s += 3 if dates.exact else 1; why.append(f"date ({dates.rule})")
        if _name_hit(t, ex, text):
            s += 2; why.append("name")
        if ex.category == "FEE_DISPUTE":
            if ex.fee_type and t["description"].startswith(FEE_PREFIX.get(ex.fee_type, "~")):
                s += 3; why.append("fee type")
            if ex.fee_month and t["txn_time"][:7] == ex.fee_month:
                s += 2; why.append("fee month")
        if ex.category == "DUPLICATE_CHARGE":
            if _has_twin(t, pool):
                s += 4; why.append("has earlier twin")
        s += t["time"].timestamp() / 1e12                  # tiny tie-breaker: prefer the more recent
        scored.append((s, t, why))

    if not scored:
        return Match(None, flags=["NO_MATCH"], reasons=[f"No {ex.category} candidate in the window fits the clues"])
    scored.sort(key=lambda x: x[0], reverse=True)
    best_s, best, why = scored[0]
    m = Match(best, candidates=[(round(s, 2), t["txn_id"]) for s, t, _ in scored[:5]],
              reasons=[f"Matched {best['txn_id']} on: {', '.join(why) or 'only candidate'}"])
    if len(scored) > 1 and int(scored[1][0]) == int(best_s):
        m.flags.append("AMBIGUOUS_MATCH")
    return m
