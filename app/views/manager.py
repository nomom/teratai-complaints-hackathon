"""Owner: C. Manager / admin: the oversight console. Headline numbers, where the open work is, what staff did."""
import altair as alt
import pandas as pd
import streamlit as st

from app import ops
from app import ui_kit as ui
from app.views.common import current_user

def pct(v):
    return "—" if v is None else f"{100 * v:.0f}%"


def category_chart(open_by_category, theme):
    """Open cases by category: one series, one violet hue, value labels at the bar ends, hover tooltip.
    Colours come from the theme's tokens (ui.chart_colors), so the chart follows the light/dark switch."""
    c = ui.chart_colors(theme)
    df = pd.DataFrame([{"Category": ui.nice(k), "Open cases": v} for k, v in open_by_category.items()])
    base = alt.Chart(df).encode(
        y=alt.Y("Category:N", sort="-x", title=None,
                axis=alt.Axis(labelColor=c["label"], labelFontSize=12.5, ticks=False, domain=False, labelPadding=8)),
        x=alt.X("Open cases:Q", title=None,
                axis=alt.Axis(labelColor=c["label"], gridColor=c["grid"], domain=False, ticks=False,
                              tickMinStep=1, format="d")))
    bars = base.mark_bar(color=c["bar"], cornerRadiusEnd=4, height={"band": 0.6}).encode(
        tooltip=[alt.Tooltip("Category:N"), alt.Tooltip("Open cases:Q")])
    labels = base.mark_text(align="left", dx=6, color=c["label"], fontSize=12.5).encode(text="Open cases:Q")
    # One configure() call: a second one would replace this config (and bring back the view frame)
    return (bars + labels).properties(height=max(120, 34 * len(df))).configure(
        background=c["background"], font="Inter, IBM Plex Sans, sans-serif", view={"stroke": None})


@st.fragment(run_every=10)
def live():
    m = ops.metrics()
    by = m["by_status"]
    ui.render(ui.grid([
        ui.kpi("Open cases", f"{m['open']:,}", f"{m['total']:,} in the store"),
        ui.kpi("Escalations", f"{by.get(ops.ESCALATED, 0):,}", "waiting for a manager"),
        ui.kpi("SLA overdue", f"{m['sla_overdue']:,}", f"{m['sla_at_risk']:,} due within the hour"),
        ui.kpi("Auto-resolved", pct(m["auto_rate"]), "of decided cases, no person needed"),
        ui.kpi("Override rate", pct(m["override_rate"]), f"of {m['human_final']} human decisions changed the draft"),
        ui.kpi("Pipeline time", f"{m['avg_ms']:.0f} ms" if m["avg_ms"] is not None else "—",
               f"per complaint · {m['tokens_per_case']:,.0f} LLM tokens" if m["tokens_per_case"] is not None
               else "per complaint"),
    ]))
    st.write("")
    left, right = st.columns([1.5, 1], gap="large")
    with left:
        with st.container(border=True):
            ui.render('<p class="tk-h">Open cases by category</p>')
            if m["open_by_category"]:
                st.altair_chart(category_chart(m["open_by_category"], ui.current_theme()), theme=None, width="stretch")
                with st.expander("Table view"):
                    st.dataframe(pd.DataFrame([{"Category": ui.nice(k), "Open cases": v}
                                               for k, v in sorted(m["open_by_category"].items(), key=lambda x: -x[1])]),
                                 hide_index=True, width="stretch")
            else:
                ui.empty_state("No open cases", "Everything taken in has been resolved.")
    with right:
        with st.container(border=True):
            ui.render('<p class="tk-h">Cases by status</p>')
            items = [f'<dt>{ui.status_badge(s)}</dt><dd class="tk-num" style="text-align:right">{by.get(s, 0):,}</dd>'
                     for s in ops.OPEN + ops.CLOSED if by.get(s)]
            if items:
                ui.render(f'<dl class="tk-kv" style="grid-template-columns:1fr max-content;row-gap:10px">{"".join(items)}</dl>')
            else:
                ui.empty_state("No cases yet")


def render():
    current_user()
    ui.page_header("Operations overview", "Complaints across every queue · refreshes every 10 seconds", glow=True)
    live()
    st.write("")
    with st.container(border=True):
        ui.render('<p class="tk-h">Recent staff actions</p>')
        acts = ops.recent_actions(25)
        if acts:
            names = {u["user_id"]: u["name"] for u in ops.users()}
            label = lambda s: ui.STATUS.get(s, ("", "", ui.nice(s)))[2]  # noqa: E731
            st.dataframe(pd.DataFrame([{
                "When": a["ts"][5:16], "Case": a["complaint_id"], "Who": names.get(a["user_id"], a["user_id"]),
                "Role": ops.ROLES.get(a["role"], a["role"]), "Action": ui.nice(a["action"]),
                "Status": f"{label(a['from_status'])} → {label(a['to_status'])}" if a["from_status"] != a["to_status"]
                else label(a["to_status"]),
                "Reason": a["reason"] or ""} for a in acts]), hide_index=True, width="stretch",
                column_config={"When": st.column_config.TextColumn(width="small"),
                               "Reason": st.column_config.TextColumn(width="large")})
        else:
            ui.empty_state("No staff actions yet", "Approvals, rejections, escalations and fraud steps show up here.")
