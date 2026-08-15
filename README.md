# Production-Grade Telco Customer Churn ML Platform

![CI Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)


## Objective
An end-to-end production ML system for Telco Customer Churn Prediction covering data ingestion, validation, feature engineering, model training, evaluation, serving, monitoring, drift detection, and automated retraining.

---

## Phase 12 — AWS ECR Provisioning & Image Push

### Overview

Phase 12 publishes the Docker image built in Phase 11 to a private **AWS Elastic Container Registry (ECR)** repository. The image is tagged with both `latest` and the current **git commit SHA** — the SHA tag is required by Phase 18 (automated retraining) and subsequent Kubernetes phases to reference immutable image versions.

> **ADR — Repository Lifecycle**
> The ECR repository `telco-churn-api` is a **long-lived project resource**. It is created once by `create_ecr_repo.ps1` and persists for the entire project lifetime. Phase 18's automated retraining pipeline does **not** recreate this repository — it only calls `push_to_ecr.ps1` to tag and push a new image version into the existing repository.

---

### Prerequisites

| Requirement | How to verify |
|---|---|
| AWS CLI installed | `aws --version` |
| AWS CLI configured (region = `ap-south-1`) | `aws configure get region` |
| IAM user has ECR full access | `aws iam list-attached-user-policies --user-name telco-mlops-cli` |
| `aws sts get-caller-identity` succeeds | Run it — must return Account, UserId, Arn |
| Docker Desktop running | `docker info` |
| Local image `telco-churn-api:latest` exists | `docker image inspect telco-churn-api:latest` |

If the local image is missing, build it first:

```powershell
py -3.12 tasks.py docker-build
```

---

### Step 1 — Create the ECR Repository (once only)

```powershell
# From the repo root
.\infra\aws\create_ecr_repo.ps1
```

**Expected output (first run — creates repository):**
```
==> [1/3] Verifying configured AWS region...
       Region OK: ap-south-1

==> [2/3] Checking if repository 'telco-churn-api' already exists...
       Repository not found. Creating it now...

==> [3/3] Creating ECR repository 'telco-churn-api'...

Repository created successfully.

  Repository Name : telco-churn-api
  Repository URI  : 123456789012.dkr.ecr.ap-south-1.amazonaws.com/telco-churn-api
  Repository ARN  : arn:aws:ecr:ap-south-1:123456789012:repository/telco-churn-api
  Region          : ap-south-1
  Scan on Push    : ENABLED
  Encryption      : AES256

Done. Run .\infra\aws\push_to_ecr.ps1 to tag and push the Docker image.
```

**Expected output (subsequent runs — already exists):**
```
==> [1/3] Verifying configured AWS region...
       Region OK: ap-south-1

==> [2/3] Checking if repository 'telco-churn-api' already exists...

Repository already exists — nothing to do.

  Repository URI : 123456789012.dkr.ecr.ap-south-1.amazonaws.com/telco-churn-api
  Region         : ap-south-1
```

**CLI verification:**
```powershell
aws ecr describe-repositories --repository-names telco-churn-api
```

---

### Step 2 — Tag & Push the Image to ECR

```powershell
# From the repo root
.\infra\aws\push_to_ecr.ps1
```

The script performs these steps automatically:
1. Verifies the configured region is `ap-south-1`
2. Derives the AWS account ID via `aws sts get-caller-identity` (never hardcoded)
3. Builds the full repository URI from account ID + region + repo name
4. Verifies the local Docker image `telco-churn-api:latest` exists (exits with a clear message if not)
5. Resolves the current `git rev-parse --short HEAD` for the SHA tag
6. Authenticates Docker with ECR via `aws ecr get-login-password | docker login`
7. Verifies Docker reports **"Login Succeeded"** — aborts immediately if not
8. Tags the image as both `<repo_uri>:latest` and `<repo_uri>:<git-sha>`
9. Pushes both tags
10. Verifies the pushed digest: compares the post-push `RepoDigests` field (manifest digest) against ECR's `imageDigest` — exits non-zero on any mismatch
11. Writes `reports/ecr_push_report.json`

