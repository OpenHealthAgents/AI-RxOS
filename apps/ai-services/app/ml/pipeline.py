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
from datetime import date
from statistics import median
from typing import Any

from .algorithms import SafetyMultiOutputLogisticRegression
from uuid import UUID, uuid4

from .models import (
    DatasetRecord,
    MLDataset,
    ModelArchitecture,
    ModelArtifact,
    ModelCalibration,
    ModelEvaluationMetrics,
    ModelStage,
    TrainingRunMetadata,
    TrainingRunStatus,
)


class ValidationPipeline:
    """Computes evaluation metrics for classification models while preserving missing metrics as None."""

    @staticmethod
    def evaluate(
        y_true: list[float],
        y_prob: list[float],
        threshold: float = 0.5,
    ) -> ModelEvaluationMetrics:
        if not y_true or not y_prob:
            return ModelEvaluationMetrics(
                accuracy=None,
                precision=None,
                recall=None,
                f1_score=None,
                roc_auc=None,
                brier_score=None,
                log_loss=None,
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
        positives = sum(1 for yt in y_true if yt >= 0.5)
        negatives = len(y_true) - positives
        if positives and negatives:
            sorted_pairs = sorted(zip(y_prob, y_true), key=lambda item: item[0], reverse=True)
            true_positives = 0
            false_positives = 0
            previous_recall = 0.0
            average_precision = 0.0
            index = 0
            while index < len(sorted_pairs):
                end = index + 1
                while end < len(sorted_pairs) and sorted_pairs[end][0] == sorted_pairs[index][0]:
                    end += 1
                group = sorted_pairs[index:end]
                true_positives += sum(outcome >= 0.5 for _, outcome in group)
                false_positives += len(group) - sum(outcome >= 0.5 for _, outcome in group)
                recall_at_threshold = true_positives / positives
                precision_at_threshold = true_positives / (true_positives + false_positives)
                average_precision += (recall_at_threshold - previous_recall) * precision_at_threshold
                previous_recall = recall_at_threshold
                index = end
            roc_auc = ValidationPipeline._compute_roc_auc(y_true, y_prob)
        else:
            average_precision = None
            roc_auc = None

        if average_precision is None:
            auprc = None
        else:
            auprc = max(0.0, min(1.0, float(average_precision)))

        return ModelEvaluationMetrics(
            accuracy=round(accuracy, 4),
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1_score=round(f1_score, 4),
            roc_auc=round(roc_auc, 4) if roc_auc is not None else None,
            average_precision=round(auprc, 4) if auprc is not None else None,
            auprc=round(auprc, 4) if auprc is not None else None,
            brier_score=round(brier_score, 4),
            log_loss=round(log_loss, 4),
        )

    @staticmethod
    def _compute_roc_auc(y_true: list[float], y_prob: list[float]) -> float:
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

    @staticmethod
    def expected_calibration_error(
        y_true: list[float],
        y_prob: list[float],
        bins: int = 5,
    ) -> float | None:
        """Calculate weighted absolute confidence/accuracy gap from observed predictions."""
        if not y_true or len(y_true) != len(y_prob):
            return None
        if bins < 1:
            raise ValueError("Calibration bins must be at least 1.")
        total_error = 0.0
        for bin_index in range(bins):
            lower = bin_index / bins
            upper = (bin_index + 1) / bins
            selected = [
                (float(outcome), float(probability))
                for outcome, probability in zip(y_true, y_prob)
                if lower <= probability < upper
                or (bin_index == bins - 1 and probability == 1.0)
            ]
            if not selected:
                continue
            accuracy = sum(outcome >= 0.5 for outcome, _ in selected) / len(selected)
            confidence = sum(probability for _, probability in selected) / len(selected)
            total_error += len(selected) / len(y_true) * abs(accuracy - confidence)
        return round(total_error, 4)


class TrainingPipeline:
    """End-to-end model training orchestrator with explicit lineage and calibration metadata."""

    def __init__(self, validation_pipeline: ValidationPipeline | None = None) -> None:
        self.validation_pipeline = validation_pipeline or ValidationPipeline()

    def _prepare_model_inputs(self, dataset: MLDataset, features: list[str] | None = None):
        feature_names = list(features or dataset.feature_names)
        train_recs = dataset.train_records
        val_recs = dataset.val_records if dataset.val_records else dataset.train_records
        if not train_recs:
            raise ValueError("Cannot train model on empty training dataset.")

        def _clean_records(records: list[DatasetRecord]):
            clean_X: list[list[float | None]] = []
            clean_y: list[float] = []
            for record in records:
                row: list[float | None] = []
                for feature_name in feature_names:
                    value = record.features.get(feature_name)
                    row.append(None if value is None else float(value))
                if record.label is None:
                    continue
                clean_X.append(row)
                clean_y.append(float(record.label))
            return clean_X, clean_y

        X_train, y_train = _clean_records(train_recs)
        X_val, y_val = _clean_records(val_recs)

        if not X_train or not X_val:
            raise ValueError("Training data cannot be prepared because all selected records are missing required label values.")

        import numpy as np
        from sklearn.impute import SimpleImputer

        X_train_array = np.asarray([[np.nan if value is None else float(value) for value in row] for row in X_train], dtype=float)
        X_val_array = np.asarray([[np.nan if value is None else float(value) for value in row] for row in X_val], dtype=float)

        if X_train_array.size == 0 or X_val_array.size == 0:
            raise ValueError("Training data cannot be prepared because no valid feature values remain after filtering missing records.")

        valid_columns = ~np.all(np.isnan(X_train_array), axis=0)
        if not np.any(valid_columns):
            raise ValueError("Training data cannot be prepared because every feature column is missing in the training set.")

        X_train_array = X_train_array[:, valid_columns]
        X_val_array = X_val_array[:, valid_columns]
        feature_names = [feature_names[i] for i, keep in enumerate(valid_columns) if keep]

        imputer = SimpleImputer(strategy="median")
        X_train_array = imputer.fit_transform(X_train_array)
        X_val_array = imputer.transform(X_val_array)

        return feature_names, X_train_array.tolist(), y_train, X_val_array.tolist(), y_val

    def _build_calibration(self, method: str | None, dataset_split: str | None, metrics: dict[str, float | None], artifact_version: str | None) -> ModelCalibration:
        return ModelCalibration(
            performed=method is not None,
            method=method,
            dataset_split=dataset_split,
            metrics=metrics,
            artifact_version=artifact_version,
        )

    def train(
        self,
        dataset: MLDataset,
        architecture: ModelArchitecture = ModelArchitecture.LOGISTIC_REGRESSION,
        hyperparameters: dict[str, Any] | None = None,
        stage: ModelStage = ModelStage.DEVELOPMENT,
        model_name: str | None = None,
        model_version: str | None = None,
        selected_features: list[str] | None = None,
        selected_labels: list[str] | None = None,
        random_seed: int | None = None,
        training_cutoff: Any | None = None,
        validation_cutoff: Any | None = None,
        test_cutoff: Any | None = None,
        calibration_method: str | None = None,
        calibration_split: str | None = None,
        training_run_id: Any | None = None,
        tenant_id: str | None = None,
    ) -> ModelArtifact:
        """Trains the specified architecture and packages it into a ModelArtifact."""
        def resolve_cutoff(value: Any | None, fallback: date | None) -> date | None:
            resolved = value if value is not None else fallback
            if resolved is not None and not isinstance(resolved, date):
                raise ValueError("Training and evaluation cutoffs must be dates.")
            return resolved

        params = dict(hyperparameters or {})
        resolved_training_cutoff = resolve_cutoff(training_cutoff, dataset.cutoff_date)
        resolved_validation_cutoff = resolve_cutoff(validation_cutoff, dataset.cutoff_date)
        resolved_test_cutoff = resolve_cutoff(test_cutoff, dataset.cutoff_date)
        feature_names, X_train, y_train, X_val, y_val = self._prepare_model_inputs(dataset, selected_features)

        # Model instantiation and fitting
        intercept = 0.0
        weights_dict: dict[str, Any] = {}
        val_probs: list[float] = []
        fitted_model: Any = None
        output_metrics: dict[str, dict[str, float | None]] = {}

        if architecture == ModelArchitecture.LOGISTIC_REGRESSION and dataset.metadata.get("model_family") == "safety":
            target_names = list(dataset.metadata.get("safety_targets", []))
            if not target_names:
                raise ValueError("Safety dataset does not declare any output targets.")
            train_records = [record for record in dataset.train_records if record.label is not None]
            val_records = [
                record
                for record in (dataset.val_records or dataset.train_records)
                if record.label is not None
            ]
            train_targets: dict[str, list[float]] = {}
            val_targets: dict[str, list[float]] = {}
            for target_name in target_names:
                train_values = [record.metadata.get("safety_labels", {}).get(target_name) for record in train_records]
                validation_values = [record.metadata.get("safety_labels", {}).get(target_name) for record in val_records]
                if any(value not in (0, 0.0, 1, 1.0) for value in train_values + validation_values):
                    raise ValueError(f"Safety target '{target_name}' has unknown labels in the training/evaluation split.")
                train_targets[target_name] = [float(value) for value in train_values]
                val_targets[target_name] = [float(value) for value in validation_values]

            fitted_model = SafetyMultiOutputLogisticRegression(
                target_names,
                random_state=42 if random_seed is None else random_seed,
                max_iter=params.get("max_iter", 500),
                C=params.get("C", 1.0),
            ).fit(X_train, train_targets)
            predicted_by_target = fitted_model.predict_proba(X_val)
            for target_name in target_names:
                target_probabilities = predicted_by_target[target_name]
                target_true = val_targets[target_name]
                target_metrics = self.validation_pipeline.evaluate(target_true, target_probabilities)
                output_metrics[target_name] = target_metrics.model_dump()
                output_metrics[target_name]["expected_calibration_error"] = (
                    self.validation_pipeline.expected_calibration_error(
                        target_true,
                        target_probabilities,
                    )
                )
                val_probs.extend(target_probabilities)
            weights = fitted_model.estimators_[target_names[0]].coef_[0].tolist()
            intercept = float(fitted_model.estimators_[target_names[0]].intercept_[0])
            weights_dict = {
                "sklearn_model": True,
                "multi_output": True,
                "primary_explanation_target": target_names[0],
                "weights": weights,
                "coef_": fitted_model.estimators_[target_names[0]].coef_.tolist(),
                "intercept": intercept,
                "intercept_": fitted_model.estimators_[target_names[0]].intercept_.tolist(),
                "n_features_in_": fitted_model.estimators_[target_names[0]].n_features_in_,
                "feature_importances": {i: abs(float(weight)) for i, weight in enumerate(weights)},
            }

        elif architecture == ModelArchitecture.LOGISTIC_REGRESSION:
            from sklearn.linear_model import LogisticRegression as SkLogisticRegression

            skl = SkLogisticRegression(
                solver="liblinear",
                random_state=42 if random_seed is None else random_seed,
                max_iter=params.get("max_iter", 500),
                C=params.get("C", 1.0),
            )
            skl.fit(X_train, y_train)
            val_probs = skl.predict_proba(X_val)[:, 1].tolist()
            weights = skl.coef_[0].tolist()
            weights_dict = {
                "sklearn_model": True,
                "weights": weights,
                "coef_": skl.coef_.tolist(),
                "intercept": float(skl.intercept_[0]),
                "intercept_": skl.intercept_.tolist(),
                "n_features_in_": skl.n_features_in_,
                "feature_importances": {i: abs(float(w)) for i, w in enumerate(weights)},
            }
            intercept = float(skl.intercept_[0])
            fitted_model = skl

        elif architecture == ModelArchitecture.RANDOM_FOREST:
            from sklearn.ensemble import RandomForestClassifier

            rf_model = RandomForestClassifier(
                n_estimators=params.get("n_estimators", 50),
                max_depth=params.get("max_depth", 5),
                min_samples_split=params.get("min_samples_split", 2),
                random_state=42 if random_seed is None else random_seed,
            )
            rf_model.fit(X_train, y_train)
            val_probs = rf_model.predict_proba(X_val)[:, 1].tolist()
            weights_dict = {
                "sklearn_model": True,
                "estimators_": [tree.tree_.__getstate__() for tree in rf_model.estimators_],
                "n_estimators": rf_model.n_estimators,
            }
            fitted_model = rf_model

        elif architecture == ModelArchitecture.GRADIENT_BOOSTING:
            from sklearn.ensemble import GradientBoostingClassifier

            gb_model = GradientBoostingClassifier(
                n_estimators=params.get("n_estimators", 50),
                learning_rate=params.get("learning_rate", 0.05),
                max_depth=params.get("max_depth", 3),
                random_state=42 if random_seed is None else random_seed,
            )
            gb_model.fit(X_train, y_train)
            val_probs = gb_model.predict_proba(X_val)[:, 1].tolist()
            weights_dict = {
                "sklearn_model": True,
                "estimators_": [estimator[0].__getstate__() for estimator in gb_model.estimators_],
            }
            intercept = float(gb_model.init_.class_prior_[1])
            fitted_model = gb_model

        else:
            raise ValueError(f"Unsupported architecture: {architecture}")

        if output_metrics:
            flattened_y = [
                value
                for target_name in output_metrics
                for value in val_targets[target_name]
            ]
            metrics = self.validation_pipeline.evaluate(flattened_y, val_probs)
        else:
            metrics = self.validation_pipeline.evaluate(y_val, val_probs)
        artifact_name = model_name or f"{dataset.target_name}_{architecture.value}"
        artifact_version = model_version or f"v1.{len(dataset.train_records)}"
        reference_distributions = {
            feature_name: [row[index] for row in X_train]
            for index, feature_name in enumerate(feature_names)
        }
        reference_missing_rates = {
            feature_name: (
                sum(record.features.get(feature_name) is None for record in dataset.train_records)
                / len(dataset.train_records)
                if dataset.train_records else None
            )
            for feature_name in feature_names
        }
        feature_imputation_values = {
            feature_name: median(values)
            for feature_name in feature_names
            if (
                values := [
                    float(record.features[feature_name])
                    for record in dataset.train_records
                    if record.features.get(feature_name) is not None
                ]
            )
        }

        calibration_metrics = {"calibration_brier_score": metrics.brier_score, "calibration_log_loss": metrics.log_loss}
        calibration = self._build_calibration(
            calibration_method,
            calibration_split,
            calibration_metrics,
            artifact_version,
        ) if calibration_method else None

        run_id = training_run_id if isinstance(training_run_id, UUID) else uuid4() if training_run_id is None else uuid4()
        run_metadata = TrainingRunMetadata(
            run_id=run_id,
            model_name=artifact_name,
            model_type=architecture.value,
            dataset_name=dataset.name,
            dataset_version=dataset.version,
            feature_versions=dataset.feature_versions,
            label_versions=dataset.label_versions,
            selected_features=feature_names,
            selected_labels=selected_labels or [dataset.target_name],
            training_cutoff=resolved_training_cutoff,
            validation_cutoff=resolved_validation_cutoff,
            test_cutoff=resolved_test_cutoff,
            hyperparameters=params,
            random_seed=random_seed,
            metrics={
                "accuracy": metrics.accuracy,
                "precision": metrics.precision,
                "recall": metrics.recall,
                "f1_score": metrics.f1_score,
                "roc_auc": metrics.roc_auc,
                "brier_score": metrics.brier_score,
                "log_loss": metrics.log_loss,
            },
            calibration=calibration,
            artifact_reference=f"artifact:{artifact_name}:{artifact_version}",
            status=TrainingRunStatus.SUCCEEDED,
            tenant_id=tenant_id,
        )

        artifact = ModelArtifact(
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
            feature_versions=dataset.feature_versions,
            label_versions=dataset.label_versions,
            training_cutoff=resolved_training_cutoff,
            validation_cutoff=resolved_validation_cutoff,
            test_cutoff=resolved_test_cutoff,
            artifact_reference=run_metadata.artifact_reference,
            calibration=calibration,
            random_seed=random_seed,
            training_run_id=run_id,
            tenant_id=tenant_id,
            lineage={
                "dataset_name": dataset.name,
                "dataset_version": dataset.version,
                "dataset_metadata": dataset.metadata,
                "feature_versions": dataset.feature_versions,
                "label_versions": dataset.label_versions,
                "target_name": dataset.target_name,
                "output_metrics": output_metrics,
                "calibration_metrics": {
                    target_name: {
                        "brier_score": target_values["brier_score"],
                        "log_loss": target_values["log_loss"],
                        "expected_calibration_error": target_values["expected_calibration_error"],
                    }
                    for target_name, target_values in output_metrics.items()
                },
                "training_cutoff": resolved_training_cutoff.isoformat() if resolved_training_cutoff else None,
                "validation_cutoff": resolved_validation_cutoff.isoformat() if resolved_validation_cutoff else None,
                "test_cutoff": resolved_test_cutoff.isoformat() if resolved_test_cutoff else None,
                "reference_training_sample_count": len(X_train),
                "reference_validation_metrics": {
                    "accuracy": metrics.accuracy,
                    "precision": metrics.precision,
                    "recall": metrics.recall,
                    "f1_score": metrics.f1_score,
                    "roc_auc": metrics.roc_auc,
                    "brier_score": metrics.brier_score,
                    "log_loss": metrics.log_loss,
                },
            },
            monitoring_reference={
                "feature_distributions": reference_distributions,
                "feature_missing_rates": reference_missing_rates,
                "feature_imputation_values": feature_imputation_values,
                "sample_count": len(X_train),
            },
            fitted_model=fitted_model,
            is_active=True,
        )
        return artifact
