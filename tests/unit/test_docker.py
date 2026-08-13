"""Unit tests for Docker containerization configuration, compose, and tasks."""

from tasks import PROJECT_ROOT, task_docker_build, task_docker_run


def test_dockerfile_structure_and_best_practices() -> None:
    """Test Dockerfile exists and contains required production directives."""
    dockerfile_path = PROJECT_ROOT / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist at project root."

    content = dockerfile_path.read_text(encoding="utf-8")

    # Multi-stage build & digest pinning check
    d_sub = "sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63"
    assert f"FROM python:3.12.3-slim-bookworm@{d_sub} AS builder" in content
    assert f"FROM python:3.12.3-slim-bookworm@{d_sub} AS runner" in content

    # OCI Metadata labels check
    assert "org.opencontainers.image.title=" in content
    assert "org.opencontainers.image.description=" in content
    assert "org.opencontainers.image.created" in content
    assert "org.opencontainers.image.revision" in content
    assert "org.opencontainers.image.version" in content

    # Non-root user check
    assert "useradd" in content or "appuser" in content
    assert "USER appuser" in content

    # Operational instructions
    assert "EXPOSE 8000" in content
    assert "HEALTHCHECK" in content
    assert "http://localhost:8000/health/readiness" in content
    assert "CMD" in content or "ENTRYPOINT" in content
    assert "uvicorn" in content

    # Bind mount preparation (models, mlruns, and mlflow.db NOT baked into image layer)
    assert "mkdir -p /app/models /app/mlruns /app/src" in content
    assert "COPY --chown=appuser:appgroup models/" not in content
    assert "COPY --chown=appuser:appgroup mlflow.db" not in content


def test_dockerignore_exclusions() -> None:
    """Test .dockerignore exists and excludes sensitive and build noise files."""
    dockerignore_path = PROJECT_ROOT / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore must exist at project root."

    content = dockerignore_path.read_text(encoding="utf-8")
    ignored_patterns = [line.strip() for line in content.splitlines() if line.strip()]

    assert ".git" in ignored_patterns
    assert ".venv/" in ignored_patterns
    assert "__pycache__/" in ignored_patterns
    assert ".env" in ignored_patterns
    assert "data/" in ignored_patterns
    assert "reports/" in ignored_patterns


def test_docker_compose_no_literal_secrets() -> None:
    """Test docker-compose.yml configures host mounts and no secret keys."""
    compose_path = PROJECT_ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist at project root."

    content = compose_path.read_text(encoding="utf-8")
    assert "./models:/app/models:ro" in content
    assert "./mlruns:/app/mlruns:ro" in content
    assert "./mlflow.db:/app/mlflow.db:rw" in content
    assert "healthcheck:" in content
    assert "http://localhost:8000/health/readiness" in content
    err1 = "docker-compose.yml must NOT contain hardcoded secret values."
    assert "API_KEY=dev-secret-key-123" not in content, err1
    err2 = "docker-compose.yml must use ${API_KEY} substitution."
    assert 'API_SECRET_KEYS=["${API_KEY' in content, err2


def test_docker_task_functions_registered() -> None:
    """Test CLI task runner functions for docker-build and docker-run exist."""
    assert callable(task_docker_build)
    assert callable(task_docker_run)
