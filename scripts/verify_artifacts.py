"""Helper verification script to print artifact metrics cleanly for Step 4."""

import json
from typing import Any, Dict, List, Tuple

import pandas as pd
from mlflow.tracking import MlflowClient

train_df = pd.read_csv("data/processed/train.csv")
test_df = pd.read_csv("data/processed/test.csv")

with open("models/feature_schema.json", "r", encoding="utf-8") as f:
    schema: Dict[str, Any] = json.load(f)

with open("models/decision_threshold.json", "r", encoding="utf-8") as f:
    thresh: Dict[str, Any] = json.load(f)

client = MlflowClient(tracking_uri="sqlite:///mlflow.db")
prod_models: List[Tuple[str, str, str]] = []

for m in client.search_registered_models():
    versions = client.search_model_versions(f"name='{m.name}'")
    for v in versions:
        if v.current_stage == "Production":
            prod_models.append((m.name, v.version, v.current_stage))

print("=== STEP 4 ARTIFACT CONTRACT VERIFICATION ===")
print(f"train.csv shape:                      {train_df.shape}")
print(f"test.csv shape:                       {test_df.shape}")
print(f"feature_schema.json feature_count:   {schema['feature_count']}")
print(f"decision_threshold.json threshold:    {thresh['optimal_threshold']}")
print(f"MLflow Production Model:              {prod_models}")
