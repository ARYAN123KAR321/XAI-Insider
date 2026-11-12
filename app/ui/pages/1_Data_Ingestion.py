"""Data ingestion: synthetic dataset generation, upload, validation report (plan §11.1 page 2)."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.ui.api_client import ApiClient, ApiError

st.set_page_config(page_title="Ingestion", page_icon="📥", layout="wide")
st.title("📥 Data Ingestion")

client: ApiClient | None = st.session_state.get("client")
if client is None:
    st.warning("Please sign in on the Home page first.")
    st.stop()

with st.expander("🧪 Step 1 — Generate synthetic dataset", expanded=True):
    c1, c2, c3 = st.columns([1, 1, 2])
    seed = c1.number_input("Seed", value=42, min_value=0)
    days = c2.number_input("Days", value=7, min_value=4, max_value=14)
    if c3.button("Generate", type="primary"):
        res = client.generate_dataset(int(seed), int(days))
        st.session_state.generated = res
        st.success(f"Generated {len(res['files'])} files in `{res['directory']}` "
                   f"with scenarios: {', '.join(res['scenarios'])}")

gen = st.session_state.get("generated")

st.subheader("Step 2 — Upload files")
dataset_name = st.text_input("New dataset name (leave blank to auto-name)",
                             value=gen["dataset_name"] if gen else "")
dataset_id = st.text_input("…or append to existing dataset_id (optional)", "")
st.session_state.setdefault("job_ids", [])

if gen:
    if st.button("⬆️ Upload all generated files (incl. manifest)"):
        results = []
        first = True
        for family, path_str in gen["files"].items():
            path = Path(path_str)
            fam = "manifest" if family == "manifest" else family
            res = client.upload_file(path, fam, dataset_id or None,
                                     dataset_name if first else None)
            first = False
            job = client.poll_job(res["job_id"])
            st.session_state["job_ids"].append(res["job_id"])
            results.append({"file": path.name, "family": fam, "dataset_id": res["dataset_id"],
                            "status": job["status"], "accepted": job["accepted"],
                            "rejected": job["rejected"], "duplicates": job["duplicates"],
                            "source_sha256": res["source_sha256"][:16] + "…"})
            if not dataset_id:
                dataset_id = res["dataset_id"]
        st.dataframe(results, width='stretch', hide_index=True)
        st.session_state.last_dataset = dataset_id

uploaded = st.file_uploader("Or upload CSV/JSONL telemetry files manually",
                            type=["csv", "jsonl", "json"], accept_multiple_files=True)
if uploaded:
    for uf in uploaded:
        tmp = Path("data/uploads/tmp") / uf.name
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(uf.getbuffer())
        res = client.upload_file(tmp, "auto", dataset_id or None, dataset_name or None)
        job = client.poll_job(res["job_id"])
        st.session_state["job_ids"].append(res["job_id"])
        st.write(f"`{uf.name}` → dataset `{res['dataset_id']}` — {job['status']}: "
                 f"accepted={job['accepted']}, rejected={job['rejected']}, "
                 f"duplicates={job['duplicates']} · SHA-256 `{res['source_sha256'][:16]}…`")
        if job["errors"]:
            with st.expander("Row-level validation errors"):
                st.dataframe(job["errors"], width='stretch')
        if not dataset_id:
            dataset_id = res["dataset_id"]
    st.session_state.last_dataset = dataset_id

if st.session_state.get("job_ids"):
    with st.expander("⬇️ Download validation CSV reports"):
        for jid in st.session_state["job_ids"][-6:]:
            csv_text = client.validation_report_csv(jid)
            st.download_button(f"validation_report_{jid}.csv", csv_text.encode(),
                               file_name=f"validation_report_{jid}.csv", mime="text/csv",
                               key=f"vcsv_{jid}")

st.subheader("Step 3 — Data quality report")
datasets = client.datasets()
if datasets:
    choice = st.selectbox("Dataset", datasets,
                          format_func=lambda d: f"{d['name']} ({d['total_events']} events)")
    if st.button("Show quality report"):
        st.session_state["show_quality"] = choice["dataset_id"]
    if st.session_state.get("show_quality") == choice["dataset_id"] or \
            st.session_state.get("last_dataset") == choice["dataset_id"]:
        q = client.dataset_quality(choice["dataset_id"])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total events", q["total_events"])
        c2.metric("Employees", q["employees"])
        c3.metric("Hosts", q["hosts"])
        c4.metric("Label manifest", "yes" if q["has_label_manifest"] else "no")
        st.dataframe([{"family": k, "count": v} for k, v in q["family_counts"].items()],
                     width='stretch', hide_index=True)
        if q.get("warning"):
            st.warning(q["warning"])
        st.caption(f"Time range: {q['time_range']['start']} → {q['time_range']['end']}")
else:
    st.info("No datasets ingested yet.")