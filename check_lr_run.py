import mlflow

client = mlflow.tracking.MlflowClient(tracking_uri="sqlite:///mlflow.db")
runs = client.search_runs(
    experiment_ids=["1"],
    filter_string="tags.candidate_family = 'LogisticRegression'",
)
if not runs:
    print("NO RUNS FOUND matching that filter.")
for r in runs:
    print("LR Run ID:", r.info.run_id)
    print("Tags:", r.data.tags)
    print("Artifacts:", client.list_artifacts(r.info.run_id))
