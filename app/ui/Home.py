"""XAI-Insider dashboard - Overview & login (plan §11.1 page 1)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.ui.api_client import ApiClient, ApiError

st.set_page_config(page_title="XAI-Insider", page_icon="🛡️", layout="wide")

if "client" not in st.session_state:
    st.session_state.client = None
    st.session_state.user = None


def _login_form():
    st.title("🛡️ XAI-Insider")
    st.caption("Explainable AI for Insider Threat Detection and Forensic Case Building — "
               "**synthetic lab demonstrator**")
    with st.form("login"):
        username = st.text_input("Username", value="analyst")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in"):
            try:
                client = ApiClient()
                res = client.login(username, password)
                client.token = res["access_token"]
                st.session_state.client = client
                st.session_state.user = res
                st.rerun()
            except ApiError as exc:
                st.error(str(exc))
    st.info("Default lab accounts: `admin`, `analyst`, `reviewer` — passwords are set in `.env`.")


if st.session_state.client is None:
    _login_form()
    st.stop()

client: ApiClient = st.session_state.client
st.title("🛡️ XAI-Insider — Overview")
st.caption(f"Signed in as **{st.session_state.user['username']}** "
           f"(role: {st.session_state.user['role']}) — synthetic lab data only.")

if st.button("Log out"):
    st.session_state.client = None
    st.session_state.user = None
    st.rerun()

try:
    datasets = client.datasets()
except ApiError as exc:
    st.error(f"API unavailable ({exc}). Start the API with: `uvicorn app.api.main:app --port 8000`")
    st.stop()

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("Datasets")
    if datasets:
        st.dataframe([{
            "dataset_id": d["dataset_id"], "name": d["name"],
            "events": d["total_events"], "labels": "yes" if d["has_labels"] else "no",
            "scenarios": d["scenario_count"],
        } for d in datasets], width='stretch', hide_index=True)
    else:
        st.info("No datasets yet. Use **Data Ingestion** to generate and upload synthetic telemetry.")

with col2:
    st.subheader("Run analysis")
    if datasets:
        ds_choice = st.selectbox("Dataset", datasets, format_func=lambda d: d["name"])
        if st.button("▶️ Run detection pipeline", type="primary"):
            with st.spinner("Queuing analysis run..."):
                res = client.start_analysis(ds_choice["dataset_id"])
            st.info(f"Run queued: `{res['run_id']}`")
            run = client.poll_run(res["run_id"])
            if run["status"] == "completed":
                st.success("Analysis complete. Open **Alert Queue** to triage.")
                m = run.get("metrics") or {}
                if "recall" in m:
                    st.metric("Recall (test split)", f"{m['recall']:.0%}")
                if "precision" in m:
                    st.metric("Precision (test split)", f"{m['precision']:.0%}")
                st.metric("Alerts raised", m.get("alerts_raised", "-"))
            else:
                st.error(f"Run failed: {run.get('error')}")
    st.subheader("Recent runs")
    try:
        runs = client.analysis_runs()[:5]
        st.dataframe([{"run_id": r["run_id"], "status": r["status"]} for r in runs],
                     width='stretch', hide_index=True)
    except ApiError:
        pass

if datasets:
    st.divider()
    st.subheader("Dataset analytics")
    summ_ds = st.selectbox("Dataset for charts", datasets, key="summ",
                           format_func=lambda d: d["name"])
    try:
        s = client.activity_summary(summ_ds["dataset_id"])
        c1, c2 = st.columns(2)
        with c1:
            hm = pd.DataFrame(s["heatmap"],
                              index=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                              columns=[f"{h:02d}" for h in range(24)])
            fig = px.imshow(hm, title="Activity heatmap (hour × weekday)",
                            color_continuous_scale="Blues", aspect="auto")
            fig.update_layout(height=300)
            st.plotly_chart(fig, width='stretch')
        with c2:
            fam = pd.DataFrame([{"family": k, "events": v}
                                for k, v in s["by_family"].items()])
            fig2 = px.bar(fam, x="family", y="events", title="Events by telemetry family")
            fig2.update_layout(height=300)
            st.plotly_chart(fig2, width='stretch')

        c3, c4 = st.columns(2)
        with c3:
            bands = pd.DataFrame([{"band": k, "alerts": v}
                                  for k, v in s["alerts_by_band"].items()])
            fig3 = px.bar(bands, x="band", y="alerts", color="band",
                          title="Alerts by triage priority band",
                          color_discrete_map={"high": "#d62728", "medium": "#ff7f0e",
                                              "low": "#2ca02c"})
            fig3.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig3, width='stretch')
        with c4:
            if s["alerts_by_date"]:
                dates = pd.DataFrame(sorted(s["alerts_by_date"].items()),
                                     columns=["date", "alerts"])
                fig4 = px.bar(dates, x="date", y="alerts", title="Alerts by date")
                fig4.update_layout(height=300)
                st.plotly_chart(fig4, width='stretch')
            else:
                st.write("No alerts yet for this dataset.")
    except ApiError as exc:
        st.warning(f"Could not load summary: {exc}")

st.divider()
st.caption("An anomaly alert is a prompt for human review — never proof of misconduct. "
           "All data in this demonstrator is synthetic.")