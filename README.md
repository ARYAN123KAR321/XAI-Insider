# XAI-Insider

**Explainable AI for Insider Threat Detection and Forensic Case Building**
A containerized lab demonstrator: synthetic endpoint telemetry → validated ingestion →
behavioural anomaly detection (Isolation Forest) → explainable alerts → constrained
counterfactuals → forensic cases with PDF + ZIP evidence exports.

> ⚠️ **All data in this project is synthetic.** An alert is a prompt for human review —
> never proof of misconduct.

---

## 🚀 Two Ways to Run

| | **Method 1 — Local** | **Method 2 — Docker Compose** |
|---|---|---|
| Best for | Development, debugging, first-ever run | Clean-machine demo & submission rehearsal |
| Requires | Python 3.11+ | Docker Desktop / Docker Engine |
| Starts with | `python -m uvicorn ...` + `python -m streamlit ...` | `docker compose up --build -d` |

⛔ **Run only ONE method at a time** — both use ports **8000** (API) and **8501** (UI).

Both methods end at the same place:
- Dashboard: **http://localhost:8501**
- Interactive API docs: **http://localhost:8000/docs**
- Login (local synthetic-demo credentials, defined in `.env`):
  `analyst / XAI-Analyst-2026!` · `reviewer / XAI-Reviewer-2026!` · `admin / XAI-Admin-2026!`

---

## Method 1 — Local (do this first)

### 1. Create and activate a virtual environment
**Windows:**
```cmd
python -m venv .venv
.venv\Scripts\activate
```
**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-optional.txt   # torch (CPU) + MLflow → enables FR-18/FR-19
```

### 3. Configure the environment
**Windows:** `copy .env.example .env`  ·  **Linux / macOS:** `cp .env.example .env`
(The defaults work as-is: SQLite database, embedded worker, demo passwords.)

### 4. Initialize database + demo users
```bash
python -m app.db.migrate
```

### 5. Generate, ingest and train the seeded demo dataset (one command)
```bash
python -m app.simulator.seed_demo
```
Takes ~1–3 minutes. Prints per-family ingestion counts, then `Analysis complete: run_id=...`

### 6. Start the API — **Terminal 1**
```bash
python -m uvicorn app.api.main:app --port 8000
```
Leave it running. (Restart this terminal whenever you change API/backend code.)

### 7. Start the dashboard — **Terminal 2** (new window, venv activated)
```bash
python -m streamlit run app/ui/Home.py
```
(Streamlit hot-reloads UI files — just refresh the browser after UI edits.)

### 8. Open and verify
- http://localhost:8501 → log in as `analyst`
- Alert Queue shows the seeded high-priority alert (EMP-001, 2026-11-08)
- Stop everything: `Ctrl+C` in both terminals

---

## Method 2 — Docker Compose (clean-machine deployment)

Prerequisite: Docker Desktop running. Stop any local Method-1 terminals first.

### 1. Configure environment
**Windows:** `copy .env.example .env`  ·  **Linux / macOS:** `cp .env.example .env`

### 2. Build and start all services (api, worker, ui, postgres)
```bash
docker compose up --build -d
```

### 3. Apply migrations and seed the demo dataset
```bash
docker compose exec api python -m app.db.migrate
docker compose exec api python -m app.simulator.seed_demo
```

### 4. Check health and open
```bash
docker compose ps
docker compose logs --tail=50 api
```
- Dashboard: http://localhost:8501 · API docs: http://localhost:8000/docs

### 5. Stop / reset
```bash
docker compose down        # stop, keep data volumes
docker compose down -v     # FULL reset (database + datasets wiped)
```

### Optional: MLflow tracking server (FR-18)
```bash
docker compose --profile mlflow up -d
```
Tracking UI at http://localhost:5000 (set `ENABLE_MLFLOW=true` in `.env`).

---

## ✅ Verify either method worked
1. `GET http://localhost:8000/api/v1/health` → `{"status": "ok", ...}`
2. Dashboard → **Alert Queue** → seeded high-band alert exists
3. **Cases** → open/create a case → export PDF + ZIP → hash verification passes
4. Full guided walkthrough: `docs/DEMO_GUIDE.md`

## 🧪 Tests
```bash
pytest -q
```

## 🛠 Useful scripts (run from project root)
| Command | Purpose |
|---|---|
| `python -m scripts.generate_data --seed 7 --days 7` | Write a new synthetic dataset to disk (no ingestion) |
| `python -m scripts.evaluate` | Re-run detection + print evaluation metrics for latest dataset |
| `python -m scripts.diagnose` | Print datasets / runs / alert counts (troubleshooting) |
| `python -m scripts.reset_demo --yes` | Wipe DB + generated data and reseed users |

> Always use the `python -m ...` form from the project root — running `python scripts/x.py`
> directly fails with `ModuleNotFoundError: No module named 'app'`.

## 📁 Project layout
```
app/            api/ ui/ ingestion/ simulator/ features/ detection/
                explainability/ cases/ db/ security/ config/
tests/          pytest suite (unit, integration, API, export, security)
scripts/        generate, evaluate, diagnose, reset utilities
docs/           architecture, data dictionary, API summary, demo guide,
                model card, test report
deploy/k8s/     optional Kubernetes manifests (post-Compose acceptance)
docker/         Dockerfile          docker-compose.yml at repo root
data/ models/   RUNTIME ONLY — gitignored (DB, uploads, exports, artifacts)
```

## 🔐 Security & responsible use
- `.env` is gitignored; only `.env.example` (placeholders) is committed.
- Pseudonymous employees, metadata only — no email bodies, file contents, or keystrokes.
- Roles enforced server-side; audit trail on uploads, runs, cases, exports.
- Counterfactuals are constrained model-sensitivity illustrations — never evasion recipes.
- See `docs/MODEL_CARD.md` for intended use, limits, and known failure modes.

## 🧯 Troubleshooting
| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Run from project root with `python -m ...` |
| `ModuleNotFoundError: No module named 'sklearn'` | The package is `scikit-learn` (already in requirements) — never `pip install sklearn` |
| `port already in use` (8000/8501) | Only one method at a time; stop the other (`Ctrl+C` or `docker compose down`) |
| Backend code changes not applied | Restart Terminal 1 (`uvicorn`) or `docker compose restart api worker` |
| `use_container_width` deprecation warnings | Harmless Streamlit notice — safe to ignore |
| Alert Queue empty after a new upload | Uploads don't score by themselves: Home → **Run detection pipeline** |
| Stale/corrupt local state | `python -m scripts.reset_demo --yes` (local) or `docker compose down -v` (Docker) |