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
