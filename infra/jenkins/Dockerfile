# ==============================================================================
# Phase 14 — Custom Jenkins Agent/Server Dockerfile
#
# Extends jenkins/jenkins:lts with all CLI tools required for the Telco Churn
# CI/CD pipeline:
#   - Python 3 + pip + venv (for lint, test, data validation, train, evaluate, promote)
#   - Docker CLI (official binary for container packaging via /var/run/docker.sock)
#   - AWS CLI v2 (for AWS ECR login & authentication)
#   - kubectl (for deploying manifests to Minikube / Kubernetes)
#
# SECURITY:
#   - User 'jenkins' is strictly non-root (uid=1000, gid=1000)
#   - Docker socket access via standard 'docker' group membership ONLY
#   - NO sudoers entry, NO root group membership
# ==============================================================================

FROM jenkins/jenkins:lts

USER root

# Install Debian packages: Python 3, pip, venv, curl, git, unzip, ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-full \
    curl \
    git \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install official stable kubectl binary
RUN curl -fsSL -o /usr/local/bin/kubectl "https://dl.k8s.io/release/v1.32.2/bin/linux/amd64/kubectl" \
    && chmod +x /usr/local/bin/kubectl

# Install official AWS CLI v2
RUN curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip -q awscliv2.zip \
    && ./aws/install \
    && rm -rf awscliv2.zip aws

# Install official static Docker CLI binary & compose plugin
RUN curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-27.5.1.tgz" | tar -xz -C /tmp \
    && cp /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker \
    && chmod +x /usr/local/bin/docker \
    && mkdir -p /usr/local/lib/docker/cli-plugins \
    && curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-compose "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-x86_64" \
    && chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Configure standard docker group and add jenkins user (NO sudo / NO root group)
RUN groupadd -g 999 docker 2>/dev/null || groupadd docker 2>/dev/null || true \
    && usermod -aG docker jenkins

USER jenkins
