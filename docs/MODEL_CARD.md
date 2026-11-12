# Model Card — XAI-Insider detection stack (v1)

- **Primary model:** scikit-learn `IsolationForest` (200 trees, contamination 0.03, fixed seed).
- **Sanity baseline:** robust z-score composite (max |z| vs employee/peer/global baseline) — §8.4.
- **Optional comparison:** PyTorch autoencoder (FR-19), reported only on the held-out test split.
- **Intended use:** prioritizing unusual *synthetic* endpoint behaviour for human triage in a lab.
- **Not for:** production monitoring, real employees, or any consequential decision-making.
- **Training data:** benign-period windows only; scenario labels used **exclusively** for evaluation.
- **Inputs:** 29 behavioural features over 60-minute rolling windows (15-minute stride),
  median-imputed and robust-scaled. Feature schema v1.0 (registry is the contract).
- **Score:** raw anomaly → percentile-normalized (0–100) against a calibration day;
  priority = 0.70 × normalized + 0.30 × bounded corroboration. Bands are triage priorities,
  **not** probabilities of maliciousness.
- **Evaluation:** precision/recall at threshold, PR-AUC, ROC-AUC, false-alert burden,
  per-scenario recall and detection delay — reported honestly from the untouched test day.
- **Explanations:** robust-z deviations + single-feature ablation through the fitted pipeline;
  labelled as an approximation; no causal claims.
- **Tracking:** parameters/metrics/artifact hashes logged to MLflow when enabled (FR-18).
- **Known limitations:** novelty outside trained feature space; role/shift changes can cause
  false alerts; small synthetic populations make baselines coarse; thresholds are dataset-specific.