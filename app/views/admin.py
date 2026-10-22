"""Owner: C. Admin: staff and approval limits, platform health, and the pre-demo reset."""
import os

import pandas as pd
import streamlit as st

from app import ops
from app import ui_kit as ui
from app.views.common import current_user, run_action


@st.dialog("Reset the case store")
def reset_dialog(user):
    st.write("Deletes every case, audit entry and staff action, and empties the inbox. Staff accounts are kept. "
             "This can't be undone.")
    typed = st.text_input('Type RESET to confirm')
    if st.button("Delete everything", key="confirm-danger-reset", disabled=typed != "RESET"):
        run_action(ops.reset, "The case store and inbox are empty.", user)


def render():
    user = current_user()
    ui.page_header("Admin", "Staff, platform health and the demo reset")
    h = ops.health()
    m = ops.metrics()
    provider = os.environ.get("LLM_PROVIDER", "")
    worker = ui.badge("success", "Keeping up", "✓") if h["worker_ok"] and not h["inbox_idle"] else \
        (ui.badge("neutral", "Idle: inbox empty", "•") if h["inbox_idle"] else
         ui.badge("error", f"Stuck: oldest file waited {h['oldest_pending_s']} s", "✕"))
    ui.render(ui.grid([
        ui.tile("Worker", worker),
        ui.tile("Inbox waiting", f'<span class="tk-num">{h["pending"]}</span>'),
        ui.tile("Processed files", f'<span class="tk-num">{h["processed"]:,}</span>'),
        ui.tile("Failed files", ui.badge("error", f'{len(h["failed"])} failed', "✕") if h["failed"]
                else ui.badge("success", "None", "✓")),
        ui.tile("LLM (this process)", ui.badge("info", provider, "✦") if provider else ui.badge("neutral", "Off (rules)", "•")),
        ui.tile("Cases in store", f'<span class="tk-num">{m["total"]:,}</span>'),
    ]))
    st.caption("The LLM setting is read from this dashboard's environment; the worker reads its own. "
               "Check a case's trace for what the worker actually used.")
    if h["failed"]:
        with st.expander(f"Failed inbox files ({len(h['failed'])})"):
            st.write("Each has an `.error.txt` next to it in `inbox/failed/`.")
            st.code("\n".join(h["failed"]))

    st.write("")
    with st.container(border=True):
        ui.render('<p class="tk-h">Staff and approval limits</p>')
        st.caption("Refunds above a person's limit are escalated to a manager. Leave the limit empty for no limit.")
        users = ops.users(ops.STAFF_ROLES)
        df = pd.DataFrame([{"User": u["user_id"], "Name": u["name"], "Role": ops.ROLES[u["role"]],
                            "Limit (RM)": u["approval_limit_myr"]} for u in users])
        edited = st.data_editor(df, hide_index=True, width="stretch", disabled=["User", "Name", "Role"], key="users-edit",
                                column_config={"Limit (RM)": st.column_config.NumberColumn(format="accounting", min_value=0,
                                                                                            alignment="right")})
        if st.button("Save limits", type="primary", key="save-limits"):
            for (_, row), u in zip(edited.iterrows(), users):
                new = None if pd.isna(row["Limit (RM)"]) else float(row["Limit (RM)"])
                if new != u["approval_limit_myr"]:
                    ops.set_limit(user, u["user_id"], new)
            st.toast("Limits saved", icon="✅")
            st.rerun()

    st.write("")
    with st.container(border=True):
        ui.render('<p class="tk-h">Before the demo</p>')
        st.caption("Empty the case store so the judges' LIVE-01… complaints start clean. Stop nothing: the worker keeps running.")
        if st.button("Reset case store…", key="reset-danger"):
            reset_dialog(user)
