# Architecture (plan §5)

Modular monolith + background worker. Streamlit (UI) → FastAPI (API) → worker (ingestion/analysis/export jobs) → PostgreSQL/SQLite + file volumes.

## System Diagram

```text
┌──────────────┐    HTTP/JSON     ┌───────────────┐  job queue (DB)  ┌───────────────┐
│ Streamlit UI │ ───────────────► │  FastAPI API  │ ───────────────► │    Worker     │
│   8 pages    │ ◄─────────────── │   /api/v1/*   │ ◄─────────────── │ ingest/score  │
└──────────────┘      tokens      │ roles + audit │  status/metrics  └───────┬───────┘
                                  │    /export    │                          │
                                  └───────┬───────┘                          │
                                          │                                  │
                                          ▼                                  ▼
                              ┌─────────────────────────────────────────────────────┐
                              │              SQLAlchemy (parameterized)             │
                              └──────────────────────────┬──────────────────────────┘
                                                         │
                                                         ▼
                              ┌─────────────────────────────────────────────────────┐
                              │       PostgreSQL (SQLite for local prototype)       │
                              │   events · windows · models · alerts · cases · audit│
                              └─────────────────────────────────────────────────────┘
```

## Components

| Component | Role |
|---|---|
| **Streamlit UI** | 8 pages; talks to the API over HTTP/JSON |
| **FastAPI API** | `/api/v1/*`; token auth, roles + audit, `/export` |
| **Worker** | Ingestion and scoring; consumes the DB-backed job queue and reports status/metrics |
| **SQLAlchemy** | Parameterized data access layer |
| **PostgreSQL** | Primary store (SQLite for the local prototype): events, windows, models, alerts, cases, audit |

## File Volumes

- `data/uploads` — immutable originals
- `data/cases` — evidence
- `data/exports` — generated exports
- `models/` — model artifacts

**Optional:** MLflow tracking (FR-18)

## Notes

- Module boundaries follow the repo layout in plan §12.5.
- Long jobs (ingestion, analysis, export) return `202` + job/run/export id and are polled (§12.1).
- Every alert stores `run_id` → `model_version` → artifact hash for full lineage (§8.7).