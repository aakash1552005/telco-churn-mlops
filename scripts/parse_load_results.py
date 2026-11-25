"""Parse and aggregate headless Locust load testing CSV reports for three concurrency profiles.

Profiles evaluated:
1. Low concurrency (1 user)  - Measures per-request latency with no queueing
2. Low concurrency (5 users) - Measures queueing under low concurrency
3. High concurrency (25 users) - Measures queueing under saturated worker concurrency

Computes the median across 3 load test runs for P50, P95, RPS, and Error Rate for each profile.
Outputs a clean Markdown table to $GITHUB_STEP_SUMMARY and a structured JSON artifact.
Exits non-zero only if total requests == 0 or median error rate > 5.0% (validity check).
"""

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List


def parse_locust_stats(csv_path: Path) -> Dict[str, Any]:
    """Extract /predict metrics from Locust stats CSV file."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Locust stats CSV not found at '{csv_path}'")

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        predict_row = None
        aggregated_row = None
        for row in reader:
            if row.get("Name") == "/predict":
                predict_row = row
            if row.get("Name") == "Aggregated":
                aggregated_row = row

    target = predict_row or aggregated_row
    if not target:
        raise ValueError(f"Could not find '/predict' or 'Aggregated' row in '{csv_path}'")

    req_count = int(target.get("Request Count", 0))
    fail_count = int(target.get("Failure Count", 0))
    error_rate = (fail_count / req_count * 100.0) if req_count > 0 else 0.0

    # Percentiles: in Locust CSV, "50%" is median, "95%" is P95
    p50 = float(target.get("50%", target.get("Median Response Time", 0.0)))
    p95 = float(target.get("95%", 0.0))
    rps = float(target.get("Requests/s", 0.0))

    return {
        "requests": req_count,
        "failures": fail_count,
        "error_rate_pct": round(error_rate, 2),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "rps": round(rps, 2),
    }


def aggregate_profile_runs(run_paths: List[Path], profile_name: str, concurrency: int) -> Dict[str, Any]:
    """Aggregate 3 runs for a single load profile."""
    runs_data: List[Dict[str, Any]] = []
    for idx, path in enumerate(run_paths, start=1):
        parsed = parse_locust_stats(path)
        parsed["run_number"] = idx
        runs_data.append(parsed)

    median_p50 = round(statistics.median([r["p50_ms"] for r in runs_data]), 2)
    median_p95 = round(statistics.median([r["p95_ms"] for r in runs_data]), 2)
    median_rps = round(statistics.median([r["rps"] for r in runs_data]), 2)
    median_error_rate = round(statistics.median([r["error_rate_pct"] for r in runs_data]), 2)
    total_requests = sum(r["requests"] for r in runs_data)
    total_failures = sum(r["failures"] for r in runs_data)

    return {
        "profile_name": profile_name,
        "concurrency_users": concurrency,
        "warmup_seconds": 10,
        "run_duration_seconds": 30,
        "ramp_up_seconds": 5,
        "iterations": len(runs_data),
        "runs": runs_data,
        "median_benchmarks": {
            "median_p50_ms": median_p50,
            "median_p95_ms": median_p95,
            "median_rps": median_rps,
            "median_error_rate_pct": median_error_rate,
            "total_requests_served": total_requests,
            "total_failures": total_failures,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse Locust CSV test runs for 3 concurrency profiles and summarize.")
    # Profile 1: Low concurrency (1 user)
    parser.add_argument("--u1-run1", type=Path, required=True, help="Path to 1-user run1 stats CSV")
    parser.add_argument("--u1-run2", type=Path, required=True, help="Path to 1-user run2 stats CSV")
    parser.add_argument("--u1-run3", type=Path, required=True, help="Path to 1-user run3 stats CSV")
    # Profile 2: Low concurrency (5 users)
    parser.add_argument("--u5-run1", type=Path, required=True, help="Path to 5-user run1 stats CSV")
    parser.add_argument("--u5-run2", type=Path, required=True, help="Path to 5-user run2 stats CSV")
    parser.add_argument("--u5-run3", type=Path, required=True, help="Path to 5-user run3 stats CSV")
    # Profile 3: High concurrency (25 users)
    parser.add_argument("--u25-run1", type=Path, required=True, help="Path to 25-user run1 stats CSV")
    parser.add_argument("--u25-run2", type=Path, required=True, help="Path to 25-user run2 stats CSV")
    parser.add_argument("--u25-run3", type=Path, required=True, help="Path to 25-user run3 stats CSV")

    parser.add_argument("--runner-cpus", type=str, default="Unknown", help="vCPUs detected on runner")
    parser.add_argument("--runner-ram", type=str, default="Unknown", help="RAM detected on runner (MB)")
    parser.add_argument("--image-size", type=str, default="Unknown", help="Measured Docker image size")
    parser.add_argument("--output-json", type=Path, required=True, help="Destination JSON path")
    parser.add_argument("--step-summary", type=Path, default=None, help="Path to GITHUB_STEP_SUMMARY file")

    args = parser.parse_args()

    profile_1u = aggregate_profile_runs([args.u1_run1, args.u1_run2, args.u1_run3], "Low concurrency (1 user)", 1)
    profile_5u = aggregate_profile_runs([args.u5_run1, args.u5_run2, args.u5_run3], "Low concurrency (5 users)", 5)
    profile_25u = aggregate_profile_runs([args.u25_run1, args.u25_run2, args.u25_run3], "High concurrency (25 users)", 25)

    summary_payload = {
        "runner_environment": {
            "vcpus": args.runner_cpus,
            "ram_mb": args.runner_ram,
            "docker_image_size": args.image_size,
            "architecture_note": "Client (Locust) and server (FastAPI container) co-located on runner sharing CPU and memory",
        },
        "profiles": {
            "low_concurrency_1u": profile_1u,
            "low_concurrency_5u": profile_5u,
            "high_concurrency_25u": profile_25u,
        },
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    m1 = profile_1u["median_benchmarks"]
    m5 = profile_5u["median_benchmarks"]
    m25 = profile_25u["median_benchmarks"]

    # Generate Markdown Summary with all three profiles
    md_content = f"""## 🚀 Container & Load Benchmarks (Measured in CI)

