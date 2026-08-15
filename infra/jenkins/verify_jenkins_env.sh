#!/usr/bin/env bash
set -e

echo "================================================================="
echo "  PHASE 14 — JENKINS AGENT TOOLING INVENTORY & CONNECTIVITY CHECK"
echo "================================================================="
echo "Current User: $(whoami) (uid=$(id -u), gid=$(id -g))"
echo "Home Directory: $HOME"
echo ""

echo "--- 1. CLI Tooling Inventory ---"
echo -n "Python version:  "; python3 --version
echo -n "Pip version:     "; pip --version
echo -n "Docker version:  "; docker --version
echo -n "AWS CLI version: "; aws --version
echo -n "kubectl version: "; kubectl version --client --output=yaml | grep gitVersion | head -n 1
echo ""

echo "--- 2. Docker Daemon Socket Access ---"
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
echo ""

echo "--- 3. Minikube API Server Connectivity & kubectl Authentication ---"
kubectl cluster-info
echo ""

echo "--- 4. Minikube Node & Workload Inspection ---"
kubectl get nodes -o wide
echo ""
kubectl get pods -l app=telco-churn-api -o wide
echo ""
kubectl get svc telco-churn-api
echo ""
kubectl get pvc
echo ""

echo "--- 5. Service & In-Cluster Endpoint Probe from Jenkins Container ---"
MINIKUBE_IP=$(kubectl get node minikube -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')
echo "Minikube Node IP: $MINIKUBE_IP"
echo "Probing http://${MINIKUBE_IP}:30800/health/readiness from inside Jenkins container..."
curl -s "http://${MINIKUBE_IP}:30800/health/readiness"
echo ""
echo ""

echo "--- 6. Smoke Test Predict Probe from Jenkins Container ---"
curl -s -X POST "http://${MINIKUBE_IP}:30800/predict" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-secret-key-12345" \
  -d '{"customerID":"jenkins-smoke-001","gender":"Male","SeniorCitizen":0,"Partner":"Yes","Dependents":"No","tenure":12,"PhoneService":"Yes","MultipleLines":"No","InternetService":"Fiber optic","OnlineSecurity":"No","OnlineBackup":"No","DeviceProtection":"No","TechSupport":"No","StreamingTV":"No","StreamingMovies":"No","Contract":"Month-to-month","PaperlessBilling":"Yes","PaymentMethod":"Electronic check","MonthlyCharges":70.35,"TotalCharges":"845.5"}'
echo ""
echo ""
echo "================================================================="
echo "  ALL CHECKS PASSED: Tooling and Minikube Connectivity Verified!"
echo "================================================================="
