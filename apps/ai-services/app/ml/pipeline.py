"""
Training and Validation Pipelines for Interpretable ML.

Components:
1. ValidationPipeline:
   - Computes rigorous classification metrics:
     - Accuracy, Precision, Recall, F1 Score
     - ROC-AUC (Wilcoxon-Mann-Whitney rank-sum)
     - Brier Score (probability calibration)
     - Log Loss (binary cross-entropy)
2. TrainingPipeline:
   - Trains configured architecture on MLDataset train records
   - Validates on validation split
   - Produces deterministic, registered ModelArtifact
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .algorithms import (
    GradientBoostingBaseline,
    LogisticRegressionModel,
    RandomForestBaseline,
)
from .models import (
    DatasetRecord,
    MLDataset,
    ModelArchitecture,
    ModelArtifact,
    ModelEvaluationMetrics,
    ModelStage,
)


class ValidationPipeline:
    """Computes comprehensive evaluation metrics for classification models."""

    @staticmethod
    def evaluate(
        y_true: List[float],
        y_prob: List[float],
        threshold: float = 0.5,
    ) -> ModelEvaluationMetrics:
        if not y_true or not y_prob:
            return ModelEvaluationMetrics(
                accuracy=0.0,
                precision=0.0,
                recall=0.0,
                f1_score=0.0,
                roc_auc=0.5,
                brier_score=0.0,
                log_loss=0.0,
            )

        n = len(y_true)
        y_pred = [1 if p >= threshold else 0 for p in y_prob]

        # Confusion Matrix
        tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt >= 0.5 and yp == 1)
        fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt < 0.5 and yp == 1)
        fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt >= 0.5 and yp == 0)
        tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt < 0.5 and yp == 0)

        # Standard classification metrics
        accuracy = (tp + tn) / n
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1_score = (
            2.0 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        # Brier Score (mean squared error of probabilities)
        brier_score = sum((p - yt) ** 2 for yt, p in zip(y_true, y_prob)) / n

        # Log Loss (with epsilon protection)
        eps = 1e-15
        log_loss = -sum(
            yt * math.log(max(p, eps)) + (1.0 - yt) * math.log(max(1.0 - p, eps))
            for yt, p in zip(y_true, y_prob)
        ) / n

        # ROC-AUC via Wilcoxon-Mann-Whitney rank-sum
        roc_auc = ValidationPipeline._compute_roc_auc(y_true, y_prob)

        return ModelEvaluationMetrics(
            accuracy=round(accuracy, 4),
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1_score=round(f1_score, 4),
            roc_auc=round(roc_auc, 4),
            brier_score=round(brier_score, 4),
            log_loss=round(log_loss, 4),
        )

    @staticmethod
    def _compute_roc_auc(y_true: List[float], y_prob: List[float]) -> float:
        """Calculates exact ROC-AUC using rank-sum statistic."""
        positives = [p for yt, p in zip(y_true, y_prob) if yt >= 0.5]
        negatives = [p for yt, p in zip(y_true, y_prob) if yt < 0.5]

        n_pos = len(positives)
        n_neg = len(negatives)

        if n_pos == 0 or n_neg == 0:
            return 0.5

        # Combined sorted pairs
        paired = sorted(zip(y_prob, y_true), key=lambda x: x[0])
        rank_sum = 0.0
        i = 0
        while i < len(paired):
            # Check for ties
            j = i
            while j < len(paired) and paired[j][0] == paired[i][0]:
                j += 1
            avg_rank = (i + 1 + j) / 2.0
            for k in range(i, j):
                if paired[k][1] >= 0.5:
                    rank_sum += avg_rank
            i = j

        auc = (rank_sum - (n_pos * (n_pos + 1)) / 2.0) / (n_pos * n_neg)
        return max(0.0, min(1.0, auc))


class TrainingPipeline:
    """End-to-end model training orchestrator."""

    def __init__(self, validation_pipeline: Optional[ValidationPipeline] = None) -> None:
        self.validation_pipeline = validation_pipeline or ValidationPipeline()

    def train(
        self,
        dataset: MLDataset,
        architecture: ModelArchitecture = ModelArchitecture.LOGISTIC_REGRESSION,
        hyperparameters: Optional[Dict[str, Any]] = None,
        stage: ModelStage = ModelStage.DEVELOPMENT,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> ModelArtifact:
        """Trains the specified architecture and packages it into a ModelArtifact."""
        params = hyperparameters or {}
        feature_names = dataset.feature_names

        # Fallback to train records if val records are empty
        train_recs = dataset.train_records
        val_recs = dataset.val_records if dataset.val_records else dataset.train_records

        if not train_recs:
            raise ValueError("Cannot train model on empty training dataset.")

        X_train = [[r.features.get(f, 0.0) for f in feature_names] for r in train_recs]
        y_train = [r.label for r in train_recs]

        X_val = [[r.features.get(f, 0.0) for f in feature_names] for r in val_recs]
        y_val = [r.label for r in val_recs]

        # Model instantiation and fitting
        intercept = 0.0
        weights_dict: Dict[str, Any] = {}

        if architecture == ModelArchitecture.LOGISTIC_REGRESSION:
            lr_model = LogisticRegressionModel(
                learning_rate=params.get("learning_rate", 0.05),
                max_iter=params.get("max_iter", 300),
                l2_penalty=params.get("l2_penalty", 0.01),
            )
            lr_model.fit(X_train, y_train)
            val_probs = lr_model.predict_proba(X_val)
            weights_dict = lr_model.to_dict()
            intercept = lr_model.intercept

        elif architecture == ModelArchitecture.RANDOM_FOREST:
            rf_model = RandomForestBaseline(
                n_estimators=params.get("n_estimators", 10),
                max_depth=params.get("max_depth", 3),
                min_samples_split=params.get("min_samples_split", 2),
                seed=params.get("seed", 42),
            )
            rf_model.fit(X_train, y_train)
            val_probs = rf_model.predict_proba(X_val)
            weights_dict = rf_model.to_dict()

        elif architecture == ModelArchitecture.GRADIENT_BOOSTING:
            gb_model = GradientBoostingBaseline(
                n_estimators=params.get("n_estimators", 15),
                learning_rate=params.get("learning_rate", 0.1),
            )
            gb_model.fit(X_train, y_train)
            val_probs = gb_model.predict_proba(X_val)
            weights_dict = gb_model.to_dict()
            intercept = gb_model.base_log_odds

        else:
            raise ValueError(f"Unsupported architecture: {architecture}")

        # Compute validation performance
        metrics = self.validation_pipeline.evaluate(y_val, val_probs)

        # Assemble ModelArtifact
        artifact_name = model_name or f"{dataset.target_name}_{architecture.value}"
        artifact_version = model_version or f"v1.{len(dataset.train_records)}"

        return ModelArtifact(
            model_id=uuid4(),
            name=artifact_name,
            version=artifact_version,
            architecture=architecture,
            stage=stage,
            feature_names=feature_names,
            hyperparameters=params,
            coefficients_or_weights=weights_dict,
            intercept=intercept,
            metrics=metrics,
            dataset_version=dataset.version,
            is_active=True,
        )
