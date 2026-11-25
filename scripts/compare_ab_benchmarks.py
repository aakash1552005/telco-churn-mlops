"""Parse and compare A/B benchmark runs within a single CI job.

Runs 3 alternating rounds between Baseline and Optimized images across the 3 profiles:
- Low concurrency (1 user)
- Low concurrency (5 users)
- High concurrency (25 users)

Computes the median across the 3 rounds for each image, and calculates the exact
median relative latency and throughput change:
    Relative Latency Delta (%) = ((Optimized - Baseline) / Baseline) * 100
Outputs a Markdown comparison table to $GITHUB_STEP_SUMMARY and a structured JSON artifact.
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


def aggregate_variant_profile(paths: List[Path], profile_name: str, concurrency: int) -> Dict[str, Any]:
    """Aggregate per-round runs for a variant's profile."""
    runs = []
    for idx, p in enumerate(paths, start=1):
        parsed = parse_locust_stats(p)
        parsed["round"] = idx
        runs.append(parsed)

    med_p50 = round(statistics.median([r["p50_ms"] for r in runs]), 2)
    med_p95 = round(statistics.median([r["p95_ms"] for r in runs]), 2)
    med_rps = round(statistics.median([r["rps"] for r in runs]), 2)
    med_err = round(statistics.median([r["error_rate_pct"] for r in runs]), 2)
    tot_reqs = sum(r["requests"] for r in runs)
    tot_fails = sum(r["failures"] for r in runs)

    return {
        "profile_name": profile_name,
        "concurrency": concurrency,
        "rounds": runs,
        "median": {
            "p50_ms": med_p50,
            "p95_ms": med_p95,
            "rps": med_rps,
            "error_rate_pct": med_err,
            "total_requests": tot_reqs,
            "total_failures": tot_fails,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="A/B Benchmark comparison parser.")
    parser.add_argument("--dir", type=Path, required=True, help="Directory containing A/B Locust reports")
    parser.add_argument("--output-json", type=Path, required=True, help="Output JSON comparison path")
    parser.add_argument("--step-summary", type=Path, default=None, help="GitHub Step Summary output path")
    args = parser.parse_args()

    profiles = [
        ("u1", "Low concurrency (1 user)", 1),
        ("u5", "Low concurrency (5 users)", 5),
        ("u25", "High concurrency (25 users)", 25),
    ]

    variants = ["baseline", "optimized"]
    results: Dict[str, Dict[str, Any]] = {"baseline": {}, "optimized": {}}

    for var in variants:
        for prefix, name, conc in profiles:
            paths = [
                args.dir / f"{var}_{prefix}_r1_stats.csv",
                args.dir / f"{var}_{prefix}_r2_stats.csv",
                args.dir / f"{var}_{prefix}_r3_stats.csv",
            ]
            results[var][prefix] = aggregate_variant_profile(paths, name, conc)

    comparison_rows = []
    for prefix, name, conc in profiles:
        base_m = results["baseline"][prefix]["median"]
        opt_m = results["optimized"][prefix]["median"]

        p50_delta = round(((opt_m["p50_ms"] - base_m["p50_ms"]) / base_m["p50_ms"]) * 100.0, 1) if base_m["p50_ms"] > 0 else 0.0
        p95_delta = round(((opt_m["p95_ms"] - base_m["p95_ms"]) / base_m["p95_ms"]) * 100.0, 1) if base_m["p95_ms"] > 0 else 0.0
        rps_delta = round(((opt_m["rps"] - base_m["rps"]) / base_m["rps"]) * 100.0, 1) if base_m["rps"] > 0 else 0.0

        comparison_rows.append({
            "name": name,
            "concurrency": conc,
            "base_p50": base_m["p50_ms"],
            "opt_p50": opt_m["p50_ms"],
            "p50_delta": p50_delta,
            "base_p95": base_m["p95_ms"],
            "opt_p95": opt_m["p95_ms"],
            "p95_delta": p95_delta,
            "base_rps": base_m["rps"],
            "opt_rps": opt_m["rps"],
            "rps_delta": rps_delta,
        })

    payload = {
        "baseline": results["baseline"],
        "optimized": results["optimized"],
        "comparison": comparison_rows,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    # Generate Markdown Summary
    md = [
        "## 🏎️ In-Job A/B Benchmark: Baseline vs. Optimized (Alternating Rounds)",
        "",
        "Both images were built and evaluated within this single job execution across 3 alternating rounds (Baseline Round 1 -> Optimized Round 1 -> Baseline Round 2 -> Optimized Round 2 -> Baseline Round 3 -> Optimized Round 3) to strictly isolate code performance from host noise.",
        "",
        "### 📊 Comparative Performance Matrix (Medians across 3 rounds)",
        "",
        "| Profile | P50 (Baseline) | P50 (Optimized) | **P50 Delta** | P95 (Baseline) | P95 (Optimized) | **P95 Delta** | Throughput (Baseline) | Throughput (Optimized) | **RPS Delta** |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for row in comparison_rows:
        p50_sign = "+" if row["p50_delta"] > 0 else ""
        p95_sign = "+" if row["p95_delta"] > 0 else ""
        rps_sign = "+" if row["rps_delta"] > 0 else ""
        md.append(
            f"| **{row['name']}** | `{row['base_p50']} ms` | `{row['opt_p50']} ms` | **`{p50_sign}{row['p50_delta']}%`** | `{row['base_p95']} ms` | `{row['opt_p95']} ms` | **`{p95_sign}{row['p95_delta']}%`** | `{row['base_rps']} req/s` | `{row['opt_rps']} req/s` | **`{rps_sign}{row['rps_delta']}%`** |"
        )

    md_str = "\n".join(md)
    print(md_str)

    if args.step_summary and args.step_summary.parent.exists():
        with open(args.step_summary, "a", encoding="utf-8") as f:
            f.write(md_str + "\n")


if __name__ == "__main__":
    main()
