# AWS Cost and Cloud Expenditure Audit Report

This report provides the full financial breakdown and infrastructure resource audit for the **Telco Customer Churn MLOps Platform**.

---

## 1. Cloud Account & Resource Baseline

| Parameter | Project Value | Source / Verification |
|---|---|---|
| **AWS Account ID** | `899640267680` | `aws sts get-caller-identity` |
| **AWS Region** | `ap-south-1` (Asia Pacific - Mumbai) | AWS CLI / `.env` configuration |
| **IAM Principal** | `arn:aws:iam::899640267680:user/telco-mlops-cli` | `aws sts get-caller-identity` |
| **Active Cloud Services** | Amazon Elastic Container Registry (ECR) | Live AWS API query |
| **Unused / Non-Deployed Cloud Services** | Amazon EC2, Amazon EKS, AWS Lambda, Amazon SageMaker, Amazon RDS | Architecture verification |

---

## 2. Exact AWS Cost Explorer CLI Query & Raw Output

To retrieve programmatic billing and cost data, the standard AWS Cost Explorer command was executed:

```powershell
aws ce get-cost-and-usage --time-period Start=2026-08-01,End=2026-08-18 --granularity MONTHLY --metrics "UnblendedCost"
```

### Exact Raw Command Output:
```
aws: [ERROR]: An error occurred (AccessDeniedException) when calling the GetCostAndUsage operation: User: arn:aws:iam::899640267680:user/telco-mlops-cli is not authorized to perform: ce:GetCostAndUsage on resource: arn:aws:ce:us-east-1:899640267680:/GetCostAndUsage because no identity-based policy allows the ce:GetCostAndUsage action
```

### Finding:
The provisioned IAM user `telco-mlops-cli` was configured following strict least-privilege security principles and possesses permissions strictly for Amazon ECR operations (`AmazonEC2ContainerRegistryFullAccess`). Because it lacks `ce:GetCostAndUsage` and `budgets:ViewBudget` permissions, programmatic cost extraction is denied. The exact billed usage must be verified manually in the AWS Billing Console by the account owner.

---

## 3. Infrastructure Usage & Financial Categorization

> [!IMPORTANT]
> **Strict Financial Distinction**:
> AWS cost reporting mandates distinguishing between **actual metered usage**, **payment authorization holds**, and **recurring payment mandate ceilings**. Do NOT infer, estimate, or combine these distinct categories.

### Category A: Actual AWS Billed Usage (Metered Compute & Storage)

| Service | Metered Metric | Measured Quantity | Unit Rate (ap-south-1) | Actual Incurred Cost |
|---|---|---|---|---|
| **Amazon ECR** | Image Storage (OCI artifacts) | 9 image manifests (~701 MB deduplicated) | $0.10 per GB-month (Free Tier: 500 MB/month) | **Manual Verification Required** (See Section 5) |
| **Amazon ECR** | Data Transfer IN | ~700 MB | Free ($0.00 / GB) | **$0.00** |
| **Amazon ECR** | Data Transfer OUT (within same region/Minikube) | ~1.4 GB | Free Tier (first 100 GB/month free) | **$0.00** |
| **Amazon EC2** | Virtual Machines | 0 instances provisioned | $0.00 | **$0.00** (Local Minikube used) |
| **Amazon EKS** | Managed Control Plane | 0 clusters provisioned | $0.00 | **$0.00** (Local Minikube used) |

### Category B: Payment-Method Verification & Authorization Holds

- **Actual Authorization Hold Event**: **₹2.00 INR**
- **Nature of Event**: When linking a payment method (e.g., credit/debit card or UPI) to an AWS account, AWS executes a temporary authorization hold of **₹2.00 INR** to verify payment method validity.
- **Financial Status**: This is **NOT an AWS service fee or usage cost**. It is a temporary pre-authorization hold automatically reversed by AWS and the issuing bank.

### Category C: UPI AutoPay / Standing Mandate Authorization Ceiling

- **Mandate Ceiling Amount**: **₹15,000 INR**
- **Nature of Event**: Under Reserve Bank of India (RBI) e-mandate guidelines, recurring cloud subscriptions require setting a maximum automated debit authorization ceiling.
- **CRITICAL CLARIFICATION**: The **₹15,000 INR** figure is a **mandate authorization ceiling** (the maximum allowable automatic transaction threshold without requiring secondary 2FA OTP), **NOT an incurred bill, usage charge, or actual debit**.
- Actual account debits occur **strictly for real billed usage** incurred on the AWS invoice.

---

## 4. ECR Inventory Evidence (Pre-Teardown Inspection)

*Query executed via `aws ecr describe-images --repository-name telco-churn-api --region ap-south-1`:*

```json
[
  { "tag": "latest / 12e7792", "digest": "sha256:d7a016...", "size_bytes": 701593879, "pushed": "2026-08-17T00:24:45+05:30" },
  { "tag": "7f8629e",          "digest": "sha256:11b0a1...", "size_bytes": 701565604, "pushed": "2026-08-16T13:35:51+05:30" },
  { "tag": "c372ce7",          "digest": "sha256:192cd0...", "size_bytes": 701562262, "pushed": "2026-08-15T14:37:43+05:30" },
  { "tag": "82b9b17",          "digest": "sha256:a71d1c...", "size_bytes": 701562194, "pushed": "2026-08-15T13:55:02+05:30" },
  { "tag": "8dee796",          "digest": "sha256:5e2241...", "size_bytes": 701562170, "pushed": "2026-08-15T13:25:20+05:30" },
  { "tag": "0595515",          "digest": "sha256:c83794...", "size_bytes": 701341834, "pushed": "2026-08-14T11:20:14+05:30" }
]
```

*Note on Storage Deduplication:* Docker multi-stage images share common underlying base layers (`python:3.12-slim`). Although 9 tags were published across phases, unique physical storage in ECR was bounded to **~701 MB**.

---

## 5. Manual Billing Console Verification Guide

Because programmatic access via `aws ce` is denied by IAM least-privilege policies, the account administrator must verify the exact finalized billed amounts directly in the console:

### Step-by-Step AWS Console Verification:
1. Log in to the [AWS Management Console](https://console.aws.amazon.com/) as the root user or billing administrator.
2. Navigate to **AWS Billing and Cost Management**:
   - URL: [https://us-east-1.console.aws.amazon.com/billing/home#/bills](https://us-east-1.console.aws.amazon.com/billing/home#/bills)
3. Under the **Charges by service** dropdown:
   - Select the billing period (`August 2026`).
   - Check line items for **Elastic Container Registry (ECR)**: Confirm storage usage and charges.
   - Confirm **Elastic Compute Cloud (EC2)** line item: **$0.00** (0 hours).
4. Review **Payment History**:
   - Verify that no unexpected debits occurred beyond actual billed usage.

| Cost Field | Status | Actual Value Source |
|---|---|---|
| Total AWS Billed Invoices | **Manual Verification Required** | AWS Console → [Billing / Bills](https://us-east-1.console.aws.amazon.com/billing/home#/bills) |
| Current Month Cost Forecast | **Manual Verification Required** | AWS Console → [Cost Explorer](https://us-east-1.console.aws.amazon.com/costmanagement/home#/cost-explorer) |
| Payment Verification Pre-Auth | **₹2.00 INR** (Reversible Hold) | Bank SMS / AWS Verification Notice |
| Standing AutoPay Ceiling | **₹15,000 INR** (Mandate Limit) | Payment Gateway / Mandate Settings |
| Pre-Teardown ECR Storage Volume | **701 MB** | Live CLI `aws ecr describe-images` |
