pipeline {
    agent any

    parameters {
        string(name: 'FORCE_DEGRADED_CANDIDATE', defaultValue: '0', description: 'Force degraded model for promotion rejection testing')
    }

    environment {
        AWS_REGION               = 'ap-south-1'
        ECR_ACCOUNT_ID           = '899640267680'
        ECR_REPO_NAME            = 'telco-churn-api'
        ECR_REGISTRY_URI         = "${ECR_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
        IMAGE_URI                = "${ECR_REGISTRY_URI}/${ECR_REPO_NAME}"
        KUBECONFIG               = '/var/jenkins_home/.kube/config'
        API_KEY                  = 'dev-secret-key-123'
        FORCE_DEGRADED_CANDIDATE = "${params.FORCE_DEGRADED_CANDIDATE ?: '0'}"
    }

    stages {
        stage('Checkout') {
            steps {
                echo '=== Stage 1: Checkout Source Code ==='
                checkout scm
                sh '''
                    chmod -R u+rw . || true
                '''
                script {
                    env.GIT_COMMIT_SHORT = sh(
                        script: 'git rev-parse --short HEAD',
                        returnStdout: true
                    ).trim()
                    echo "Current Git Commit SHA (short): ${env.GIT_COMMIT_SHORT}"
                }
            }
        }

        stage('Install Dependencies') {
            steps {
                echo '=== Stage 2: Install Python Virtual Environment & Dependencies ==='
                sh '''
                    if [ ! -f .venv/bin/activate ]; then
                        python3 -m venv .venv
                    fi
                    . .venv/bin/activate
                    pip install -e ".[dev,test]"
                '''
            }
        }

        stage('Lint & Format Checks') {
            steps {
                echo '=== Stage 3: Run Code Quality, Style & Type Checks ==='
                sh '''
                    . .venv/bin/activate
                    python3 tasks.py lint
                '''
            }
        }

        stage('Unit Tests') {
            steps {
                echo '=== Stage 4: Run Unit Test Suite ==='
                sh '''
                    . .venv/bin/activate
                    python3 tasks.py test
                '''
            }
        }

        stage('Integration Test') {
            steps {
                echo '=== Stage 4.5: Run End-to-End Integration Suite in Isolated Environment ==='
                sh '''
                    . .venv/bin/activate
                    python3 tasks.py integration-test
                '''
            }
        }

        stage('Data Validation') {
            steps {
                echo '=== Stage 5: Validate Raw Dataset Schema & Integrity ==='
                sh '''
                    . .venv/bin/activate
                    python3 tasks.py ingest
                    python3 tasks.py validate
                '''
            }
        }

        stage('Feature Engineering & Train') {
            steps {
                echo '=== Stage 6: Execute Feature Pipeline & Model Training ==='
                sh '''
                    . .venv/bin/activate
                    python3 tasks.py features
                    python3 tasks.py train
                '''
            }
        }

        stage('Evaluate') {
            steps {
                echo '=== Stage 7: Evaluate Model & Compute Optimal Threshold ==='
                sh '''
                    . .venv/bin/activate
                    python3 tasks.py evaluate
                '''
            }
        }

        stage('Promote') {
            steps {
                echo '=== Stage 8: MLflow Registry Model Promotion ==='
                sh '''
                    . .venv/bin/activate
                    python3 tasks.py promote
                '''
            }
        }

        stage('Docker Build') {
            steps {
                echo '=== Stage 9: Build Docker Container Image ==='
                sh """
                    docker build \
                        -t telco-churn-api:${env.GIT_COMMIT_SHORT} \
                        -t telco-churn-api:latest \
                        --build-arg BUILD_DATE=\$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
                        --build-arg GIT_COMMIT=${env.GIT_COMMIT_SHORT} \
                        --build-arg VERSION=1.0.0 \
                        .
                """
            }
        }

        stage('Push to ECR') {
            steps {
                echo '=== Stage 10: Authenticate, Tag & Push Image to AWS ECR ==='
                sh """
                    echo "--> Authenticating Docker CLI with AWS ECR in \${AWS_REGION}..."
                    aws ecr get-login-password --region \${AWS_REGION} | \
                        docker login --username AWS --password-stdin \${ECR_REGISTRY_URI}

                    echo "--> Tagging container images..."
                    docker tag telco-churn-api:${env.GIT_COMMIT_SHORT} \${IMAGE_URI}:${env.GIT_COMMIT_SHORT}
                    docker tag telco-churn-api:latest \${IMAGE_URI}:latest

                    echo "--> Pushing immutable SHA tag \${IMAGE_URI}:${env.GIT_COMMIT_SHORT}..."
                    docker push \${IMAGE_URI}:${env.GIT_COMMIT_SHORT}

                    echo "--> Pushing latest tag \${IMAGE_URI}:latest..."
                    docker push \${IMAGE_URI}:latest

                    echo "--> Verifying pushed manifest digest (RepoDigests vs ECR imageDigest)..."
                    LOCAL_REPO_DIGEST=\$(docker image inspect \${IMAGE_URI}:${env.GIT_COMMIT_SHORT} --format='{{index .RepoDigests 0}}' | awk -F'@' '{print \$2}')
                    ECR_DIGEST=\$(aws ecr describe-images --repository-name \${ECR_REPO_NAME} --image-ids imageTag=${env.GIT_COMMIT_SHORT} --region \${AWS_REGION} --query "imageDetails[0].imageDigest" --output text)

                    echo "Local RepoDigest: \${LOCAL_REPO_DIGEST}"
                    echo "ECR ImageDigest:  \${ECR_DIGEST}"

                    if [ "\${LOCAL_REPO_DIGEST}" != "\${ECR_DIGEST}" ]; then
                        echo "ERROR: Digest mismatch between pushed manifest and ECR registry!"
                        exit 1
                    fi
                    echo "SUCCESS: Image digest verified against ECR registry."
                """
            }
        }

        stage('Deploy to Kubernetes') {
            steps {
                echo '=== Stage 11: Deploy Manifests to Minikube (Excluding secret.yaml) ==='
                sh """
                    echo "--> Syncing image to Minikube local container cache..."
                    if docker ps --format '{{.Names}}' | grep -q '^minikube\$'; then
                        docker save \${IMAGE_URI}:\${GIT_COMMIT_SHORT} | docker exec -i minikube docker load || true
                    fi

                    echo "--> Applying non-secret Kubernetes manifests..."
                    # NOTE (Phase 13 hardening): Explicitly apply individual manifests to avoid overwriting live secret
                    kubectl apply -f infra/k8s/configmap.yaml
                    kubectl apply -f infra/k8s/pvc-models.yaml
                    kubectl apply -f infra/k8s/pvc-mlflow.yaml
                    kubectl apply -f infra/k8s/deployment.yaml
                    kubectl apply -f infra/k8s/service.yaml
                    kubectl apply -f infra/k8s/hpa.yaml
                    kubectl apply -f infra/k8s/pdb.yaml
                    kubectl apply -f infra/k8s/prometheus-configmap.yaml
                    kubectl apply -f infra/k8s/prometheus-deployment.yaml
                    kubectl apply -f infra/k8s/prometheus-service.yaml

                    echo "--> Updating deployment image to immutable tag \${IMAGE_URI}:\${GIT_COMMIT_SHORT}..."
                    kubectl set image deployment/telco-churn-api telco-churn-api=\${IMAGE_URI}:\${GIT_COMMIT_SHORT}

                    echo "--> Waiting for rollout completion..."
                    kubectl rollout status deployment/telco-churn-api --timeout=180s
                    kubectl rollout status deployment/prometheus --timeout=180s
                """
            }
        }

        stage('Smoke Test') {
            steps {
                echo '=== Stage 12: In-Cluster Health & Prediction Smoke Test ==='
                sh """
                    MINIKUBE_IP=\$(kubectl get node minikube -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')
                    TARGET_URL="http://\${MINIKUBE_IP}:30800"
                    echo "Probing service via NodePort on \${TARGET_URL}..."

                    echo "--> 1. Testing /health/readiness probe..."
                    HEALTH_RESP=\$(curl -fsS "\${TARGET_URL}/health/readiness")
                    echo "Health Response: \${HEALTH_RESP}"
                    echo "\${HEALTH_RESP}" | grep -q '"status":"ready"' || { echo "Health check failed"; exit 1; }

                    echo "--> 2. Testing /predict inference endpoint with authenticated sample..."
                    PAYLOAD='{"customerID":"ci-smoke-001","gender":"Male","SeniorCitizen":0,"Partner":"Yes","Dependents":"No","tenure":12,"PhoneService":"Yes","MultipleLines":"No","InternetService":"Fiber optic","OnlineSecurity":"No","OnlineBackup":"No","DeviceProtection":"No","TechSupport":"No","StreamingTV":"No","StreamingMovies":"No","Contract":"Month-to-month","PaperlessBilling":"Yes","PaymentMethod":"Electronic check","MonthlyCharges":70.35,"TotalCharges":"845.5"}'
                    PREDICT_RESP=\$(curl -fsS -X POST "\${TARGET_URL}/predict" \
                        -H "Content-Type: application/json" \
                        -H "X-API-Key: \${API_KEY}" \
                        -d "\${PAYLOAD}")
                    echo "Prediction Response: \${PREDICT_RESP}"
                    echo "\${PREDICT_RESP}" | grep -q '"churn_predicted"' || { echo "Predict test failed"; exit 1; }
                    echo "SUCCESS: Smoke test passed cleanly."
                """
            }
        }
    }

    post {
        success {
            echo "============================================================"
            echo "  CI/CD PIPELINE SUCCEEDED: Build #${env.BUILD_NUMBER} (${env.GIT_COMMIT_SHORT})"
            echo "============================================================"
        }
        failure {
            echo "============================================================"
            echo "  CI/CD PIPELINE FAILED: Build #${env.BUILD_NUMBER}"
            echo "============================================================"
        }
    }
}
