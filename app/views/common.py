"""Owner: C. Helpers shared by the console pages: the signed-in user, flash messages, safe actions, queue tables."""
import datetime as dt

import pandas as pd
import streamlit as st

from app import ops
from app import ui_kit as ui


def current_user():
    """The signed-in user, re-read each run so limit changes apply at once."""
    uid = st.session_state.get("user_id")
    return ops.get_user(uid) if uid else None


def flash(tone, text):
    """Show a message after the next rerun (an action usually reruns the page)."""
    st.session_state["flash"] = (tone, text)


def show_flash():
    if "flash" in st.session_state:
        tone, text = st.session_state.pop("flash")
        ui.alert(tone, text)
        st.toast(text, icon={"success": "✅", "error": "⛔", "warning": "⚠️", "info": "ℹ️"}[tone])


def run_action(fn, done_text, *args):
    """Run an ops action; on success flash and rerun, on failure show why. Returns False on failure."""
    try:
        fn(*args)
    except ops.SelfCheckFailed as e:
        ui.alert("error", "Not sent: the reply failed the self-check. Fix it and try again.", e.problems)
        return False
    except ops.PermissionDenied as e:
        ui.alert("error", str(e))
        return False
    except ValueError as e:
        ui.alert("warning", str(e))
        return False
    flash("success", done_text)
    st.rerun()


def sla_text(case, now):
    left = ops.sla_left(case, now)
    if left is None:
        return "closed"
    return f"overdue {ui.duration(left)}" if left.total_seconds() < 0 else f"{ui.duration(left)} left"


def sort_key(case, now):
    left = ops.sla_left(case, now)
    return (case["priority"] or "P9", left.total_seconds() if left is not None else 1e12)


PRIO_TXT = {"P1": "▲ P1", "P2": "◆ P2", "P3": "● P3"}


def queue_table(rows, key, extra_cols=None, height=None):
    """A selectable queue sorted by priority, then SLA time left. Returns the selected case id (first row if none)."""
    now = dt.datetime.now()
    rows = sorted(rows, key=lambda r: sort_key(r, now))
    data = []
    for r in rows:   # what decides the next pick comes first: priority, case, money, time left
        item = {"Priority": PRIO_TXT.get(r["priority"], r["priority"] or "—"), "Case": r["complaint_id"],
                "Refund (RM)": r["refund_amount_myr"], "SLA": sla_text(r, now),
                "Category": ui.nice(r["category"]), "Outcome": ui.nice(r["outcome"]) if r["outcome"] else "—",
                "Status": ui.STATUS.get(r["status"], ("", "", r["status"]))[2]}
        for col, fn in (extra_cols or {}).items():
            item[col] = fn(r)
        data.append(item)
    event = st.dataframe(
        pd.DataFrame(data), hide_index=True, on_select="rerun", selection_mode="single-row", key=key,
        width="stretch", height=height or min(40 + 35 * max(len(data), 1), 250),
        column_config={"Refund (RM)": st.column_config.NumberColumn(format="accounting", alignment="right"),
                       "Priority": st.column_config.TextColumn(width="small"),
                       "SLA": st.column_config.TextColumn(help="Time left to acknowledge the customer (SLA policy)")})
    picked = event.selection.rows
    return rows[picked[0]]["complaint_id"] if picked else rows[0]["complaint_id"]


def guard_view(user, case):
    """Show a case only to someone allowed to see it; returns False (with a message) otherwise."""
    reason = ops.why_not(user, "view", case)
    if reason:
        ui.alert("warning", f"You can't open {case['complaint_id']}: {reason}.")
        return False
    return True