### 🖥️ Runner Specifications & Container Footprint
- **Runner Environment**: GitHub-hosted Ubuntu (`{args.runner_cpus}` vCPUs, `{args.runner_ram} MB` RAM)
- **Container Footprint**: `{args.image_size}` (local uncompressed size, measured via `docker images`)
- **Execution Topology**: Co-located on runner (**Client and server share runner CPU & memory**)
- **Target Endpoint**: `POST /predict` (with runtime `X-API-Key` authentication)

### ⏱️ Load Test Profiles
- **Protocol**: 10s warm-up, 3 x 30s runs per profile (each run includes ~5s ramp-up), 0s think time.
- **Reporting**: Medians are calculated over per-run percentiles across the 3 runs for each profile.

### 📊 Benchmark Results

| Load Profile | Concurrency | P50 Latency (Median) | P95 Latency | Throughput (Requests/s) | Error Rate | Total Requests |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Low concurrency (1 user)** | 1 user | **`{m1['median_p50_ms']} ms`** | **`{m1['median_p95_ms']} ms`** | **`{m1['median_rps']} req/s`** | **`{m1['median_error_rate_pct']}%`** | `{m1['total_requests_served']}` |
| **Low concurrency (5 users)** | 5 users | **`{m5['median_p50_ms']} ms`** | **`{m5['median_p95_ms']} ms`** | **`{m5['median_rps']} req/s`** | **`{m5['median_error_rate_pct']}%`** | `{m5['total_requests_served']}` |
| **High concurrency (25 users)** | 25 users | **`{m25['median_p50_ms']} ms`** | **`{m25['median_p95_ms']} ms`** | **`{m25['median_rps']} req/s`** | **`{m25['median_error_rate_pct']}%`** | `{m25['total_requests_served']}` |

#### Detailed Per-Run Iterations

**Profile 1: Low concurrency (1 user)**
| Run | Requests | P50 Latency | P95 Latency | Throughput | Error Rate |
| :---: | :---: | :---: | :---: | :---: | :---: |
| Run 1 | `{profile_1u['runs'][0]['requests']}` | `{profile_1u['runs'][0]['p50_ms']} ms` | `{profile_1u['runs'][0]['p95_ms']} ms` | `{profile_1u['runs'][0]['rps']} req/s` | `{profile_1u['runs'][0]['error_rate_pct']}%` |
| Run 2 | `{profile_1u['runs'][1]['requests']}` | `{profile_1u['runs'][1]['p50_ms']} ms` | `{profile_1u['runs'][1]['p95_ms']} ms` | `{profile_1u['runs'][1]['rps']} req/s` | `{profile_1u['runs'][1]['error_rate_pct']}%` |
| Run 3 | `{profile_1u['runs'][2]['requests']}` | `{profile_1u['runs'][2]['p50_ms']} ms` | `{profile_1u['runs'][2]['p95_ms']} ms` | `{profile_1u['runs'][2]['rps']} req/s` | `{profile_1u['runs'][2]['error_rate_pct']}%` |
| **Median** | `{m1['total_requests_served']} (Total)` | **`{m1['median_p50_ms']} ms`** | **`{m1['median_p95_ms']} ms`** | **`{m1['median_rps']} req/s`** | **`{m1['median_error_rate_pct']}%`** |

