# Demo Guide (mirrors plan §17.2 — target < 10 minutes)

Credentials (local synthetic demo, set in `.env`): analyst / `XAI-Analyst-2026!`,
reviewer / `XAI-Reviewer-2026!`, admin / `XAI-Admin-2026!`.

1. Open http://localhost:8501, sign in as **analyst**. State clearly: *all data is synthetic*.
2. **Data Ingestion** → Generate (seed 42, 7 days) → Upload all generated files.
   Show accepted/rejected/duplicate counts, SHA-256 column, and the validation CSV download.
3. Show the data-quality report (family coverage, time range, employee/host counts).
4. **Home** → Run detection pipeline. While it runs, explain train/calibration/test split
   and that scenario labels are never used for training.
5. **Model & Evaluation** → show precision/recall/PR-AUC, the model comparison table
   (Isolation Forest vs robust z-score vs autoencoder), scenario-level detection,
   score distribution with threshold line.
6. **Alert Queue** → open the top high-band alert → **Open full investigation**:
   explanation table (observed vs baseline, robust-z, ablation delta), evidence events,
   caveat text, verification checklist.
7. Run the **counterfactual what-if** — emphasize: model sensitivity only, immutable fields,
   evidence is never modified.
8. **Timeline** → follow login → sensitive file reads → archive tool → USB writes;
   alert windows are shaded red.
9. Set alert status **in_review**, then **Create case & link alert & collect evidence**.
10. **Cases** → add a note, collect evidence, record disposition, generate PDF + ZIP,
    download both.
11. **Reports & Exports** → run the independent hash verification (ZIP + per-file manifest).
12. Close with limitations: explanation approximation, false-positive burden, synthetic-only.