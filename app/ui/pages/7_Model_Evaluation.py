"""Model versions, evaluation metrics, model comparison (plan §11.1 page 8)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from app.ui.api_client import ApiClient, ApiError

st.set_page_config(page_title="Model & Evaluation", page_icon="📊", layout="wide")
st.title("📊 Model & Evaluation")

client: ApiClient | None = st.session_state.get("client")
if client is None:
    st.warning("Please sign in on the Home page first.")
    st.stop()

models = client.models()
st.subheader("Model versions")
if models:
    st.dataframe(pd.DataFrame(models)[["model_version_id", "algorithm", "parameters",
                                       "artifact_sha256", "trained_at"]],
                 width='stretch', hide_index=True)
else:
    st.info("No models trained yet.")

runs = client.analysis_runs()
st.subheader("Analysis runs")
if not runs:
    st.stop()

run_choice = st.selectbox("Run", runs, format_func=lambda r: f"{r['run_id']} · {r['status']}")
if run_choice["status"] != "completed":
    st.write(f"Status: **{run_choice['status']}** — {run_choice.get('error') or ''}")
    st.stop()

m = run_choice.get("metrics") or {}
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Precision", f"{m.get('precision', 0):.0%}" if m.get("precision") is not None else "-")
c2.metric("Recall", f"{m.get('recall', 0):.0%}" if m.get("recall") is not None else "-")
c3.metric("PR-AUC", m.get("pr_auc", "-"))
c4.metric("ROC-AUC", m.get("roc_auc", "-"))
c5.metric("Alerts", m.get("alerts_raised", "-"))
st.caption(f"Windows scored: {m.get('windows_scored')} · positives: {m.get('positive_windows')} · "
           f"false alerts: {m.get('false_alerts')} · threshold: {m.get('alert_threshold')} · "
           f"tracking backend: {(m.get('tracking') or {}).get('backend', '-')}")

# model comparison: Isolation Forest vs robust z-score vs autoencoder (FR-19)
st.markdown("**Model comparison on the held-out test split**")
rows = []
for name, block in (("isolation_forest (primary)", m),
                    ("robust z-score baseline (§8.4)", m.get("zscore_baseline") or {}),
                    ("autoencoder (optional)", m.get("autoencoder") or {})):
    if not block or block.get("note"):
        rows.append({"model": name, "note": block.get("note", "")})
        continue
    rows.append({"model": name,
                 "precision": block.get("precision"), "recall": block.get("recall"),
                 "pr_auc": block.get("pr_auc"), "roc_auc": block.get("roc_auc"),
                 "alerts": block.get("alerts_raised"), "false_alerts": block.get("false_alerts")})
st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

if m.get("scenarios"):
    st.markdown("**Scenario-level detection (primary model)**")
    st.dataframe(pd.DataFrame(m["scenarios"]), width='stretch', hide_index=True)

try:
    dist = client.score_distribution(run_choice["run_id"])
    hist = pd.DataFrame(dist["histogram"])
    if not hist.empty:
        fig = px.bar(hist, x="bin_start", y="count",
                     title="Score distribution (test split, normalized 0–100)")
        fig.add_vline(x=dist.get("metrics", {}).get("alert_threshold", 85),
                      line_dash="dash", annotation_text="alert threshold")
        st.plotly_chart(fig, width='stretch')
except ApiError:
    pass

with st.expander("Model card (limitations & intended use)"):
    st.markdown("""
- **Intended use:** lab decision-support for triaging synthetic endpoint telemetry.
- **Not intended for:** production monitoring, employment decisions, or any real-person assessment.
- **Training data:** synthetic benign period only; scenario labels used **only** for evaluation.
- **Known failure modes:** novel attack patterns outside the trained feature space; threshold
  sensitivity; role/shift changes may raise false alerts.
- **Explanations** are approximations (robust-z + ablation), not exact attributions.
- Anomaly scores are **never** proof of misconduct.
""")