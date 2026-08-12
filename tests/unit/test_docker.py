"""Unit tests for Docker containerization configuration, compose, and tasks."""

from tasks import PROJECT_ROOT, task_docker_build, task_docker_run


def test_dockerfile_structure_and_best_practices() -> None:
    """Test Dockerfile exists and contains required production directives."""
    dockerfile_path = PROJECT_ROOT / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist at project root."

    content = dockerfile_path.read_text(encoding="utf-8")

    # Multi-stage build check
    assert "FROM python:3.12.3-slim-bookworm AS builder" in content
    assert "FROM python:3.12.3-slim-bookworm AS runner" in content

    # OCI Metadata labels check
    assert "org.opencontainers.image.title=" in content
    assert "org.opencontainers.image.description=" in content

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


def test_docker_compose_bind_mounts() -> None:
    """Test docker-compose.yml configures host bind mounts for ML artifacts."""
    compose_path = PROJECT_ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist at project root."

    content = compose_path.read_text(encoding="utf-8")
    assert "./models:/app/models:ro" in content
    assert "./mlruns:/app/mlruns:ro" in content
    assert "./mlflow.db:/app/mlflow.db:rw" in content
    assert "healthcheck:" in content
    assert "http://localhost:8000/health/readiness" in content


def test_docker_task_functions_registered() -> None:
    """Test CLI task runner functions for docker-build and docker-run exist."""
    assert callable(task_docker_build)
    assert callable(task_docker_run)