**Profile 2: Low concurrency (5 users)**
| Run | Requests | P50 Latency | P95 Latency | Throughput | Error Rate |
| :---: | :---: | :---: | :---: | :---: | :---: |
| Run 1 | `{profile_5u['runs'][0]['requests']}` | `{profile_5u['runs'][0]['p50_ms']} ms` | `{profile_5u['runs'][0]['p95_ms']} ms` | `{profile_5u['runs'][0]['rps']} req/s` | `{profile_5u['runs'][0]['error_rate_pct']}%` |
| Run 2 | `{profile_5u['runs'][1]['requests']}` | `{profile_5u['runs'][1]['p50_ms']} ms` | `{profile_5u['runs'][1]['p95_ms']} ms` | `{profile_5u['runs'][1]['rps']} req/s` | `{profile_5u['runs'][1]['error_rate_pct']}%` |
| Run 3 | `{profile_5u['runs'][2]['requests']}` | `{profile_5u['runs'][2]['p50_ms']} ms` | `{profile_5u['runs'][2]['p95_ms']} ms` | `{profile_5u['runs'][2]['rps']} req/s` | `{profile_5u['runs'][2]['error_rate_pct']}%` |
| **Median** | `{m5['total_requests_served']} (Total)` | **`{m5['median_p50_ms']} ms`** | **`{m5['median_p95_ms']} ms`** | **`{m5['median_rps']} req/s`** | **`{m5['median_error_rate_pct']}%`** |

**Profile 3: High concurrency (25 users)**
| Run | Requests | P50 Latency | P95 Latency | Throughput | Error Rate |
| :---: | :---: | :---: | :---: | :---: | :---: |
| Run 1 | `{profile_25u['runs'][0]['requests']}` | `{profile_25u['runs'][0]['p50_ms']} ms` | `{profile_25u['runs'][0]['p95_ms']} ms` | `{profile_25u['runs'][0]['rps']} req/s` | `{profile_25u['runs'][0]['error_rate_pct']}%` |
| Run 2 | `{profile_25u['runs'][1]['requests']}` | `{profile_25u['runs'][1]['p50_ms']} ms` | `{profile_25u['runs'][1]['p95_ms']} ms` | `{profile_25u['runs'][1]['rps']} req/s` | `{profile_25u['runs'][1]['error_rate_pct']}%` |
| Run 3 | `{profile_25u['runs'][2]['requests']}` | `{profile_25u['runs'][2]['p50_ms']} ms` | `{profile_25u['runs'][2]['p95_ms']} ms` | `{profile_25u['runs'][2]['rps']} req/s` | `{profile_25u['runs'][2]['error_rate_pct']}%` |
| **Median** | `{m25['total_requests_served']} (Total)` | **`{m25['median_p50_ms']} ms`** | **`{m25['median_p95_ms']} ms`** | **`{m25['median_rps']} req/s`** | **`{m25['median_error_rate_pct']}%`** |

> **Note on Queueing & Runner Variance**:
> 1. With 0s think time, every concurrent profile saturates the single-worker process. Response latency is dominated by queueing (latency ~= users * service time). The 1-user profile measures per-request latency with no queueing, whereas the 25-user P50/P95 latency mostly reflects queue waiting time in the threadpool.
> 2. Throughput on shared GitHub Actions runners varies between runs due to host virtualization noisy neighbours (e.g. the identical 25-user profile measured 108 req/s in an earlier run and 64 req/s in a subsequent run on identical code). Performance optimizations must therefore be evaluated comparatively within a single job execution.
"""

    print(md_content)

    if args.step_summary and args.step_summary.parent.exists():
        with open(args.step_summary, "a", encoding="utf-8") as f:
            f.write(md_content + "\n")

    # Validity checks: fail only if benchmark run was invalid
    total_reqs = m1["total_requests_served"] + m5["total_requests_served"] + m25["total_requests_served"]
    max_error = max(m1["median_error_rate_pct"], m5["median_error_rate_pct"], m25["median_error_rate_pct"])

    if total_reqs == 0:
        print("ERROR: Total requests served across all benchmark runs is 0. Load test failed.", file=sys.stderr)
        sys.exit(1)

    if max_error > 5.0:
        print(f"ERROR: Median error rate {max_error}% exceeds 5% validity threshold.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
