# Test Report (plan §16)

Run everything: `pytest -q`

| Scenario | Test / command | Status |
|---|---|---|
| T-01 six valid families | `tests/test_end_to_end.py` (ingest asserts rejected==0 for all families) | automated |
| T-02 malformed rows | `tests/test_validators.py` + manual JSONL upload in UI | automated + manual |
| T-03 duplicate upload | upload same file twice; duplicates counted (`ingest_file_sync` dedupe) | manual step |
| T-04 USB exfiltration detected | `tests/test_end_to_end.py` recall assertion | automated |
| T-05 privilege misuse detected | scenario S2 in `tests/test_simulator.py` + run metrics | automated + metrics |
| T-06 print volume explained | explanation feature_reasons assertion in e2e test | automated |
| T-07 missing telemetry warning | `GET /datasets/{id}/quality` warning field | manual check |
| T-08 counterfactual bounded | e2e test asserts bounds + immutable features | automated |
| T-09 role bypass rejected | `tests/test_api.py::test_reviewer_cannot_create_case` | automated |
| T-10 tampered ZIP detected | `tests/test_exports.py` | automated |
| T-11 Compose restart persistence | `docker compose restart` then inspect cases/alerts | manual runbook |
| T-12 reproducibility | `tests/test_simulator.py::test_generator_deterministic`; run `scripts/evaluate.py` twice with same seed | automated + manual |

Measured results (fill during the final rehearsal on the demo machine):

| Metric | Target (§8.6) | Measured |
|---|---|---|
| Recall on high-priority scenarios | ≥ 80% | ______ |
| High-band false alerts / 100 employee-days | ≤ 2 | ______ |
| Ingestion + scoring time (≤100k events) | a few minutes | ______ |
| Seeded demo walkthrough | < 10 min | ______ |