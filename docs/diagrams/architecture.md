# System Architecture Diagram

This document contains the complete, reproducible system architecture diagram for the **Telco Customer Churn MLOps Platform**.

---

## High-Level Architecture Overview

The system is organized into five tightly integrated subsystems:
1. **Developer / Continuous Integration**: Git push triggers Jenkins CI/CD automation.
2. **ML Lifecycle Pipeline**: Ingestion, validation, feature engineering, deterministic cross-validation training, threshold optimization, and promotion policy gating against local SQLite MLflow Model Registry.
3. **Container & Cloud Registry**: Multi-stage hardened Docker image pinned with git-SHA digests pushed to private AWS Elastic Container Registry (ECR).
4. **Kubernetes Runtime**: Local Minikube Kubernetes cluster running FastAPI prediction pods, PVC mounts, HPA autoscaling, and NodePort exposure.
5. **Observability & Closed-Loop Retraining**: Real-time Prometheus metrics scraping, Grafana dashboards, Evidently drift detection, and automated webhook triggers back to Jenkins.

---

## Architecture Diagram (Mermaid Source)

```mermaid
flowchart TD
    %% Subgraphs and Styling
    classDef dev fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef cicd fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    classDef ml fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px;
    classDef cloud fill:#e8f5e9,stroke:#388e3c,stroke-width:2px;
    classDef k8s fill:#ede7f6,stroke:#512da8,stroke-width:2px;
    classDef obs fill:#fce4ec,stroke:#c2185b,stroke-width:2px;

    subgraph DeveloperWorkspace ["1. Developer & Source Control"]
        DEV["Developer Workstation"] -->|git push| GITHUB["GitHub / Git Repository"]
        NGROK["ngrok Tunnel / Webhook"] -.->|Push Event| JENKINS
    end
    class DeveloperWorkspace dev;

    subgraph CI_CD_Engine ["2. Jenkins Automation Server (Docker)"]
        JENKINS["Jenkins CI/CD Pipeline\n(Docker Container: port 8080)"]
        LINT_TEST["Quality Gates:\nLint, Unit Tests, Integration Tests"]
        BUILD_IMG["Docker Multi-Stage Build\n& Git-SHA Tagging"]
        JENKINS --> LINT_TEST
    end
    class CI_CD_Engine cicd;

    subgraph ML_Pipeline ["3. Machine Learning Pipeline"]
        INGEST["Data Ingestion\n(Kaggle / Local Source)"]
        VALID["Data Validation\n(Schema & Type Checks)"]
        FEAT["Feature Engineering\n(Scikit-Learn Pipeline & DVC)"]
        TRAIN["Model Training\n(XGBoost / Logistic Regression CV)"]
        EVAL["Model Evaluation\n(Threshold Tuning & Calibration)"]
        PROMOTE{"Section 9\nPromotion Gate"}
        MLFLOW[("MLflow Model Registry\nsqlite:///mlflow.db\nStaging / Production")]

        LINT_TEST --> INGEST --> VALID --> FEAT --> TRAIN --> EVAL --> PROMOTE
        TRAIN -.-> MLFLOW
        EVAL -.-> MLFLOW
        PROMOTE -->|Promote to Production| MLFLOW
        PROMOTE -->|Accept| BUILD_IMG
        PROMOTE -.->|Reject: Keep Incumbent| MLFLOW
    end
    class ML_Pipeline ml;

    subgraph CloudRegistry ["4. Cloud Container Registry"]
        BUILD_IMG -->|aws ecr push| ECR[("AWS Elastic Container Registry\n(ECR: telco-churn-api)")]
    end
    class CloudRegistry cloud;

    subgraph KubernetesCluster ["5. Minikube Kubernetes Cluster"]
        ECR -->|minikube image load / pull| K8S_DEP["Kubernetes Deployment\n(telco-churn-api pods)"]
        PVC_MODELS[("PVC: telco-models-pvc\n(/app/models)")] --> K8S_DEP
        PVC_MLFLOW[("PVC: telco-mlflow-pvc\n(/app/mlruns & mlflow.db)")] --> K8S_DEP
        K8S_SVC["Kubernetes NodePort Service\n(Port 30800)"] --> K8S_DEP
        HPA["Horizontal Pod Autoscaler\n(CPU >= 70%)"] -.-> K8S_DEP
        API["FastAPI Prediction Service\n(/predict, /health, /metrics)"] --- K8S_DEP
    end
    class KubernetesCluster k8s;

    subgraph MonitoringObservability ["6. Observability & Drift Closed-Loop"]
        CLIENT["Client / Consumer App"] -->|POST /predict\nwith X-API-Key| API
        PROM["Prometheus Server\n(Port 9090 / 30090)"] -->|Scrape /metrics| API
        GRAFANA["Grafana Dashboard\n(Port 3000 / 30091)"] -->|Query Metrics| PROM

        DRIFT["Evidently Drift Monitor\n(Reference vs Current Window)"] -->|Read Predictions & Features| API
        DRIFT -->|Log Metrics| PROM
        DRIFT -->|3 Consecutive Drift Windows| RETRIGGER{"Drift Threshold\nBreached?"}
        RETRIGGER -->|POST /job/retrain/buildWithParameters| JENKINS
    end
    class MonitoringObservability obs;
```

---

## Subsystem Descriptions

| Subsystem | Components | Technology Stack | Key Responsibilities |
|---|---|---|---|
| **Source & Orchestration** | Git, ngrok, Jenkins | Git, Docker, Jenkins LTS | Version control, webhook routing, automated pipeline execution, build verification. |
| **ML Lifecycle** | Ingestion, Validation, Features, Training, Evaluation, Promotion | Pandas, Scikit-learn, XGBoost, DVC, MLflow (SQLite) | Deterministic training with 5-fold CV, optimal threshold tuning ($\approx 0.3254$), Section 9 promotion policy enforcement. |
| **Container & Cloud Registry** | Docker, AWS ECR | Docker BuildKit, AWS CLI, ECR | Multi-stage image build, non-root `appuser` execution, immutable git-SHA digest tagging, AWS ECR push. |
| **Cluster Runtime** | Minikube, Kubernetes manifests | Minikube, kubectl, Kubernetes v1.30+ | Local cluster deployment, PVC artifact mounting, rolling updates, HPA auto-scaling, NodePort routing. |
| **Inference Service** | FastAPI, Uvicorn, SlowAPI | FastAPI, Pydantic v2, Python 3.12 | REST prediction endpoints (`/predict`), health probes (`/health/liveness`, `/health/readiness`), API key auth, rate limiting. |
| **Observability & Closed Loop** | Prometheus, Grafana, Evidently | Prometheus, Grafana, Evidently AI | Telemetry scraping, visual performance dashboards, data drift monitoring, automated retraining trigger. |
