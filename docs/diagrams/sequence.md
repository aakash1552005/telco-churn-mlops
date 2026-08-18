# Closed-Loop Retraining & Redeployment Sequence Diagram

This document contains the sequence diagram modeling the real closed-loop feedback mechanism of the **Telco Customer Churn MLOps Platform**, spanning inference telemetry, drift detection windowing, Jenkins retraining triggers, Section 9 promotion policy gating, and Kubernetes rolling deployment.

---

## Retraining & Deployment Lifecycle Sequence (Mermaid Source)

```mermaid
sequenceDiagram
    autonumber
    actor Client as API Consumer
    participant API as FastAPI Prediction Service
    participant Prom as Prometheus Metrics
    participant Drift as Evidently Drift Monitor
    participant Jenkins as Jenkins Automation Server
    participant Pipeline as ML Retraining Pipeline
    participant MLflow as MLflow Model Registry
    participant Docker as Docker Engine
    participant ECR as AWS ECR Registry
    participant K8s as Minikube / Kubernetes

    %% 1. Online Inference Phase
    Note over Client,API: 1. Live Inference & Telemetry Collection
    Client->>API: POST /predict (Payload + X-API-Key)
    API->>API: Validate schema & execute feature transformation
    API->>API: Score with Production model & apply optimal threshold
    API-->>Client: 200 OK (churn_probability, decision, model_version)
    API->>Prom: Update telco_predictions_total, latency histogram, metrics

    %% 2. Observability & Drift Monitoring Phase
    Note over Prom,Drift: 2. Drift Detection & Windowing
    Prom->>Drift: Scrape prediction & feature distributions
    Drift->>Drift: Compare Current Window against Reference Dataset
    alt Drift Detected in Single Window
        Drift->>Drift: Increment consecutive_drift_windows count (1 or 2)
        Drift->>Prom: Update telco_drift_detected gauge = 1
        Note over Drift: Threshold not yet reached (Requires 3 consecutive windows)
    else 3 Consecutive Drift Windows Breached
        Drift->>Drift: consecutive_drift_windows == 3 (Persistent Drift Confirmed)
        Drift->>Prom: Update telco_consecutive_drift_count = 3
        Drift->>Jenkins: POST /job/telco-churn-retrain/buildWithParameters (Trigger Pipeline)
    end

    %% 3. Automated Retraining Phase
    Note over Jenkins,MLflow: 3. Execution of Retraining Pipeline
    Jenkins->>Pipeline: Execute Ingestion, Validation & Feature Engineering
    Jenkins->>Pipeline: Train candidate models (5-Fold Stratified CV)
    Pipeline->>MLflow: Log candidate metrics, parameters, and artifacts
    Jenkins->>Pipeline: Evaluate candidate on held-out test set & optimize threshold
    Pipeline->>MLflow: Log evaluation metrics (ROC-AUC, optimal-threshold F1)

    %% 4. Section 9 Promotion Policy Gate
    Note over Pipeline,MLflow: 4. Master Contract Section 9 Promotion Gate
    Pipeline->>Pipeline: Compare Candidate against Incumbent Production Model:
    Note right of Pipeline: Criteria:<br/>1. F1 improvement >= +0.0100<br/>2. Precision drop <= 0.0200<br/>3. Recall drop <= 0.0000

    alt REJECT: Candidate Fails Promotion Criteria
        Pipeline->>MLflow: Tag Candidate Run: "Rejected by Section 9 Policy"
        Pipeline-->>Jenkins: Stage FAILED / UNCHANGED (Incumbent Retained)
        Jenkins->>Jenkins: Terminate pipeline (Zero deployment actions taken)
        Note over K8s,API: Incumbent Production model remains live and untouched.
    else ACCEPT: Candidate Passes Promotion Criteria
        Pipeline->>MLflow: Transition Candidate to "Production" stage
        Pipeline->>MLflow: Archive previous Production model version
        Pipeline-->>Jenkins: Promotion SUCCESS (New Production Model Approved)

        %% 5. Build, Push & Rolling Deployment
        Note over Jenkins,K8s: 5. Containerization & Rolling Update
        Jenkins->>Docker: Build multi-stage Docker image & tag with git-SHA
        Jenkins->>ECR: Push image to AWS ECR (latest + git-SHA)
        Jenkins->>K8s: minikube image load / update image tag in deployment.yaml
        Jenkins->>K8s: kubectl apply -f infra/k8s/deployment.yaml
        K8s->>K8s: Execute zero-downtime rolling update (1/1 Ready)
        K8s->>API: Pod Startup -> Mount PVC -> Load new Production model version
        API->>API: Health checks passing (/health/readiness)
        API->>Prom: Reset drift counters & report new model version
        Note over Client,API: New Production model actively serving predictions.
    end
```

---

## Key Sequence Decision Points

1. **Windowed Drift Dampening**: Prevents thrashing by requiring **3 consecutive drifted windows** before initiating heavy compute retraining.
2. **Deterministic Promotion Gate**: The candidate model MUST strictly demonstrate:
   - $\Delta \text{F1} \ge +0.0100$
   - $\Delta \text{Precision} \ge -0.0200$
   - $\Delta \text{Recall} \ge 0.0000$
3. **Safe Rejection Fallback**: If a retrained candidate fails the gate, the pipeline exits safely without mutating the live Kubernetes cluster or the incumbent Production model.
4. **Zero-Downtime Rolling Update**: Upon passing the gate, the image is pushed to ECR and rolled out on Kubernetes with liveness/readiness probes ensuring no dropped requests.
