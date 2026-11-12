"""Dedicated alert investigation page (plan §11.1 page 4)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.ui.api_client import ApiClient

st.set_page_config(page_title="Alert Investigation", page_icon="🔍", layout="wide")
st.title("🔍 Alert Investigation")

client: ApiClient | None = st.session_state.get("client")
if client is None:
    st.warning("Please sign in on the Home page first.")
    st.stop()

alert_id = st.session_state.get("selected_alert_id")
if not alert_id:
    st.info("Select an alert in the **Alert Queue** first.")
    st.stop()

detail = client.alert(alert_id)
a = detail["alert"]

st.subheader(f"Why this alert was raised — {a['alert_id']}")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Normalized score", f"{a['normalized_score']:.1f}")
m2.metric("Priority score", f"{a['priority_score']:.1f}")
m3.metric("Band", a["priority_band"].upper())
m4.metric("Model version", a.get("model_version_id") or "-")
st.caption(f"Employee **{a['employee_id']}** · window {a['window_start']} → {a['window_end']} · "
           f"run `{a['run_id']}` · status **{a['status']}**")

new_status = st.selectbox("Analyst status", ["new", "in_review", "case_linked",
                                             "closed_benign", "closed_suspicious",
                                             "closed_inconclusive"],
                          index=["new", "in_review", "case_linked", "closed_benign",
                                 "closed_suspicious", "closed_inconclusive"].index(a["status"]))
if new_status != a["status"] and st.button("Update alert status"):
    try:
        client.update_alert_status(alert_id, new_status)
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))

expl = detail.get("explanation")
if expl:
    st.markdown(f"**Method:** {expl['method']} · **Baseline used:** {expl['baseline_used']}")
    reasons = pd.DataFrame(expl["feature_reasons"])
    if not reasons.empty:
        st.dataframe(reasons[["feature", "observed", "baseline_median", "robust_z",
                              "ablation_delta_score", "description"]],
                     width='stretch', hide_index=True)
        fig = px.bar(reasons, x="ablation_delta_score", y="feature", orientation="h",
                     title="Ablation impact (negative = feature increases the anomaly score)",
                     color="ablation_delta_score", color_continuous_scale="RdBu_r")
        fig.update_layout(height=320, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width='stretch')

        comp = reasons[["feature", "observed", "baseline_median"]].melt(
            id_vars="feature", var_name="series", value_name="value")
        fig2 = px.bar(comp, x="feature", y="value", color="series", barmode="group",
                      title="Observed vs baseline (top drivers)")
        fig2.update_layout(height=320)
        st.plotly_chart(fig2, width='stretch')

    st.info(f"⚠️ {expl['caveats']}")
    st.markdown("**Analyst verification checklist:** device authorization · assignment context · "
                "role/shift change · travel · data quality (missing families) · alternative explanations.")

st.subheader("Supporting evidence events")
if detail.get("evidence_events"):
    ev = pd.DataFrame(detail["evidence_events"])
    ev["timestamp_utc"] = pd.to_datetime(ev["timestamp_utc"]).dt.strftime("%H:%M:%S")
    st.dataframe(ev[["event_id", "timestamp_utc", "event_type", "host_id", "metadata"]],
                 width='stretch', hide_index=True)
    st.page_link("pages/3_Timeline.py", label="🕒 Open employee timeline")
else:
    st.write("No evidence events linked.")

with st.expander("🔎 Counterfactual what-if (model sensitivity)", expanded=True):
    st.caption("Constrained sensitivity analysis. Never modifies evidence; not an evasion guide.")
    if st.button("Run constrained what-if"):
        cf = client.counterfactual(alert_id)
        st.write(f"Original score: **{cf['original_score']}** → hypothetical: "
                 f"**{cf['hypothetical_score']}**")
        st.dataframe(pd.DataFrame(cf["changes"]), width='stretch', hide_index=True)
        st.warning(cf["constraints"]["disclaimer"])
    if detail.get("counterfactuals"):
        st.json(detail["counterfactuals"])

st.divider()
new_case = st.text_input("Create a case from this alert — title:",
                         value=f"Investigation {a['employee_id']} {str(a['window_start'])[:10]}")
if st.button("Create case & link alert & collect evidence"):
    res = client.create_case(new_case)
    client.link_alert(res["case_id"], alert_id)
    client.collect_evidence(res["case_id"])
    st.success(f"Case `{res['case_id']}` created. See the Cases page.")