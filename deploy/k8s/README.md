# Kubernetes deployment (FR-20 — optional, after Compose acceptance)

Prerequisite: the Docker Compose deployment and acceptance checklist (§16.2) pass.

1. Build and load the image into your cluster:
   `docker build -t xai-insider:1.0.0 .` (then `kind load` / `minikube image load` / registry push).
2. `cp deploy/k8s/secret.example.yaml deploy/k8s/secret.yaml` and set real values.
3. Apply: `kubectl apply -f deploy/k8s/`
4. Migrate + seed:
   `kubectl -n xai-insider exec deploy/xai-api -- python -m app.db.migrate`
   `kubectl -n xai-insider exec deploy/xai-api -- python -m app.simulator.seed_demo`
5. Dashboard: `http://<node>:30851` · API: internal service `xai-api:8000`.