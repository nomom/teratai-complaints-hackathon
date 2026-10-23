"""Owner: C. The numbers behind the staff dashboard (GET /dashboard). Read only: nothing here writes to the database.

    summary(filters, date_from, date_to, scope, people)  ->  totals, cases per day and status, counts per column,
                                                            the values each filter can take, and (manager) who acted

Every number answers the same question: the cases received between date_from and date_to that match the filters.
`scope` is the role's own limit (roles.case_filter) and is applied on top of the filters, so the dashboard never counts
a case its viewer could not open in a queue: an officer who filters on the fraud route gets zero, not the fraud cases.
"""
import datetime as dt
import json

from app import store
from app.UserAccessControl import accounts

# Request parameter -> cases column. Each takes one value or several, comma-separated.
FILTERS = {"status": "status", "route": "route", "category": "category", "outcome": "outcome",
           "priority": "priority", "channel": "channel", "language": "reply_language"}
NONE = "NONE"      # an empty column, e.g. the outcome of a case still waiting for the customer; also a filter value

OPEN = ("AWAITING_CUSTOMER", "PENDING_APPROVAL", "FRAUD_QUEUE")
WAITING = ("PENDING_APPROVAL", "FRAUD_QUEUE")             # waiting for a person to approve or reject
AUTO_SENT = ("RESOLVED", "ANSWERED", "SENT")              # the reply went out with no person involved
PEOPLE_ACTIONS = ("approve", "edit_approve", "reject", "holding_reply")


def _in(values) -> str:
    """A fixed list of our own constants as SQL: ('A','B'). Never used for anything a request sent."""
    return "(" + ",".join(f"'{v}'" for v in values) + ")"


def _day(text, name):
    try:
        return dt.date.fromisoformat(text)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a date, YYYY-MM-DD")


def _where(scope, filters=None, date_from=None, date_to=None):
    """The WHERE clause (with its arguments) for the role's scope plus the chosen filters, on table alias c."""
    where, args = [], []
    for column, value in scope.items():
        where.append(f"c.{column} = ?")
        args.append(value)
    for name, values in (filters or {}).items():
        column = FILTERS[name]
        chosen = [v for v in values if v != NONE]
        either = [f"c.{column} IN ({','.join('?' * len(chosen))})"] if chosen else []
        if NONE in values:
            either.append(f"(c.{column} IS NULL OR c.{column} = '')")
        where.append("(" + " OR ".join(either) + ")")
        args.extend(chosen)
    if date_from:
        where.append("c.received_at >= ?")
        args.append(_day(date_from, "date_from").isoformat())
    if date_to:                                                  # the whole of that day
        where.append("c.received_at < ?")
        args.append((_day(date_to, "date_to") + dt.timedelta(days=1)).isoformat())
    return (" WHERE " + " AND ".join(where) if where else ""), args


def parse_filters(params: dict) -> dict:
    """{'category': 'FEE_DISPUTE,FAILED_TRANSFER', 'outcome': None} -> {'category': ['FEE_DISPUTE', 'FAILED_TRANSFER']}."""
    out = {}
    for name in FILTERS:
        values = [v.strip() for v in (params.get(name) or "").split(",") if v.strip()]
        if values:
            out[name] = values
    return out


