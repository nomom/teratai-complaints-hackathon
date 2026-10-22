"""Owner: C. Teratai Ops console: the role-based back office on top of the agent (bonus "Best Ops Platform"),
plus a customer portal where a signed-in customer sends complaints and follows the bank's replies.

    python -m streamlit run app/console.py      (needs the worker running: python -m app.worker)

Each role signs in and sees only its own pages (see ops.PAGES); every action is permission-checked again in
app/ops.py. app/ui.py stays as the simple single-page fallback dashboard.
Light/dark: st.session_state["theme"] ("dark" by default), switched from the header or the sidebar.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app import ops  # noqa: E402
from app import ui_kit as ui  # noqa: E402
from app.views import admin, cases, desk, escalations, fraud, intake, manager, portal  # noqa: E402
from app.views.common import current_user, show_flash  # noqa: E402

st.set_page_config(page_title="Teratai Ops", page_icon=":material/spa:", layout="wide")
st.session_state.setdefault("theme", "dark")
ui.inject_css()

# Every page, by key. A role's pages come from ops.PAGES, in this order.
PAGES = {
    "console": (manager.render, "Overview", ":material/monitoring:", "overview", "Oversight"),
    "escalations": (escalations.render, "Escalations", ":material/priority_high:", "escalations", "Oversight"),
    "desk": (desk.render, "Resolution desk", ":material/task_alt:", "desk", "Work"),
    "fraud": (fraud.render, "Fraud workbench", ":material/shield:", "fraud", "Work"),
    "intake": (intake.render, "Live intake", ":material/move_to_inbox:", "intake", "Work"),
    "cases": (cases.render, "All cases", ":material/folder_open:", "cases", "Records"),
    "admin": (admin.render, "Admin", ":material/settings:", "admin", "Platform"),
    "portal_new": (portal.new_complaint, "New complaint", ":material/edit_square:", "new-complaint", "My bank"),
    "portal_mine": (portal.my_complaints, "My complaints", ":material/forum:", "my-complaints", "My bank"),
}
LANDING = {"officer": "desk", "fraud": "fraud", "manager": "console", "admin": "console", "customer": "portal_new"}
LOGO = {"dark": Path(__file__).resolve().parent / "assets" / "logo.svg",          # light text
        "light": Path(__file__).resolve().parent / "assets" / "logo-light.svg"}   # dark text


# ---- Theme toggle: one choice in session state, two mirrored switches ----------------------------------------------
def _theme_changed(src_key):
    st.session_state["theme"] = "dark" if st.session_state[src_key] else "light"


def theme_toggle(where, key):
    """Draw a switch that mirrors st.session_state["theme"]. Switching reruns the page; inputs, filters and the
    current page are kept because every widget has a stable key."""
    st.session_state[key] = st.session_state["theme"] == "dark"     # sync before the widget is drawn
    where.toggle(":material/dark_mode: Dark mode", key=key, on_change=_theme_changed, args=(key,))


def top_bar():
    _, right = st.columns([6, 1.35])
    theme_toggle(right, "theme-top")


def sign_out():
    theme = st.session_state.get("theme", "dark")
    st.session_state.clear()
    st.session_state["theme"] = theme       # the theme outlives the session's sign-in


# ---- Sign-in -------------------------------------------------------------------------------------------------------
def sign_in():
    top_bar()
    ui.render('<div class="tk-signin-glow"></div>')
    _, mid, _ = st.columns([1, 1.15, 1])
    with mid:
        ui.render('<div class="tk-orb" aria-hidden="true"></div>'
                  '<div style="text-align:center"><div class="tk-brand" style="justify-content:center">'
                  '<span class="tk-brand-dot"></span><span class="tk-brand-name">Teratai Bank</span></div>'
                  '<h1 style="margin:6px 0 4px 0;font-size:28px;font-weight:600">Complaints Ops</h1>'
                  '<p class="tk-sub">Sign in to work your queue, or to follow your complaints</p></div>')
        kind = st.segmented_control("I am", ["Bank staff", "Customer"], default="Bank staff", required=True,
                                    key="signin-kind", width="stretch")
        accounts = ops.users(ops.STAFF_ROLES if kind == "Bank staff" else ("customer",))
        with st.form("sign-in", border=True):
            uid = st.selectbox(
                "Account", [u["user_id"] for u in accounts],
                format_func=lambda i: next(
                    (f"{u['name']} · {ops.ROLES[u['role']]}" if u["role"] != "customer"
                     else f"{u['name']} · {u['customer_id']}") for u in accounts if u["user_id"] == i))
            go = st.form_submit_button("Sign in", type="primary", width="stretch")
        st.caption("Demo sign-in with seeded accounts. Each role sees only its own pages.")
        if go:
            st.session_state["user_id"] = uid
            st.rerun()


# ---- Sidebar -------------------------------------------------------------------------------------------------------
def sidebar(user):
    st.logo(str(LOGO[ui.current_theme()]), size="large")
    with st.sidebar:
        if user["role"] == "customer":
            sub = f'Customer ID {ui.esc(user["customer_id"])}'
        else:
            limit = user["approval_limit_myr"]
            sub = f'Approval limit: {ui.esc(ui.money(limit) if limit is not None else "none")}'
        ui.render(ui.card(
            f'<p class="tk-value">{ui.esc(user["name"])}</p>'
            f'<div class="tk-row" style="margin:6px 0">{ui.badge("accent", ops.ROLES[user["role"]])}</div>'
            f'<p class="tk-sub">{sub}</p>'))
        rows = ops.cases(user=user)
        if user["role"] == "customer":
            open_n = sum(r["status"] in ops.OPEN for r in rows)
            ui.render(f'<p class="tk-label" style="margin-top:14px">Your complaints</p>'
                      f'<div class="tk-row" style="justify-content:space-between;margin:6px 0">'
                      f'{ui.badge("warning", "Open", "⏳")}<span class="tk-num">{open_n}</span></div>'
                      f'<div class="tk-row" style="justify-content:space-between;margin:6px 0">'
                      f'{ui.badge("neutral", "Closed", "✓")}<span class="tk-num">{len(rows) - open_n}</span></div>')
        else:
            counts = {}
            for r in rows:
                counts[r["status"]] = counts.get(r["status"], 0) + 1
            mine = [s for s in ops.OPEN if counts.get(s)]
            if mine:
                ui.render('<p class="tk-label" style="margin-top:14px">Open work you can see</p>' + "".join(
                    f'<div class="tk-row" style="justify-content:space-between;margin:6px 0">{ui.status_badge(s)}'
                    f'<span class="tk-num">{counts[s]}</span></div>' for s in mine))
            h = ops.health()
            if not h["inbox_idle"] and not h["worker_ok"]:
                ui.alert("error", f"Worker may be down: a complaint has waited {h['oldest_pending_s']} s.")
        st.write("")
        if st.button("Sign out", key="sign-out", width="stretch", icon=":material/logout:"):
            sign_out()
            st.rerun()
        st.divider()
        theme_toggle(st, "theme-side")


user = current_user()
if not user:
    sign_in()
    st.stop()

sections = {}
for key in ops.PAGES[user["role"]]:
    fn, title, icon, path, section = PAGES[key]
    sections.setdefault(section, []).append(
        st.Page(fn, title=title, icon=icon, url_path=path, default=key == LANDING[user["role"]]))
page = st.navigation(sections)
sidebar(user)
top_bar()
show_flash()
page.run()
