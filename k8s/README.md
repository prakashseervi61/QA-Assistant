# QA Assistant — Kubernetes Manifests (backend only)

Deployment manifests for the QA-Assistant backend API. The frontend is a
separate static artifact and is **not** covered here.

## ⚠️ UNVERIFIED — no live cluster

These manifests were authored from a **static review of the repository
only**. **No cluster was available**: nothing was applied, nothing was
`kubectl apply --dry-run=server`-validated, and no API server was contacted.

Before any real deployment, run (with a `kubectl` context pointing at a
real or ephemeral cluster):

```bash
# client-side syntax + schema check against the cluster's API server
kubectl apply --dry-run=client -f k8s/
kubectl apply --dry-run=server -f k8s/
```

Then validate schema/version availability (the manifests use `apps/v1`,
`autoscaling/v2`, `networking.k8s.io/v1` — all GA since k8s 1.19/1.23/1.19
respectively):

```bash
kubectl api-resources | grep -E "deployments|horizontalpodautoscalers|ingresses"
```

## Files

| File | Kind | Notes |
|---|---|---|
| `deployment.yaml` | Deployment | 2 replicas, `your-registry/qa-assistant:latest` (placeholder), probes on `/api/health`, envFrom ConfigMap + Secret |
| `service.yaml` | Service | ClusterIP on port 8000 → named port `http` |
| `ingress.yaml` | Ingress | `qa-assistant.example.com` placeholder, TLS block commented with TODO |
| `hpa.yaml` | HorizontalPodAutoscaler | min 2 / max 8, CPU 70% (autoscaling/v2) |
| `configmap.yaml` | ConfigMap | Non-secret env — **all feature flags OFF** |
| `secret.yaml` | Secret | **Template only** — empty stringData placeholders, no real values |
| `README.md` | — | This file |

## Apply order

```bash
# 1. Config + secrets first (the Deployment references them via envFrom)
kubectl create secret generic qa-assistant-secrets --from-env-file=secrets.env
kubectl apply -f k8s/configmap.yaml

# 2. Workload + network
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# 3. Autoscaling, then ingress (hostname/TLS depend on your setup)
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/ingress.yaml

# 4. Verify
kubectl rollout status deployment/qa-assistant
kubectl get pods -l app=qa-assistant
kubectl get hpa qa-assistant-hpa
kubectl get ingress qa-assistant
```

(All resources are namespace-less in the manifests — they land in your
current `kubectl` namespace. Add `-n <ns>` / `metadata.namespace` as needed.)

## Secrets — recommended pattern

`k8s/secret.yaml` is a **template with empty placeholders only**. Do not put
real values in it. Create the secret from an untracked env file instead
(keep `secrets.env` out of Git — add it to `.gitignore`):

```bash
# secrets.env (example — never commit)
GEMINI_API_KEY=your_gemini_api_key
AUTH_API_KEY=your_auth_api_key
SECRET_KEY=$(openssl rand -hex 32)   # any long random value
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/qa_assistant

kubectl create secret generic qa-assistant-secrets --from-env-file=secrets.env
```

The Deployment pulls env via `envFrom` (ConfigMap `qa-assistant-config` +
Secret `qa-assistant-secrets`). Key names match the app's real settings
(`src/infrastructure/config/settings.py`, pydantic `case_sensitive=False`).

> **Auth note:** with `ENABLE_AUTH=true` the app **refuses to start** if
> `SECRET_KEY` is still the bundled dev default (`dev-secret-change-me`).
> Always set a strong `SECRET_KEY` in the Secret.

## Health checks

Verified from the repo source:

- `GET /api/health` — defined in
  `src/presentation/api/routes/health.py` (`/health`) and mounted under the
  `/api` prefix in `src/presentation/api/app.py`.
- Deliberately **public** (no auth), so it is safe for liveness/readiness
  probes.
- Port **8000** — Dockerfile `EXPOSE 8000` and
  `uvicorn ... --port 8000`.

## Image

`image: your-registry/qa-assistant:latest` in `deployment.yaml` is a
placeholder — replace it with the tag you build from the root `Dockerfile`
(`python:3.11-slim`, uvicorn factory `src.presentation.api.app:create_app`).

## Scaling notes

- HPA scales the Deployment between **2 and 8** replicas at **70% CPU** of
  the pod request (256m). Watch `kubectl describe hpa qa-assistant-hpa`.
- ⚠️ **Statefulness caveats before scaling out:**
  - **ChromaDB** persists to `CHROMA_PERSIST_DIR` (`./data/chroma`). Without
    a mounted volume (e.g. PVC/emptyDir per pod) embeddings are **rebuilt on
    every pod start** and are **not shared** across pods. Use a shared
    volume (ReadWriteMany PVC) or a separate Chroma/Qdrant service for a
    multi-replica deployment.
  - **Conversation storage** is in-memory unless `DATABASE_URL` is set
    (requires the optional `[postgres]` extra). With 2+ replicas and no DB,
    conversations and rate-limit counters are per-pod and non-deterministic.
  - **Rate limiting** is an in-memory sliding window keyed on client IP. As
    noted in `.env.example`, behind a reverse proxy the app sees the proxy's
    IP — per-pod counters mean the effective limit multiplies by replica
    count.
  - **huggingface embeddings** download the model (~80–100 MB) on first
    start per pod — see the `startupProbe` in `deployment.yaml`.
- Rolling updates use `maxUnavailable: 0, maxSurge: 1` so 2 replicas keep
  serving during deploys.
- Manual rollback: `kubectl rollout undo deployment/qa-assistant`.

## Environment variables

- ConfigMap keys mirror `.env.example` / `settings.py` exactly (no invented
  names). All optional features are **off** (`ENABLE_AUTH=false`,
  `ENABLE_RATE_LIMITING=false`, `ENABLE_GUARDRAILS=false`,
  `ENABLE_INCREMENTAL_INGESTION=false`, `ENABLE_TRACING=false`,
  `ENABLE_PROMPT_AB_TESTING=false`, `ENABLE_USAGE_TRACKING=false` — the code
  default for usage tracking is `true`).
- `EMBEDDING_PROVIDER=huggingface` matches the `.env.example` recommended
  keyless setup; switch to `gemini`/`openai` and add the corresponding key
  in the Secret if preferred.
