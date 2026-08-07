# ADR 0002: Configure pydantic.mypy Plugin for Type Checking BaseSettings

- **Status:** Accepted
- **Date:** 2026-08-07
- **Deciders:** MLOps Engineering Team

---

## Context
Pydantic's `BaseSettings` resolves required fields at runtime from environment variables and `.env` files rather than requiring explicit arguments at instantiation (`Settings()`). Without specialized type checker integration, static type analysis (`mypy`) flags `Settings()` instantiation as missing required arguments (`[call-arg]`).

Suppressing this error via inline `# type: ignore` comments masks potential type misconfigurations across the codebase.

## Decision
We configure the official Pydantic Mypy plugin (`pydantic.mypy`) in [`pyproject.toml`](file:///C:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/pyproject.toml) under `[tool.mypy] plugins = ["pydantic.mypy"]`.

The plugin understands Pydantic model initialization and dynamic environment resolution for `BaseSettings` subclasses, allowing `Settings()` to type-check natively without any `# type: ignore` suppressions.

## Alternatives Considered
1. **Inline `# type: ignore[call-arg]` suppressions:** Masks real type errors and violates Master Contract guidelines prohibiting unexplained type suppressions.
2. **Default dummy value for required fields:** Defeats fail-fast validation when required environment variables (e.g. `ENVIRONMENT`) are missing in production.
3. **Official `pydantic.mypy` Plugin (Chosen):** Solves the root cause natively through Pydantic's official static analysis extension.

## Consequences
- **Positive:** `Settings()` type-checks cleanly with zero inline ignores.
- **Positive:** Type safety and fail-fast environment validation are strictly preserved.
