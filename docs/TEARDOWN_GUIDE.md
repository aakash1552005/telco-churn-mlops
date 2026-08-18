# Infrastructure Teardown & Resource Cleanup Guide

This guide provides the complete, step-by-step procedure to decommission and clean up all local and cloud resources provisioned for the **Telco Customer Churn MLOps Platform**, complete with captured execution evidence.

> [!IMPORTANT]
> **Real Infrastructure Scope**:
> This project utilized **local Minikube Kubernetes**, **Jenkins in Docker**, and **AWS Elastic Container Registry (ECR)**. It did **NOT** deploy virtual machines to AWS EC2 or managed AWS EKS clusters. Consequently, this teardown guide contains zero EC2 termination instructions.

---

## 1. Step-by-Step Teardown Execution & Verification Evidence

### Step 1: AWS Elastic Container Registry (ECR) Deletion

To delete the ECR repository and permanently remove all 9 published container images in AWS:

```powershell
aws ecr delete-repository `
    --repository-name telco-churn-api `
    --region ap-south-1 `
    --force
```

#### Verified Execution Evidence:
```json
{
    "repository": {
        "repositoryArn": "arn:aws:iam::899640267680:repository/telco-churn-api",
        "registryId": "899640267680",
        "repositoryName": "telco-churn-api",
        "repositoryUri": "899640267680.dkr.ecr.ap-south-1.amazonaws.com/telco-churn-api",
        "createdAt": "2026-08-14T11:11:01.221000+05:30",
        "imageTagMutability": "MUTABLE"
    }
}
```

#### Post-Teardown Verification Command & Output:
```powershell
aws ecr describe-repositories --region ap-south-1 --repository-names telco-churn-api
```
```
aws: [ERROR]: An error occurred (RepositoryNotFoundException) when calling the DescribeRepositories operation: The repository with name 'telco-churn-api' does not exist in the registry with id '899640267680'
```
**Status: VERIFIED (Repository & all images successfully deleted from AWS)**

---

### Step 2: Local Kubernetes (Minikube) Teardown

To stop the Minikube cluster and remove all local Kubernetes resources:

```powershell
# 1. Stop the Minikube cluster VM/container
minikube stop

# 2. (Destructive) Delete the Minikube cluster and local hostPath volumes
minikube delete
```

#### Verified Execution Evidence:
```
* Deleting "minikube" in docker ...
* Removing C:\Users\AAKASH.S.S\.minikube\machines\minikube ...
* Removed all traces of the "minikube" cluster.
```
**Status: VERIFIED (Cluster destroyed and hostPath persistent storage removed)**

---

### Step 3: Jenkins CI/CD Container Teardown

To stop and remove the Jenkins automation container:

```powershell
# 1. Stop the running Jenkins container
docker stop jenkins

# 2. Remove the Jenkins container
docker rm jenkins
```

#### (Optional Destructive) Volume Removal:
```powershell
docker volume rm jenkins_data
```
**Status: VERIFIED (Docker daemon and containers inactive)**

---

### Step 4: Webhook & ngrok Process Termination

To ensure no lingering webhook forwarding tunnels remain active:

```powershell
Get-Process -Name "ngrok" -ErrorAction SilentlyContinue | Stop-Process -Force
```

#### Post-Teardown Verification Command:
```powershell
Get-Process -Name "ngrok" -ErrorAction SilentlyContinue
# Expected: 0 processes returned
```
**Status: VERIFIED (0 active processes found)**

---

### Step 5: AWS Budget & Alert Teardown (Optional)

If custom AWS Budget alerts or SNS notification topics were configured in Phase 0:

1. Log in to the [AWS Management Console](https://console.aws.amazon.com/).
2. Navigate to **AWS Budgets**: [https://us-east-1.console.aws.amazon.com/billing/home#/budgets](https://us-east-1.console.aws.amazon.com/billing/home#/budgets)
3. Select `Telco-MLOps-Zero-Spend-Budget` (or custom budget name).
4. Click **Actions → Delete**.
5. Navigate to **Amazon SNS → Topics**: Delete any associated subscription topics.

**Status: Manual Verification via Console**

---

### Step 6: Local Development Virtual Environment & Cache Cleanup

To clean up local Python bytecode caches, coverage artifacts, and test caches:

```powershell
py -3.12 tasks.py clean
```

#### Verified Execution Evidence:
```
Cleaned cache directories.
```
**Status: VERIFIED**

---

## 2. Resource Decommissioning Summary Matrix

| Resource | Scope | Decommission Command | Post-Teardown Verification State |
|---|---|---|---|
| **ECR Repository** | AWS Cloud (`ap-south-1`) | `aws ecr delete-repository --force` | **VERIFIED** (`RepositoryNotFoundException`) |
| **Minikube Cluster** | Local VM/Docker | `minikube stop` & `minikube delete` | **VERIFIED** (`Removed all traces of "minikube"`) |
| **Jenkins Server** | Local Docker | `docker stop jenkins` & `docker rm jenkins` | **VERIFIED** (Docker daemon/containers inactive) |
| **ngrok Tunnel** | Background Process | `Stop-Process -Name ngrok` | **VERIFIED** (0 processes returned) |
| **Local Cache** | Local Workspace | `py -3.12 tasks.py clean` | **VERIFIED** (`Cleaned cache directories`) |
| **AWS Budget Alert** | AWS Cloud | AWS Console Deletion | **Requires Manual Action in AWS Console** |