def summary(filters=None, date_from=None, date_to=None, scope=None, people=False, now=None, last_days=None):
    """The dashboard for one viewer. `scope` is roles.case_filter(user); `people` adds who approved, rejected or sent
    a holding reply on these cases (the manager's view: it names staff). `now` is for tests.

    `last_days` (instead of date_from / date_to) is the last n days up to the newest complaint the viewer can see. The
    bank's data ends on 30 Sep 2026, so counting back from today would leave every "last 30 days" empty.

    The SLA clock matches the queues (web/src/features/cases/lib/sla.ts): the data lives in 2026, so a case's time
    allowed (sla_due - received_at) runs from when it entered our store (created_at)."""
    scope = scope or {}
    if date_from and date_to and _day(date_from, "date_from") > _day(date_to, "date_to"):
        raise ValueError("date_from is after date_to")
    if last_days is not None and last_days < 1:
        raise ValueError("last_days must be at least 1")
    now = (now or dt.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    with store.connect() as con:
        scope_where, scope_args = _where(scope)
        first, last = con.execute(f"SELECT MIN(substr(c.received_at, 1, 10)), MAX(substr(c.received_at, 1, 10)) "
                                  f"FROM cases c{scope_where}", scope_args).fetchone()
        if last_days and last:
            date_to = last
            date_from = (_day(last, "date_to") - dt.timedelta(days=last_days - 1)).isoformat()
        where, args = _where(scope, filters, date_from, date_to)
        k = con.execute(f"SELECT COUNT(*) total, {KPI_SQL} FROM cases c{where}", (now, *args)).fetchone()
        daily = [_kpi_row(r) | {"day": r["day"], "received": r["total"]} for r in con.execute(
            f"SELECT substr(c.received_at, 1, 10) day, COUNT(*) total, {KPI_SQL} FROM cases c{where} GROUP BY 1 ORDER BY 1",
            (now, *args))]
        by_day = [dict(r) for r in con.execute(
            f"SELECT substr(c.received_at, 1, 10) day, c.status, COUNT(*) n FROM cases c{where} GROUP BY 1, 2 ORDER BY 1, 2",
            args)]
        breakdowns = {name: _counts(con, column, where, args) for name, column in FILTERS.items()}
        categories = _categories(con, where, args)

        # The same figures for the period just before, as long as this one, to compare against. Only for a range with
        # both ends: "all dates" has nothing before it.
        previous = None
        if date_from and date_to:
            start, end = _day(date_from, "date_from"), _day(date_to, "date_to")
            before_to = start - dt.timedelta(days=1)
            before_from = before_to - (end - start)
            p_where, p_args = _where(scope, filters, before_from.isoformat(), before_to.isoformat())
            p = con.execute(f"SELECT COUNT(*) total, {KPI_SQL} FROM cases c{p_where}", (now, *p_args)).fetchone()
            previous = {"date_from": before_from.isoformat(), "date_to": before_to.isoformat(), "total": p["total"],
                        "kpis": _kpi_row(p)}

        # What each filter can take, from every case the role may see (not just the filtered ones), so picking one
        # filter never hides the other choices.
        options = {name: sorted(_counts(con, column, scope_where, scope_args)) for name, column in FILTERS.items()}
        acted = _people(con, where, args) if people else None
    return {
        "total": k["total"],
        "kpis": _kpi_row(k),
        "previous": previous,
        "daily": daily,
        "by_day": by_day,
        "breakdowns": breakdowns,
        "categories": categories,
        "options": options,
        "date_range": {"first": first, "last": last},                # of every case the viewer may see
        "applied": {"date_from": date_from or None, "date_to": date_to or None},
        "people": acted,
    }


# The headline figures, as SQL over the cases table (alias c). Takes one argument: now, for the SLA clock.
KPI_SQL = f"""
    COALESCE(SUM(c.status IN {_in(WAITING)}), 0) waiting,
    COALESCE(SUM(c.status = 'AWAITING_CUSTOMER'), 0) awaiting_customer,
    COALESCE(SUM(c.status IN {_in(AUTO_SENT)}), 0) auto_sent,
    COALESCE(SUM(c.status IN {_in(OPEN)}), 0) open,
    COALESCE(SUM(c.status IN {_in(OPEN)} AND c.sla_due IS NOT NULL AND c.created_at IS NOT NULL
        AND julianday(c.sla_due) - julianday(c.received_at) < julianday(?) - julianday(c.created_at)), 0) overdue,
    COALESCE(SUM(CASE WHEN c.outcome = 'REFUND' AND c.status IN {_in(store.SENT_STATUSES)}
                      THEN c.refund_amount_myr END), 0) refund_sent_myr,
    COALESCE(SUM(CASE WHEN c.outcome = 'REFUND' AND c.status IN {_in(WAITING)}
                      THEN c.refund_amount_myr END), 0) refund_waiting_myr"""
KPI_COUNTS = ("waiting", "awaiting_customer", "auto_sent", "open", "overdue")
KPI_MONEY = ("refund_sent_myr", "refund_waiting_myr")


def _kpi_row(r) -> dict:
    return {key: r[key] for key in KPI_COUNTS} | {key: round(r[key], 2) for key in KPI_MONEY}


def _categories(con, where, args):
    """Per category, biggest first: how many cases, each outcome's share of them, and the refunds sent."""
    out = {}
    for r in con.execute(
            f"SELECT COALESCE(NULLIF(c.category, ''), '{NONE}') category, COALESCE(NULLIF(c.outcome, ''), '{NONE}') "
            f"outcome, COUNT(*) n, COALESCE(SUM(CASE WHEN c.outcome = 'REFUND' AND c.status IN "
            f"{_in(store.SENT_STATUSES)} THEN c.refund_amount_myr END), 0) refund FROM cases c{where} GROUP BY 1, 2",
            args):
        row = out.setdefault(r["category"], {"category": r["category"], "n": 0, "refund_sent_myr": 0, "outcomes": {}})
        row["n"] += r["n"]
        row["refund_sent_myr"] = round(row["refund_sent_myr"] + r["refund"], 2)
        row["outcomes"][r["outcome"]] = r["n"]
    return sorted(out.values(), key=lambda c: (-c["n"], c["category"]))


def _counts(con, column, where, args):
    """{value: number of cases}, biggest first; an empty column counts as NONE."""
    return {r["v"]: r["n"] for r in con.execute(
        f"SELECT COALESCE(NULLIF(c.{column}, ''), '{NONE}') v, COUNT(*) n FROM cases c{where} GROUP BY 1 ORDER BY 2 DESC, 1",
        args)}


def _people(con, where, args):
    """Per person: how many of these cases they approved (as drafted or edited), rejected, or sent the fraud holding
    reply on. From the audit log, so it counts every action, including several on one case."""
    rows = con.execute(
        f"SELECT a.actor, a.action, a.detail FROM audit a JOIN cases c ON c.complaint_id = a.complaint_id"
        f"{where}{' AND' if where else ' WHERE'} a.action IN ('human_action', 'holding_reply_sent')", args)
    tally = {}
    for r in rows:
        if r["action"] == "holding_reply_sent":
            kind = "holding_reply"
        else:
            try:
                kind = json.loads(r["detail"]).get("action")
            except (TypeError, ValueError, AttributeError):
                continue
        if kind in PEOPLE_ACTIONS:
            if r["actor"] not in tally:                # the contract endpoint takes any actor name: not always staff
                staff = accounts.get_staff(r["actor"])
                tally[r["actor"]] = {"actor": r["actor"], "name": staff.full_name if staff else r["actor"],
                                     **dict.fromkeys(PEOPLE_ACTIONS, 0)}
            person = tally[r["actor"]]
            person[kind] += 1
    return sorted(tally.values(), key=lambda p: (-sum(p[a] for a in PEOPLE_ACTIONS), p["actor"]))
