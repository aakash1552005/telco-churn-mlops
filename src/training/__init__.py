"""Model training, hyperparameter tuning, and evaluation modules."""

from src.training.evaluate import (
    evaluate_model,
    generate_evaluation_report,
    optimize_threshold,
    plot_confusion_matrix,
    plot_feature_importance,
)
from src.training.promotion import (
    compare_candidate_to_incumbent,
    load_promotion_policy,
    log_pipeline_run_to_mlflow,
    promote_model,
)
from src.training.train import (
    log_class_balance,
    roc_auc_binary_scorer,
    train_candidate_models,
    validate_feature_schema,
)

__all__ = [
    "train_candidate_models",
    "validate_feature_schema",
    "log_class_balance",
    "roc_auc_binary_scorer",
    "evaluate_model",
    "optimize_threshold",
    "generate_evaluation_report",
    "plot_feature_importance",
    "plot_confusion_matrix",
    "promote_model",
    "compare_candidate_to_incumbent",
    "load_promotion_policy",
    "log_pipeline_run_to_mlflow",
]
