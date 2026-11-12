"""Reports & exports history with independent hash verification (plan §11.1 page 7)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.ui.api_client import ApiClient, ApiError

st.set_page_config(page_title="Reports & Exports", page_icon="📤", layout="wide")
st.title("📤 Reports & Exports")

client: ApiClient | None = st.session_state.get("client")
if client is None:
    st.warning("Please sign in on the Home page first.")
    st.stop()

exports = client.list_exports()
if not exports:
    st.info("No exports generated yet. Create a case and export it from the Cases page.")
    st.stop()

df = pd.DataFrame(exports)
df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
st.dataframe(df[["export_id", "case_id", "case_title", "status", "created_at"]],
             width='stretch', hide_index=True)

choice = st.selectbox("Select export", exports,
                      format_func=lambda e: f"{e['export_id']} · {e['case_title'][:30]} · {e['status']}")

c1, c2 = st.columns(2)
if choice["status"] == "verified":
    if c1.button("🔎 Verify hashes now (independent re-check)"):
        v = client.verify_export(choice["export_id"])
        st.session_state[f"verify_{choice['export_id']}"] = v
    v = st.session_state.get(f"verify_{choice['export_id']}")
    if v:
        ok_zip = v["zip_integrity"] == "verified"
        ok_pkg = v["manifest_check"] == "verified"
        (st.success if ok_zip else st.error)(
            f"ZIP integrity: **{v['zip_integrity']}** (recomputed `{v['zip_sha256_recomputed'][:16]}…`)")
        (st.success if ok_pkg else st.error)(
            f"Manifest check: **{v['manifest_check']}** — {v['files_checked']} files verified")
        if v["mismatches"]:
            st.error(f"Mismatched files: {', '.join(v['mismatches'])}")

    pdf_bytes = client.download(f"/downloads/{choice['export_id']}/pdf")
    zip_bytes = client.download(f"/downloads/{choice['export_id']}/zip")
    c2.download_button("⬇️ report.pdf", pdf_bytes,
                       file_name=f"case_{choice['case_id']}_report.pdf", mime="application/pdf")
    c2.download_button("⬇️ evidence ZIP", zip_bytes,
                       file_name=f"case_{choice['case_id']}_evidence.zip", mime="application/zip")
    st.caption(f"Stored ZIP SHA-256: `{choice['zip_sha256']}`")
else:
    st.warning(f"Export status is `{choice['status']}` — downloads unavailable.")