**Expected output:**
```
==> [1/8] Verifying configured AWS region...
       Region OK: ap-south-1

==> [2/8] Fetching AWS account ID via STS...
       Account ID: 123456789012

==> [3/8] Repository URI: 123456789012.dkr.ecr.ap-south-1.amazonaws.com/telco-churn-api

==> [4/8] Verifying local Docker image 'telco-churn-api:latest' exists...
       Image found locally.

==> [5/8] Resolving git commit SHA...
       Git SHA: b41fe4e

==> [6/8] Authenticating Docker with ECR...
       Login Succeeded.

==> [7/8] Tagging and pushing image...
       Tagging as: 123456789012.dkr.ecr.ap-south-1.amazonaws.com/telco-churn-api:latest
       Tagging as: 123456789012.dkr.ecr.ap-south-1.amazonaws.com/telco-churn-api:b41fe4e

       Pushing '...telco-churn-api:latest'...
       [push layers output]

       Pushing '...telco-churn-api:b41fe4e'...
       [push layers output — most layers already exist, only manifest re-pushed]

       Both tags pushed successfully.

==> [8/8] Verifying push digest (RepoDigests vs ECR imageDigest)...
       Local  RepoDigest : sha256:abcdef1234567890...
       ECR    imageDigest: sha256:abcdef1234567890...
       Digest MATCH confirmed.

===========================================================
  Phase 12 — ECR Push COMPLETE
===========================================================

  Repository      : telco-churn-api
  Repository URI  : 123456789012.dkr.ecr.ap-south-1.amazonaws.com/telco-churn-api
  Tags pushed     : latest, b41fe4e
  Manifest Digest : sha256:abcdef1234567890...
  Push Timestamp  : 2026-08-14T05:00:00Z
  Report saved to : reports\ecr_push_report.json
```

---

### Step 3 — Verify in CLI & AWS Console

**CLI verification (run after push):**
```powershell
# List all images in the repository — should show both 'latest' and git SHA tags
aws ecr describe-images --repository-name telco-churn-api

# Inspect the pushed image digest for 'latest'
aws ecr describe-images `
    --repository-name telco-churn-api `
    --image-ids imageTag=latest `
    --query "imageDetails[0].imageDigest" `
    --output text
```

