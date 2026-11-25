"""In-process micro-benchmark for single-row /predict latency breakdown.

Loads the PredictionService in identical fashion to the production FastAPI app
and executes N=2000 single-row inference requests with realistic customer payloads.
Measures and reports the Mean, P50, and P95 latency (in milliseconds) per stage using time.perf_counter:
1. DataFrame Construction (dict -> pd.DataFrame)
2. ColumnTransformer (fit-time pipeline transformation)
3. Schema Validation (validate_feature_schema)
4. Model Inference (predict_proba)
5. Response Building (thresholding & dictionary construction)
"""

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from src.core.config import get_settings
from src.inference.service import prediction_service
from src.training.train import validate_feature_schema

CUSTOMER_SAMPLE = {
    "customerID": "7590-VHVEG",
    "gender": "Female",
    "SeniorCitizen": 0,
    "Partner": "Yes",
    "Dependents": "No",
    "tenure": 1,
    "PhoneService": "No",
    "MultipleLines": "No phone service",
    "InternetService": "DSL",
    "OnlineSecurity": "No",
    "OnlineBackup": "Yes",
    "DeviceProtection": "No",
    "TechSupport": "No",
    "StreamingTV": "No",
    "StreamingMovies": "No",
    "Contract": "Month-to-month",
    "PaperlessBilling": "Yes",
    "PaymentMethod": "Electronic check",
    "MonthlyCharges": 29.85,
    "TotalCharges": "29.85",
}


def run_profiler(n_iterations: int = 2000, warmup: int = 50) -> Dict[str, Any]:
    """Execute timed profiling over n_iterations."""
    print("Ensuring Production model is loaded in prediction service...")
    prediction_service.load_production_model()

    print(f"Executing {warmup} warmup iterations...")
    for _ in range(warmup):
        prediction_service.predict(CUSTOMER_SAMPLE)

    timings: Dict[str, List[float]] = {
        "1_dataframe_construction": [],
        "2_column_transformer": [],
        "3_schema_validation": [],
        "4_model_predict": [],
        "5_response_building": [],
        "total_service_predict": [],
    }

    settings = get_settings()
    schema_path = prediction_service.schema_path or Path(settings.FEATURE_SCHEMA_PATH)

    print(f"Starting {n_iterations} measured iterations with time.perf_counter()...")
    for _ in range(n_iterations):
        t0 = time.perf_counter()

        # Stage 1: DataFrame construction
        t1_start = time.perf_counter()
        df_raw = pd.DataFrame([CUSTOMER_SAMPLE])
        customer_id = df_raw.get("customerID", [None])[0] if "customerID" in df_raw else None
        X_raw = df_raw.drop(columns=["customerID", "Churn"], errors="ignore")
        t1_end = time.perf_counter()

        # Stage 2: ColumnTransformer
        t2_start = time.perf_counter()
        X_transformed = prediction_service.feature_pipeline.transform(X_raw)
        if prediction_service.expected_features and len(prediction_service.expected_features) == X_transformed.shape[1]:
            feature_cols = prediction_service.expected_features
        else:
            col_trans = prediction_service.feature_pipeline.named_steps["column_preprocessor"]
            cat_enc = col_trans.named_transformers_["cat"]
            cat_names = list(cat_enc.get_feature_names_out())
            num_names = list(col_trans.transformers[1][2])
            bin_names = list(col_trans.transformers[2][2])
            feature_cols = cat_names + num_names + bin_names
        X_proc_df = pd.DataFrame(X_transformed, columns=feature_cols)
        t2_end = time.perf_counter()

        # Stage 3: Schema validation
        t3_start = time.perf_counter()
        validate_feature_schema(X_proc_df, schema_path=schema_path, log_success=False)
        t3_end = time.perf_counter()

        # Stage 4: Model predict
        t4_start = time.perf_counter()
        probs = prediction_service.model.predict_proba(X_proc_df)[:, 1]
        prob = float(probs[0])
        t4_end = time.perf_counter()

        # Stage 5: Response building
        t5_start = time.perf_counter()
        churn_bool = prob >= prediction_service.optimal_threshold
        decision_str = "Churn" if churn_bool else "No Churn"
        _ = {
            "customerID": customer_id,
            "probability": round(prob, 6),
            "decision": decision_str,
            "churn_predicted": churn_bool,
            "threshold_used": round(prediction_service.optimal_threshold, 4),
            "model_version": prediction_service.model_version,
        }
        t5_end = time.perf_counter()

        t_total = time.perf_counter() - t0

        timings["1_dataframe_construction"].append((t1_end - t1_start) * 1000.0)
        timings["2_column_transformer"].append((t2_end - t2_start) * 1000.0)
        timings["3_schema_validation"].append((t3_end - t3_start) * 1000.0)
        timings["4_model_predict"].append((t4_end - t4_start) * 1000.0)
        timings["5_response_building"].append((t5_end - t5_start) * 1000.0)
        timings["total_service_predict"].append(t_total * 1000.0)

    summary: Dict[str, Any] = {}
    print("\n" + "=" * 80)
    print(f"PREDICT LATENCY BREAKDOWN (N={n_iterations} requests, time in milliseconds)")
    print("=" * 80)
    print(f"{'Stage':<35} | {'Mean (ms)':<10} | {'P50 (ms)':<10} | {'P95 (ms)':<10} | {'Share %':<8}")
    print("-" * 80)

    mean_total = statistics.mean(timings["total_service_predict"])

    for stage_key in [
        "1_dataframe_construction",
        "2_column_transformer",
        "3_schema_validation",
        "4_model_predict",
        "5_response_building",
        "total_service_predict",
    ]:
        vals = timings[stage_key]
        m = statistics.mean(vals)
        p50 = statistics.median(vals)
        p95 = float(np.percentile(vals, 95))
        share = (m / mean_total * 100.0) if stage_key != "total_service_predict" else 100.0

        label = stage_key.replace("_", " ").title()
        print(f"{label:<35} | {m:<10.3f} | {p50:<10.3f} | {p95:<10.3f} | {share:<7.1f}%")

        summary[stage_key] = {
            "mean_ms": round(m, 3),
            "p50_ms": round(p50, 3),
            "p95_ms": round(p95, 3),
            "share_pct": round(share, 1),
        }

    print("=" * 80)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Micro-benchmark /predict execution stages.")
    parser.add_argument("-n", "--iterations", type=int, default=2000, help="Number of iterations (default: 2000)")
    parser.add_argument("--output-json", type=Path, default=None, help="Save summary to JSON file")
    args = parser.parse_args()

    results = run_profiler(n_iterations=args.iterations)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved profile results to {args.output_json}")


if __name__ == "__main__":
    main()
