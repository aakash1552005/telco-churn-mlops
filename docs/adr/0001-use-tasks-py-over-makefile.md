# ADR 0001: Standardize Task Automation via tasks.py for Cross-Platform Portability

- **Status:** Accepted
- **Date:** 2026-08-07
- **Deciders:** MLOps Engineering Team

---

## Context
Phase 1 deliverable requires standard task targets (`install`, `lint`, `format`, `test`, `clean`). GNU `make` is standard on Linux/macOS environments, but Windows operating systems do not ship `make` by default. Developers or CI runners on Windows machines encounter missing executable errors (`CommandNotFoundException` for `make`).

## Decision
We adopt a pure Python task runner script ([`tasks.py`](file:///C:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/tasks.py)) utilizing Python's built-in `argparse` and `subprocess` standard library modules as the primary automation interface.

The [`Makefile`](file:///C:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/Makefile) is retained as a light wrapper delegating calls to `python tasks.py <target>`, ensuring backward compatibility for Unix users without requiring extra tool installation on Windows.

## Alternatives Considered
1. **Require GNU Make for Windows (e.g. via Chocolatey/winget/MSYS2):** Adds external installation friction and non-standard shell dependencies for developer onboarding.
2. **`pyinvoke` / `nox` / `tox`:** Requires pre-installing additional third-party dependencies before the initial `install` target can be run.
3. **`tasks.py` with standard library `argparse` (Chosen):** Requires zero pre-installed tools beyond Python 3.12+, works out-of-the-box on Windows, Linux, and macOS.

## Consequences
- **Positive:** Developers on Windows can run all operations via standard `python tasks.py <target>` without installing third-party tools.
- **Positive:** Multi-platform OS compatibility guaranteed in CI/CD and local environments.
- **Negative:** Slightly more verbose command invocation (`python tasks.py lint` vs `make lint`) when run directly without `make`.