**Console verification:**
1. Open [AWS Console → ECR → ap-south-1 → Repositories](https://ap-south-1.console.aws.amazon.com/ecr/repositories)
2. Click on `telco-churn-api`
3. Confirm **both** `latest` and the git SHA tag (e.g. `b41fe4e`) appear in the **Images** tab
4. Confirm the image digest matches the value in `reports/ecr_push_report.json`

---

### Digest Verification — Design Note

> **Why RepoDigests (not `.Id`)?**
>
> `docker image inspect <image> --format="{{.Id}}"` returns the **image config digest** (SHA256 of the image configuration JSON). ECR's `imageDigest` is the **manifest digest** (SHA256 of the OCI image manifest). These two digest types are fundamentally different and will **always differ**, even on a perfectly correct push.
>
> The correct comparison uses `{{index .RepoDigests 0}}` which Docker populates **only after a successful push**. This field contains the registry's manifest digest in `registry/repo@sha256:...` format — the SHA portion after `@` is identical to ECR's `imageDigest`.

---

### Output Report

After a successful push, `reports/ecr_push_report.json` is written automatically:

```json
{
  "repository_name": "telco-churn-api",
  "region": "ap-south-1",
  "image_tag": "b41fe4e",
  "image_digest": "sha256:abcdef1234567890...",
  "repository_uri": "123456789012.dkr.ecr.ap-south-1.amazonaws.com/telco-churn-api",
  "push_timestamp": "2026-08-14T05:00:00Z"
}
```

---

### Cleanup (Environment Reset)

To delete the ECR repository and all images inside it (e.g. to reset for a clean re-run):

```powershell
aws ecr delete-repository --repository-name telco-churn-api --force
```

> **Warning:** `--force` deletes all images inside the repository without a secondary confirmation prompt. This is irreversible. Re-run `create_ecr_repo.ps1` followed by `push_to_ecr.ps1` to reprovision.

---

### Error Reference

| Error Message | Cause | Fix |
|---|---|---|
| `AWS CLI is configured for region '...'` | Wrong region in `aws configure` | Run `aws configure`, set region to `ap-south-1` |
| `Local image 'telco-churn-api:latest' not found` | Docker image not built | Run `py -3.12 tasks.py docker-build` |
| `Docker login did not report 'Login Succeeded'` | ECR auth failure | Check IAM permissions (`AmazonEC2ContainerRegistryFullAccess`) |
| `Digest verification failed` | Push partially failed or wrong image pushed | Re-run `push_to_ecr.ps1` |
| `Could not retrieve AWS account ID` | AWS credentials expired/missing | Run `aws sts get-caller-identity` to diagnose |

---

## Phase 13 — Kubernetes Deployment (Minikube)

### Overview

Phase 13 deploys the Telco Churn API to a local Minikube cluster using production-aligned
Kubernetes manifests. The manifests live in `infra/k8s/` and are designed to carry forward
intact to EKS (Phase 14+) with minimal changes (storage class, service type, imagePullSecrets).

**Image:** `899640267680.dkr.ecr.ap-south-1.amazonaws.com/telco-churn-api:0595515` (git SHA pinned — not `:latest`)

---

### Manifest Inventory

| File | Purpose |
|---|---|
| `configmap.yaml` | Non-secret runtime config (ports, log level, MLflow URI) |
| `secret.yaml` | **Template only** — placeholder values; real secret injected at deploy time |
| `pvc-models.yaml` | PVC for model artifacts — read-mostly, 1Gi |
| `pvc-mlflow.yaml` | PVC for MLflow tracking store — frequently written, 2Gi |
| `deployment.yaml` | Deployment with startup/liveness/readiness probes, resource limits, rolling update |
| `service.yaml` | NodePort service → `<minikube-ip>:30800` |
| `hpa.yaml` | HPA: CPU ≥70% triggers scale-out, min=1 / max=3 replicas |
| `pdb.yaml` | PodDisruptionBudget: `minAvailable: 1` |

---

### Prerequisites

| Requirement | Verify |
|---|---|
| Minikube running | `minikube status` |
| kubectl configured | `kubectl cluster-info` |
| AWS CLI configured (for ECR) | `aws sts get-caller-identity` |
| metrics-server (for HPA) | `minikube addons enable metrics-server` |

---

### Step 1 — ECR Authentication (choose one option)

#### Option A — `minikube image load` ✅ Recommended for local development

**No AWS credentials inside the cluster.** Pull the image to your local Docker daemon,
then load it directly into Minikube's container runtime. Kubernetes will find the image
locally without contacting ECR.

```powershell
# Authenticate Docker with ECR (one-time per session)
aws ecr get-login-password --region ap-south-1 | `
  docker login --username AWS --password-stdin `
  899640267680.dkr.ecr.ap-south-1.amazonaws.com

# Pull the image to local Docker
docker pull 899640267680.dkr.ecr.ap-south-1.amazonaws.com/telco-churn-api:0595515

# Load into Minikube's container runtime
minikube image load 899640267680.dkr.ecr.ap-south-1.amazonaws.com/telco-churn-api:0595515

# Verify the image is available inside Minikube
minikube image ls | findstr telco-churn-api
```

The Deployment uses `imagePullPolicy: IfNotPresent`, so Kubernetes uses the loaded image
without attempting an ECR pull. Leave `imagePullSecrets` commented out in `deployment.yaml`.

**Advantages:** No AWS credentials inside the cluster, faster iteration, ideal for development.

---

#### Option B — `kubectl create secret docker-registry` (production-like ECR pull)

Creates a Kubernetes pull secret so the cluster can authenticate with ECR directly.
This mirrors how EKS authenticates with ECR and is useful for testing the full registry flow.

```powershell
# Get a fresh ECR login token (tokens expire after 12 hours)
$ECR_TOKEN = aws ecr get-login-password --region ap-south-1

# Create the pull secret in Kubernetes
kubectl create secret docker-registry ecr-credentials `
  --docker-server=899640267680.dkr.ecr.ap-south-1.amazonaws.com `
  --docker-username=AWS `
  --docker-password=$ECR_TOKEN `
  --namespace=default

# Verify secret was created
kubectl get secret ecr-credentials
```

Then **uncomment** the `imagePullSecrets` block in `infra/k8s/deployment.yaml`:

```yaml
# Before deploying, uncomment these lines in deployment.yaml:
imagePullSecrets:
  - name: ecr-credentials
```

> **Token expiry:** ECR tokens expire after 12 hours. If pods fail to pull with `ImagePullBackOff`,
> delete and recreate the secret using the command above.

**Advantages:** Mirrors EKS authentication, tests real registry pulls end-to-end.

---

### Step 2 — Inject the Real API Secret

The committed `secret.yaml` contains only a placeholder. Before deploying, create the
real secret so its value never touches the filesystem or git:

```powershell
# Replace "your-actual-api-key" with a real secret key
kubectl create secret generic telco-churn-secret `
  --from-literal=API_SECRET_KEYS='["your-actual-api-key"]' `
  --dry-run=client -o yaml | kubectl apply -f -

# Verify (value is not printed)
kubectl describe secret telco-churn-secret
```

---

### Step 3 — Copy Model Artifacts onto the PVCs

The PVCs are initially empty. Before the pod can pass the readiness probe, the model
artifacts must exist on `telco-models-pvc`. Use a temporary init pod to copy them:

```powershell
# Apply PVCs first so they are bound
kubectl apply -f infra/k8s/pvc.yaml

# Copy models/ onto telco-models-pvc
kubectl run pvc-init --image=busybox --restart=Never `
  --overrides='{"spec":{"volumes":[{"name":"m","persistentVolumeClaim":{"claimName":"telco-models-pvc"}}],"containers":[{"name":"c","image":"busybox","command":["sh","-c","sleep 3600"],"volumeMounts":[{"name":"m","mountPath":"/mnt"}]}]}}' -- sh -c "sleep 3600"

kubectl wait --for=condition=Ready pod/pvc-init --timeout=60s

# Copy artifacts from local to PVC (adjust path as needed)
kubectl cp models/. pvc-init:/mnt/

# Verify
kubectl exec pvc-init -- ls /mnt/

# Cleanup init pod
kubectl delete pod pvc-init

# Repeat for mlflow PVC (telco-mlflow-pvc → /mnt/mlruns and mlflow.db)
```

---

### Step 4 — Deploy All Manifests

> [!IMPORTANT]
> `kubectl apply -f infra/k8s/` applies **all files** in the directory including `secret.yaml`,
> which contains the placeholder value. If you run `kubectl apply -f infra/k8s/` after already
> injecting the real secret (Step 2), it will **overwrite** it with the placeholder.
>
> Use the explicit per-file approach below, which skips `secret.yaml`:

```powershell
# Dry-run validation first (validates all manifests including secret template)
kubectl apply --dry-run=client -f infra/k8s/

# Deploy non-secret resources (excludes secret.yaml to protect the real secret)
kubectl apply -f infra/k8s/configmap.yaml
kubectl apply -f infra/k8s/pvc-models.yaml
kubectl apply -f infra/k8s/pvc-mlflow.yaml
kubectl apply -f infra/k8s/deployment.yaml
kubectl apply -f infra/k8s/service.yaml
kubectl apply -f infra/k8s/hpa.yaml
kubectl apply -f infra/k8s/pdb.yaml

# Watch rollout completion (stronger than just checking pod state)
kubectl rollout status deployment/telco-churn-api
```

> [!NOTE]
> If you want to use `kubectl apply -f infra/k8s/` (e.g. in CI), inject the real secret
> **after** that command using `kubectl create secret ... | kubectl apply -f -`.
> A `kubectl rollout restart deployment/telco-churn-api` is then required to pick up the new value.

---

### Step 5 — Verify Deployment

Run through the full verification checklist in order:

```powershell
# 1. Rollout completed successfully
kubectl rollout status deployment/telco-churn-api
# Expected: "deployment "telco-churn-api" successfully rolled out"

# 2. Pod is Running and 1/1 Ready
kubectl get pods -l app=telco-churn-api
# Expected: STATUS=Running, READY=1/1

# 3. Probes passing — no restarts
kubectl describe pod -l app=telco-churn-api
# Expected: Liveness/Readiness probe succeeding, RESTART COUNT=0

# 4. Confirm model artifacts are mounted and readable (catches PVC mount issues)
kubectl exec -it $(kubectl get pod -l app=telco-churn-api -o jsonpath='{.items[0].metadata.name}') `
  -- ls -la /app/models/
# Expected: feature_pipeline.joblib, decision_threshold.json, feature_schema.json present

# 5. Check logs for clean startup
kubectl logs -l app=telco-churn-api --tail=50
# Expected: "Startup complete: Production model version X ready for inference"
# No: CrashLoopBackOff, model load errors, repeated restarts

# 6. Expose the service
minikube service telco-churn-api --url
# OR: kubectl port-forward svc/telco-churn-api 8000:8000

# 7. Health check (no auth required)
curl http://<minikube-url>/health/readiness
# Expected: {"status":"ready","model_loaded":true,...}

# 8. Prediction (requires API key from secret)
curl -X POST http://<minikube-url>/predict `
  -H "Content-Type: application/json" `
  -H "X-API-Key: your-actual-api-key" `
  -d '{
    "customerID": "test-001",
    "gender": "Male",
    "SeniorCitizen": 0,
    "Partner": "Yes",
    "Dependents": "No",
    "tenure": 12,
    "PhoneService": "Yes",
    "MultipleLines": "No",
    "InternetService": "Fiber optic",
    "OnlineSecurity": "No",
    "OnlineBackup": "No",
    "DeviceProtection": "No",
    "TechSupport": "No",
    "StreamingTV": "No",
    "StreamingMovies": "No",
    "Contract": "Month-to-month",
    "PaperlessBilling": "Yes",
    "PaymentMethod": "Electronic check",
    "MonthlyCharges": 70.35,
    "TotalCharges": "845.5"
  }'
