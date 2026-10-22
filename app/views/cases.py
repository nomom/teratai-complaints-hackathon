"""Owner: C. All cases (managers, admin) or the cases a role may see: filter, search, open read-only."""
import streamlit as st

from app import ops, store
from app import ui_kit as ui
from app.views import case_view as cv
from app.views.common import current_user, guard_view, queue_table


def render():
    user = current_user()
    scope = "every case" if user["role"] in ("manager", "admin") else \
        ("fraud cases" if user["role"] == "fraud" else "non-fraud cases")
    ui.page_header("All cases", f"Search and open {scope}, read-only, with the full decision trail")
    rows = ops.cases(user=user)
    if not rows:
        ui.empty_state("No cases yet", "Take in a complaint on the Live intake page, or run the worker.")
        return
    with st.container(border=True):
        c1, c2, c3 = st.columns([1.4, 1.2, 1.2])
        q = c1.text_input("Search", placeholder="case ID, customer ID or words in the complaint")
        statuses = c2.multiselect("Status", sorted({r["status"] for r in rows}), format_func=lambda s: ui.STATUS.get(s, ("", "", s))[2])
        cats = c3.multiselect("Category", sorted({r["category"] for r in rows if r["category"]}), format_func=ui.nice)
        prios = st.pills("Priority", ["P1", "P2", "P3"], selection_mode="multi")
    ql = q.strip().lower()
    shown = [r for r in rows
             if (not ql or ql in r["complaint_id"].lower() or ql in (r["customer_id"] or "").lower() or ql in (r["text"] or "").lower())
             and (not statuses or r["status"] in statuses) and (not cats or r["category"] in cats)
             and (not prios or r["priority"] in prios)]
    st.caption(f"{len(shown)} of {len(rows)} cases")
    if not shown:
        ui.empty_state("No cases match these filters", "Clear a filter to see more.")
        return
    cid = queue_table(shown, "cases-table", extra_cols={"Received": lambda r: r["received_at"], "Customer": lambda r: r["customer_id"]},
                      height=380)
    case = store.get_case(cid)
    st.write("")
    if case and guard_view(user, case):
        with st.container(border=True):
            cv.read_only(case, f"cases-{cid}")
