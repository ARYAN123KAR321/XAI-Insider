"""Forensic case workflow incl. reviewer stage (plan §10.1, §11.1 page 6)."""
from __future__ import annotations

import streamlit as st

from app.ui.api_client import ApiClient, ApiError

st.set_page_config(page_title="Cases", page_icon="📁", layout="wide")
st.title("📁 Forensic Cases")

client: ApiClient | None = st.session_state.get("client")
if client is None:
    st.warning("Please sign in on the Home page first.")
    st.stop()

role = st.session_state.get("user", {}).get("role", "")

c1, c2 = st.columns([2, 1])
new_title = c1.text_input("New case title", "Investigation — suspicious activity")
if c1.button("Create case") and role in ("admin", "analyst"):
    res = client.create_case(new_title)
    st.success(f"Case created: `{res['case_id']}`")

cases = client.cases()
if not cases:
    st.info("No cases yet.")
    st.stop()

case_choice = c2.selectbox("Open case", cases,
                           format_func=lambda c: f"{c['case_id']} · {c['title'][:24]} · {c['status']}")
detail = client.case(case_choice["case_id"])
case = detail["case"]

st.subheader(f"Case {case['case_id']}")
st.write(f"**Title:** {case['title']} · **Status:** `{case['status']}` · "
         f"**Disposition:** {case['disposition'] or '—'} · **Priority:** {case['priority']}")

st.markdown("**Linked alerts:** " + (", ".join(f"`{a}`" for a in case["alert_ids"])
                                      if case["alert_ids"] else "_none_"))
link_id = st.text_input("Link additional alert_id")
if link_id and st.button("Link alert"):
    try:
        client.link_alert(case["case_id"], link_id.strip())
        st.success("Alert linked.")
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not link alert: {exc}  (copy the exact alert_id from the Alert Queue.)")
st.divider()
note = st.text_area("Add investigator note")
if note and st.button("Add note"):
    client.add_note(case["case_id"], note)
    st.rerun()
for n in detail["notes"]:
    st.markdown(f"> 📝 {n['text']}  \n> _{n['created_at']}_")

st.divider()
r1, r2, r3 = st.columns(3)
if r1.button("🧾 Collect evidence (hash snapshots)"):
    res = client.collect_evidence(case["case_id"])
    st.success(f"Evidence collected: {res['items_added']} new item(s).")
    st.rerun()

if role in ("reviewer", "admin"):
    if case["status"] == "open" and r2.button("👀 Start review"):
        client.review_case(case["case_id"], "start_review")
        st.rerun()
    comment = r2.text_input("Review comment")
    if case["status"] == "under_review" and r2.button("✅ Complete review"):
        client.review_case(case["case_id"], "complete_review", comment)
        st.rerun()

disp = r3.selectbox("Disposition", ["needs_follow_up", "benign", "suspicious", "inconclusive"])
rationale = r3.text_input("Rationale")
if r3.button("Record disposition"):
    client.disposition(case["case_id"], disp, rationale)
    st.rerun()

if detail["evidence"]:
    st.markdown("**Evidence register (SHA-256)**")
    st.dataframe(detail["evidence"], width='stretch', hide_index=True)

st.divider()
if st.button("📦 Generate PDF report + evidence ZIP", type="primary"):
    res = client.create_export(case["case_id"])
    with st.spinner("Generating and verifying export..."):
        exp = client.poll_export(res["export_id"])
    if exp["status"] == "verified":
        st.success(f"Export verified. ZIP SHA-256: `{exp['zip_sha256']}`")
        st.session_state[f"export_{case['case_id']}"] = exp
    else:
        st.error(f"Export failed: {exp.get('error')}")

exp = st.session_state.get(f"export_{case['case_id']}")
if exp and exp.get("downloads"):
    d1, d2 = st.columns(2)
    try:
        pdf_bytes = client.download(exp["downloads"]["pdf"])
        zip_bytes = client.download(exp["downloads"]["zip"])
    except Exception as exc:  # noqa: BLE001
        st.error(f"Download failed: {exc} — retry from the Reports & Exports page.")
        pdf_bytes = zip_bytes = None
    if pdf_bytes and zip_bytes:
        d1.download_button("⬇️ Download report.pdf", pdf_bytes,
                           file_name=f"case_{case['case_id']}_report.pdf", mime="application/pdf")
        d2.download_button("⬇️ Download evidence ZIP", zip_bytes,
                           file_name=f"case_{case['case_id']}_evidence.zip", mime="application/zip")
        st.caption("Full export history & independent hash verification: **Reports & Exports** page.")