# Expected: {"probability":..., "decision":"churn"/"retain", "churn_predicted":true/false,...}
```

---

### Updating the Image Tag After Each Push

After each `push_to_ecr.ps1` run, update the image tag in `deployment.yaml`:

```powershell
# Get the latest git SHA
git rev-parse --short HEAD

# Edit infra/k8s/deployment.yaml — update this line:
#   image: 899640267680.dkr.ecr.ap-south-1.amazonaws.com/telco-churn-api:<NEW-SHA>

# Re-apply (triggers rolling update)
kubectl apply -f infra/k8s/deployment.yaml
kubectl rollout status deployment/telco-churn-api
```

---

### Design Notes

#### Why hostPath / "standard" StorageClass?

Minikube's `standard` StorageClass uses `hostPath` — data lives on the Minikube VM's
local filesystem. This is **intentional for local development only**:

- Minikube is a **single-node** cluster. HA, replication, and cross-node scheduling
  don't apply. Cloud storage classes (`gp2`, `gp3`, `efs`) are unavailable without plugins.
- Development workflow: model artifacts are copied onto the PVC once; the pod reads them
  at every startup. MLflow writes experiment runs to the mlflow PVC continuously.
- **Not production HA storage.** In Phase 14+ (EKS), the `storageClassName` field in
  `pvc.yaml` changes to the appropriate cloud class (e.g., `gp3`). PVC names and mount
  paths remain identical — zero changes needed in `deployment.yaml`.

#### Why Two PVCs?

| PVC | Contents | Access Pattern | Future Storage Class |
|---|---|---|---|
| `telco-models-pvc` | models/, feature_pipeline.joblib, decision_threshold.json, feature_schema.json | Read-mostly; updated only on model promotion | ReadWriteMany (EFS) for multi-pod serving |
| `telco-mlflow-pvc` | mlruns/, mlflow.db | Frequently written (every training run, metric log) | ReadWriteOnce (gp3) — high IOPS |

Combining them into one PVC would force both into the same access mode and storage class,
preventing independent scaling and storage class optimization in later phases.

#### Why NodePort (not LoadBalancer)?

Minikube has no cloud load balancer provisioner. `LoadBalancer` type services stay in
`Pending` indefinitely on bare Minikube. `NodePort` is immediately functional and
reachable at `<minikube-ip>:30800`. In EKS, change `type: NodePort` to `type: LoadBalancer`
or deploy an Ingress controller.

#### Why SHA-pinned Image?

`:latest` is a mutable tag — the same string can point to a different image digest after
each push. SHA tags are immutable: `telco-churn-api:0595515` will always resolve to the
exact image that was built from that git commit. This guarantees reproducibility and makes
rollbacks trivial (`kubectl set image deployment/... image=...:previous-sha`).

---

### Error Reference

| Symptom | Cause | Fix |
|---|---|---|
| `ImagePullBackOff` | ECR auth missing / token expired | Option A: `minikube image load`; Option B: recreate `ecr-credentials` secret |
| Pod stuck in `Init:0/1` or CrashLoopBackOff | PVC empty — model artifacts not copied | Run Step 3 (copy models to PVC) |
| `0/1` Ready, restarts > 0 | Readiness probe failing; MLflow can't open `mlflow.db` | Check `kubectl logs` for model load errors; verify mlflow PVC mount |
| `kubectl apply` fails with `unknown field` | API version mismatch | Verify K8s cluster version: `kubectl version` |
| HPA shows `<unknown>/70%` CPU | metrics-server not running | `minikube addons enable metrics-server` |
| `Error from server: secrets "telco-churn-secret" not found` | Real secret not created | Run Step 2 (`kubectl create secret`) |

---

## Phase 16 — Grafana Monitoring Dashboard

### Overview

Phase 16 deploys a dedicated **Grafana** instance in the local Minikube cluster. It automatically provisions:
1. **Prometheus Datasource**: Points to `http://prometheus:9090` (in-cluster Prometheus service).
2. **Telco Churn Production Telemetry Dashboard**: Complete visual dashboard with real-time graphs and telemetry for the API.

