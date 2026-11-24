"""Parse and aggregate headless Locust load testing CSV reports.

Computes the median across 3 load test runs for P50, P95, RPS, and Error Rate.
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse Locust CSV test runs and summarize.")
    parser.add_argument("--run1", type=Path, required=True, help="Path to run1 stats CSV")
    parser.add_argument("--run2", type=Path, required=True, help="Path to run2 stats CSV")
    parser.add_argument("--run3", type=Path, required=True, help="Path to run3 stats CSV")
    parser.add_argument("--runner-cpus", type=str, default="Unknown", help="vCPUs detected on runner")
    parser.add_argument("--runner-ram", type=str, default="Unknown", help="RAM detected on runner (MB)")
    parser.add_argument("--image-size", type=str, default="Unknown", help="Measured Docker image size")
    parser.add_argument("--output-json", type=Path, required=True, help="Destination JSON path")
    parser.add_argument("--step-summary", type=Path, default=None, help="Path to GITHUB_STEP_SUMMARY file")

    args = parser.parse_args()

    runs_data: List[Dict[str, Any]] = []
    for idx, path in enumerate([args.run1, args.run2, args.run3], start=1):
        parsed = parse_locust_stats(path)
        parsed["run_number"] = idx
        runs_data.append(parsed)

    median_p50 = round(statistics.median([r["p50_ms"] for r in runs_data]), 2)
    median_p95 = round(statistics.median([r["p95_ms"] for r in runs_data]), 2)
    median_rps = round(statistics.median([r["rps"] for r in runs_data]), 2)
    median_error_rate = round(statistics.median([r["error_rate_pct"] for r in runs_data]), 2)
    total_requests = sum(r["requests"] for r in runs_data)
    total_failures = sum(r["failures"] for r in runs_data)

    summary_payload = {
        "runner_environment": {
            "vcpus": args.runner_cpus,
            "ram_mb": args.runner_ram,
            "docker_image_size": args.image_size,
            "architecture_note": "Client (Locust) and server (FastAPI container) co-located on runner sharing CPU and memory",
        },
        "load_profile": {
            "warmup_seconds": 10,
            "run_duration_seconds": 30,
            "ramp_up_seconds": 5,
            "concurrency_users": 25,
            "iterations": 3,
        },
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

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    # Generate Markdown Summary
    md_content = f"""## 🚀 Container & Load Benchmarks (Measured in CI)

### 🖥️ Runner Specifications & Container Footprint
- **Runner Environment**: GitHub-hosted Ubuntu (`{args.runner_cpus}` vCPUs, `{args.runner_ram} MB` RAM)
- **Container Footprint**: `{args.image_size}` (local uncompressed size, measured via `docker images`)
- **Execution Topology**: Co-located on runner (**Client and server share runner CPU & memory**)
- **Target Endpoint**: `POST /predict` (with runtime `X-API-Key` authentication)

### ⏱️ Load Test Profile
- **Warm-up**: 10 seconds
- **Test Duration**: 30 seconds per run (includes ~5s ramp-up)
- **Concurrency**: 25 concurrent users (ramp rate: 5 users/sec, 0s think time)
- **Number of Runs**: 3 consecutive runs (reporting median over the three runs' per-run percentiles)

### 📊 Benchmark Results

| Metric | Run 1 | Run 2 | Run 3 | **Median (Reported)** |
| :--- | :---: | :---: | :---: | :---: |
| **P50 Latency (Median)** | `{runs_data[0]['p50_ms']} ms` | `{runs_data[1]['p50_ms']} ms` | `{runs_data[2]['p50_ms']} ms` | **`{median_p50} ms`** |
| **P95 Latency** | `{runs_data[0]['p95_ms']} ms` | `{runs_data[1]['p95_ms']} ms` | `{runs_data[2]['p95_ms']} ms` | **`{median_p95} ms`** |
| **Throughput (Requests/s)** | `{runs_data[0]['rps']} req/s` | `{runs_data[1]['rps']} req/s` | `{runs_data[2]['rps']} req/s` | **`{median_rps} req/s`** |
| **Error Rate** | `{runs_data[0]['error_rate_pct']}%` | `{runs_data[1]['error_rate_pct']}%` | `{runs_data[2]['error_rate_pct']}%` | **`{median_error_rate}%`** |
| **Requests Served** | `{runs_data[0]['requests']}` | `{runs_data[1]['requests']}` | `{runs_data[2]['requests']}` | `{total_requests} (Total)` |

> **Note**: These benchmarks were measured on a GitHub Actions runner where Locust and the FastAPI container share the runner's CPU. The model served was bootstrapped in CI with `n_iter=2`, so measured latencies refer to that model artifact.
"""

    print(md_content)

    if args.step_summary and args.step_summary.parent.exists():
        with open(args.step_summary, "a", encoding="utf-8") as f:
            f.write(md_content + "\n")

    # Validity checks: fail only if benchmark run was invalid
    if total_requests == 0:
        print("ERROR: Total requests served across all benchmark runs is 0. Load test failed.", file=sys.stderr)
        sys.exit(1)

    if median_error_rate > 5.0:
        print(f"ERROR: Median error rate {median_error_rate}% exceeds 5% validity threshold.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
