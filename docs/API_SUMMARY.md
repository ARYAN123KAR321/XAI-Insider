# API Summary (Appendix C + implemented extensions)

Base: `/api/v1` · JSON · UTC · bearer JWT · errors: `{code, message, request_id, field_errors?}`

| Method / path | Purpose |
|---|---|
| POST /auth/login | Obtain token |
| POST /simulator/generate | Generate synthetic dataset files (seed, days) |
| POST /uploads | Upload telemetry (multipart) → 202 {upload_id, dataset_id, job_id, source_sha256} |
| GET /jobs/{job_id} | Ingestion job status + counters |
| GET /jobs/{job_id}/validation-report | Downloadable validation CSV (§6.4) |
| GET /datasets · GET /datasets/{id}/quality | Dataset list / data-quality report |
| GET /datasets/{id}/activity-summary | Heatmap + family counts + alert distribution |
| POST /analysis-runs · GET /analysis-runs[/{id}] | Queue/track detection runs |
| GET /alerts (paginated) · GET /alerts/{id} | Alert queue / detail + explanation + evidence |
| PATCH /alerts/{id}/status | Workflow transitions with audit |
| POST /alerts/{id}/counterfactuals | Constrained what-if (analyst/admin only) |
| GET /employees/{id}/timeline | Ordered timeline with source references |
| POST /cases · GET /cases[/{id}] | Case CRUD |
| POST /cases/{id}/alerts · /notes · /disposition · /evidence · /review | Case lifecycle |
| POST /cases/{id}/exports · GET /exports/{id} · GET /downloads/{id}/{pdf,zip} | Exports |
| GET /reports/exports · GET /reports/exports/{id}/verify | Export history / hash verification |
| GET /models · GET /models/runs/{id}/score-distribution | Model registry / evaluation views |
| GET /health | Health check |