### Access & Credentials

- **Access URL**: `http://<minikube-ip>:30091` or run `minikube service grafana --url`
- **Default Credentials**:
  - Username: `admin`
  - Password: `admin`
  > **SECURITY NOTICE**: `admin`/`admin` credentials are configured strictly for local Minikube development and must never be used in a production environment.

### Auto-Provisioned Panels

| Panel | Type | Metric / Expression | Description |
|---|---|---|---|
| **API Service Health** | Stat | `up{app="telco-churn-api"}` | Instant cluster health status (`UP` / `DOWN`) |
| **Active Model Version** | Stat | `telco_model_info` | Model version currently loaded and serving inference |
| **Total Predictions** | Stat | `sum(telco_predictions_total) by (decision)` | Real-time prediction counter broken down by `Churn` vs `No Churn` |
| **Data & Concept Drift Score** | Text | *Static Notice* | Placeholder explicitly marked **"Coming in Phase 17"** |
| **Request Latency Percentiles** | Time Series | `histogram_quantile(0.50, ...)` / `(0.95, ...)` | p50 and p95 latency percentiles over time |
| **Prediction Traffic Rate** | Time Series | `sum(rate(telco_predictions_total[1m])) by (decision)` | Requests per second by decision |
| **Process CPU Usage Rate** | Time Series | `rate(process_cpu_seconds_total[1m])` | Real CPU core usage rate of the API process |
| **Process Memory Usage** | Time Series | `process_resident_memory_bytes` / `process_virtual_memory_bytes` | RSS and VMS memory consumption |
