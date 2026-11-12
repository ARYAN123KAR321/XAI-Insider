"""Alert triage queue (plan §11.1 page 3)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.ui.api_client import ApiClient

st.set_page_config(page_title="Alerts", page_icon="🚨", layout="wide")
st.title("🚨 Alert Queue")

client: ApiClient | None = st.session_state.get("client")
if client is None:
    st.warning("Please sign in on the Home page first.")
    st.stop()

datasets = client.datasets()
if not datasets:
    st.info("No datasets yet — ingest data first.")
    st.stop()

c1, c2 = st.columns([2, 1])
ds = c1.selectbox("Dataset", datasets, format_func=lambda d: d["name"])
band = c2.selectbox("Priority band", ["all", "high", "medium", "low"])

alerts = client.alerts(ds["dataset_id"], None if band == "all" else band)
if not alerts:
    st.success("No alerts for this filter.")
    st.stop()

df = pd.DataFrame(alerts)
df["window_start"] = pd.to_datetime(df["window_start"]).dt.strftime("%Y-%m-%d %H:%M")
st.dataframe(df[["alert_id", "employee_id", "window_start", "normalized_score",
                 "priority_score", "priority_band", "status"]],
             width='stretch', hide_index=True)
st.caption("Bands are triage priorities, **not** probabilities of maliciousness. "
           "Text labels are used in addition to colour.")

choice = st.selectbox("Select alert", alerts,
                      format_func=lambda a: f"{a['alert_id']} · {a['employee_id']} · "
                                            f"{a['priority_band'].upper()} ({a['priority_score']:.0f}) · {a['status']}")

b1, b2 = st.columns([1, 2])
if b1.button("🔍 Open full investigation", type="primary"):
    st.session_state["selected_alert_id"] = choice["alert_id"]
    st.switch_page("pages/4_Alert_Investigation.py")

new_status = b2.selectbox("Quick status change", ["", "in_review"],
                          help="Further transitions happen on the investigation page.")
if new_status and b2.button("Apply status"):
    try:
        client.update_alert_status(choice["alert_id"], new_status)
        st.success(f"Alert status → {new_status}")
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))