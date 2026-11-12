"""Employee/session timeline with event-family lanes and alert shading (plan §11.1 page 5)."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from app.ui.api_client import ApiClient

st.set_page_config(page_title="Timeline", page_icon="🕒", layout="wide")
st.title("🕒 Employee Timeline")

client: ApiClient | None = st.session_state.get("client")
if client is None:
    st.warning("Please sign in on the Home page first.")
    st.stop()

datasets = client.datasets()
if not datasets:
    st.info("No datasets yet.")
    st.stop()

ds = st.selectbox("Dataset", datasets, format_func=lambda d: d["name"])
alerts = client.alerts(ds["dataset_id"])
employees = sorted({a["employee_id"] for a in alerts}) or ["EMP-001"]
emp = st.selectbox("Employee (pseudonym)", employees)

# Default to the last day that actually has data (no hard-coded date)
try:
    q = client.dataset_quality(ds["dataset_id"])
    end_range = (q.get("time_range") or {}).get("end")
    default_day = pd.Timestamp(end_range).date() if end_range else pd.Timestamp.today().date()
except Exception:  # noqa: BLE001
    default_day = pd.Timestamp.today().date()
date = st.date_input("Day (UTC)", value=default_day)

# FIXED: build end from a *date* isoformat, not a Timestamp isoformat
next_day = date + timedelta(days=1)
start = f"{date.isoformat()}T00:00:00+00:00"
end = f"{next_day.isoformat()}T00:00:00+00:00"

try:
    events = client.timeline(ds["dataset_id"], emp, start, end)
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load timeline: {exc}")
    st.stop()

if not events:
    st.info(f"No events for **{emp}** on {date.isoformat()}. "
            f"Try another day (data range ends {default_day.isoformat()}) or another employee.")
    st.stop()

df = pd.DataFrame(events)
df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])  # naive UTC (matches DB + vrect bounds)
df["detail"] = df["metadata"].apply(
    lambda m: ", ".join(f"{k}={v}" for k, v in list(m.items())[:4]))

fig = px.scatter(df, x="timestamp_utc", y="event_type", color="event_type",
                 hover_data=["event_id", "host_id", "detail"],
                 title=f"Activity timeline — {emp} on {date.isoformat()} "
                       f"(hover for host/metadata; red bands = alert windows)",
                 category_orders={"event_type": ["login", "process", "file_access", "usb",
                                                  "print", "email_metadata"]})
for a in alerts:
    if a["employee_id"] == emp:
        ws = pd.Timestamp(a["window_start"])
        we = pd.Timestamp(a["window_end"])
        if ws.date() == date or we.date() == date:
            fig.add_vrect(x0=ws, x1=we, fillcolor="red", opacity=0.12, line_width=0,
                          annotation_text=f"alert ({a['priority_band']})",
                          annotation_position="top left")
fig.update_layout(height=440, xaxis_title="Time (UTC)", yaxis_title="Event family")
st.plotly_chart(fig, width="stretch")

st.dataframe(df[["event_id", "timestamp_utc", "event_type", "host_id", "session_id", "detail"]],
             width="stretch", hide_index=True)