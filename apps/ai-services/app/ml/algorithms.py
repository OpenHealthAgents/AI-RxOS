"""
Interpretable Machine Learning Baseline Algorithms.

Pure-Python statistical implementations of:
1. Logistic Regression (calibrated coefficients, L2 regularization, gradient descent)
2. Random Forest (ensemble of decision trees with bootstrap aggregation)
3. Gradient Boosting (additive regression trees on log-loss pseudo-residuals)

All models are deterministic, transparent, and produce exact probability distributions
and feature importance scores without black-box opacity or external dependencies.
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple


def _sigmoid(z: float) -> float:
    """Numerically stable sigmoid function."""
    z_clamped = max(min(z, 35.0), -35.0)
    return 1.0 / (1.0 + math.exp(-z_clamped))


def _dot(a: List[float], b: List[float]) -> float:
    """Dot product of two vectors."""
    return sum(x * y for x, y in zip(a, b))


# ==============================================================================
# 1. Logistic Regression Model
# ==============================================================================

class LogisticRegressionModel:
    """
    Interpretable baseline binary logistic regression classifier.
    Optimized via gradient descent with L2 (Ridge) penalty.
    """

    def __init__(
        self,
        learning_rate: float = 0.05,
        max_iter: int = 300,
        l2_penalty: float = 0.01,
    ) -> None:
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.l2_penalty = l2_penalty
        self.weights: List[float] = []
        self.intercept: float = 0.0
        self.n_features: int = 0

    def fit(self, X: List[List[float]], y: List[float]) -> LogisticRegressionModel:
        if not X or not y:
            raise ValueError("Training dataset cannot be empty.")
        n_samples = len(X)
        self.n_features = len(X[0])

        # Initialize weights
        self.weights = [0.0] * self.n_features
        self.intercept = 0.0

        for _ in range(self.max_iter):
            # Compute predictions
            preds = [_sigmoid(self.intercept + _dot(self.weights, x)) for x in X]

            # Compute gradients
            errors = [p - target for p, target in zip(preds, y)]
            grad_intercept = sum(errors) / n_samples

            grad_weights = [0.0] * self.n_features
            for j in range(self.n_features):
                grad_w = sum(errors[i] * X[i][j] for i in range(n_samples)) / n_samples
                # L2 regularization gradient
                grad_w += self.l2_penalty * self.weights[j]
                grad_weights[j] = grad_w

            # Gradient descent step
            self.intercept -= self.learning_rate * grad_intercept
            for j in range(self.n_features):
                self.weights[j] -= self.learning_rate * grad_weights[j]

        return self

    def predict_proba(self, X: List[List[float]]) -> List[float]:
        return [_sigmoid(self.intercept + _dot(self.weights, x)) for x in X]

    def predict(self, X: List[List[float]], threshold: float = 0.5) -> List[int]:
        probas = self.predict_proba(X)
        return [1 if p >= threshold else 0 for p in probas]

    def get_feature_importances(self, feature_names: List[str]) -> Dict[str, float]:
        """Returns normalized absolute magnitude of coefficients."""
        total_mag = sum(abs(w) for w in self.weights) or 1.0
        return {
            name: round(abs(w) / total_mag, 4)
            for name, w in zip(feature_names, self.weights)
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "learning_rate": self.learning_rate,
            "max_iter": self.max_iter,
            "l2_penalty": self.l2_penalty,
            "weights": self.weights,
            "intercept": self.intercept,
            "n_features": self.n_features,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LogisticRegressionModel:
        model = cls(
            learning_rate=data.get("learning_rate", 0.05),
            max_iter=data.get("max_iter", 300),
            l2_penalty=data.get("l2_penalty", 0.01),
        )
        model.weights = data.get("weights", [])
        model.intercept = data.get("intercept", 0.0)
        model.n_features = data.get("n_features", len(model.weights))
        return model


class SafetyMultiOutputLogisticRegression:
    """Independent LogisticRegression heads for the versioned safety endpoints."""

    def __init__(
        self,
        target_names: List[str],
        *,
        random_state: int = 42,
        max_iter: int = 500,
        C: float = 1.0,
    ) -> None:
        self.target_names = list(target_names)
        self.random_state = random_state
        self.max_iter = max_iter
        self.C = C
        self.estimators_: Dict[str, Any] = {}

    def fit(
        self,
        X: List[List[float]],
        target_values: Dict[str, List[float]],
    ) -> SafetyMultiOutputLogisticRegression:
        from sklearn.linear_model import LogisticRegression

        if not X:
            raise ValueError("Safety model training data cannot be empty.")
        for target_name in self.target_names:
            labels = target_values.get(target_name)
            if labels is None or len(labels) != len(X):
                raise ValueError(f"Safety labels are missing or misaligned for '{target_name}'.")
            if len(set(labels)) != 2:
                raise ValueError(f"Safety target '{target_name}' requires both classes for fitting.")
            estimator = LogisticRegression(
                solver="liblinear",
                random_state=self.random_state,
                max_iter=self.max_iter,
                C=self.C,
            )
            estimator.fit(X, labels)
            self.estimators_[target_name] = estimator
        return self

    def predict_proba(self, X: List[List[float]]) -> Dict[str, List[float]]:
        if not self.estimators_:
            raise ValueError("Safety multi-output model has not been fitted.")
        return {
            target_name: estimator.predict_proba(X)[:, 1].tolist()
            for target_name, estimator in self.estimators_.items()
        }


# ==============================================================================
# 2. Decision Tree & Random Forest Baseline
# ==============================================================================

class DecisionTreeNode:
    def __init__(
        self,
        feature_idx: Optional[int] = None,
        threshold: Optional[float] = None,
        left: Optional[DecisionTreeNode] = None,
        right: Optional[DecisionTreeNode] = None,
        value: Optional[float] = None,
    ) -> None:
        self.feature_idx = feature_idx
        self.threshold = threshold
        self.left = left
        self.right = right
        self.value = value  # Probability or average target

    @property
    def is_leaf(self) -> bool:
        return self.value is not None

    def to_dict(self) -> Dict[str, Any]:
        if self.is_leaf:
            return {"value": self.value}
        return {
            "feature_idx": self.feature_idx,
            "threshold": self.threshold,
            "left": self.left.to_dict() if self.left else None,
            "right": self.right.to_dict() if self.right else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> DecisionTreeNode:
        if "value" in d and d["value"] is not None:
            return cls(value=d["value"])
        return cls(
            feature_idx=d.get("feature_idx"),
            threshold=d.get("threshold"),
            left=cls.from_dict(d["left"]) if d.get("left") else None,
            right=cls.from_dict(d["right"]) if d.get("right") else None,
        )


class DecisionTreeModel:
    """Interpretable binary decision tree."""

    def __init__(self, max_depth: int = 4, min_samples_split: int = 2) -> None:
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.root: Optional[DecisionTreeNode] = None
        self.feature_importances_accum: Dict[int, float] = {}

    def fit(
        self,
        X: List[List[float]],
        y: List[float],
        feature_indices: Optional[List[int]] = None,
    ) -> DecisionTreeModel:
        self.feature_importances_accum = {}
        features = feature_indices or list(range(len(X[0])))
        self.root = self._build_tree(X, y, depth=0, feature_indices=features)
        return self

    def _gini(self, y: List[float]) -> float:
        if not y:
            return 0.0
        p = sum(y) / len(y)
        return 1.0 - (p**2 + (1.0 - p) ** 2)

    def _build_tree(
        self,
        X: List[List[float]],
        y: List[float],
        depth: int,
        feature_indices: List[int],
    ) -> DecisionTreeNode:
        n_samples = len(X)
        if (
            depth >= self.max_depth
            or n_samples < self.min_samples_split
            or len(set(y)) <= 1
        ):
            leaf_val = sum(y) / n_samples if n_samples > 0 else 0.5
            return DecisionTreeNode(value=leaf_val)

        best_gini_gain = 0.0
        best_feat = None
        best_thresh = None
        current_gini = self._gini(y)

        for feat_idx in feature_indices:
            values = sorted(set(x[feat_idx] for x in X))
            for i in range(len(values) - 1):
                thresh = (values[i] + values[i + 1]) / 2.0
                left_y = [y[idx] for idx in range(n_samples) if X[idx][feat_idx] <= thresh]
                right_y = [y[idx] for idx in range(n_samples) if X[idx][feat_idx] > thresh]

                if not left_y or not right_y:
                    continue

                p_left = len(left_y) / n_samples
                gini_split = p_left * self._gini(left_y) + (1.0 - p_left) * self._gini(right_y)
                gain = current_gini - gini_split

                if gain > best_gini_gain:
                    best_gini_gain = gain
                    best_feat = feat_idx
                    best_thresh = thresh

        if best_feat is None or best_thresh is None:
            return DecisionTreeNode(value=sum(y) / n_samples if n_samples > 0 else 0.5)

        # Track importance
        self.feature_importances_accum[best_feat] = (
            self.feature_importances_accum.get(best_feat, 0.0) + best_gini_gain
        )

        left_X = [x for x in X if x[best_feat] <= best_thresh]
        left_y = [y[i] for i, x in enumerate(X) if x[best_feat] <= best_thresh]
        right_X = [x for x in X if x[best_feat] > best_thresh]
        right_y = [y[i] for i, x in enumerate(X) if x[best_feat] > best_thresh]

        left_child = self._build_tree(left_X, left_y, depth + 1, feature_indices)
        right_child = self._build_tree(right_X, right_y, depth + 1, feature_indices)

        return DecisionTreeNode(
            feature_idx=best_feat,
            threshold=best_thresh,
            left=left_child,
            right=right_child,
        )

    def _predict_sample(self, node: DecisionTreeNode, x: List[float]) -> float:
        if node.is_leaf:
            return node.value or 0.5
        if node.feature_idx is not None and node.threshold is not None:
            if x[node.feature_idx] <= node.threshold:
                return self._predict_sample(node.left, x) if node.left else 0.5
            else:
                return self._predict_sample(node.right, x) if node.right else 0.5
        return node.value or 0.5

    def predict_proba(self, X: List[List[float]]) -> List[float]:
        if not self.root:
            return [0.5] * len(X)
        return [self._predict_sample(self.root, x) for x in X]


class RandomForestBaseline:
    """
    Random Forest ensemble combining bagged decision trees
    with random feature subspace selection.
    """

    def __init__(
        self,
        n_estimators: int = 10,
        max_depth: int = 3,
        min_samples_split: int = 2,
        seed: int = 42,
    ) -> None:
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.seed = seed
        self.trees: List[DecisionTreeModel] = []
        self.n_features: int = 0
        self.feature_importances_: Dict[int, float] = {}

    def fit(self, X: List[List[float]], y: List[float]) -> RandomForestBaseline:
        if not X or not y:
            raise ValueError("Training dataset cannot be empty.")
        n_samples = len(X)
        self.n_features = len(X[0])
        rng = random.Random(self.seed)

        # Subset size for features: sqrt(n_features) bounded
        subset_size = max(1, int(math.sqrt(self.n_features)))

        self.trees = []
        self.feature_importances_ = {i: 0.0 for i in range(self.n_features)}

        for _ in range(self.n_estimators):
            # Bootstrap sample
            boot_indices = [rng.randint(0, n_samples - 1) for _ in range(n_samples)]
            boot_X = [X[i] for i in boot_indices]
            boot_y = [y[i] for i in boot_indices]

            # Random feature selection
            feature_sub = rng.sample(range(self.n_features), subset_size)

            tree = DecisionTreeModel(
                max_depth=self.max_depth, min_samples_split=self.min_samples_split
            )
            tree.fit(boot_X, boot_y, feature_indices=feature_sub)
            self.trees.append(tree)

            for feat_idx, gain in tree.feature_importances_accum.items():
                self.feature_importances_[feat_idx] = (
                    self.feature_importances_.get(feat_idx, 0.0) + gain
                )

        return self

    def predict_proba(self, X: List[List[float]]) -> List[float]:
        if not self.trees:
            return [0.5] * len(X)
        all_tree_preds = [tree.predict_proba(X) for tree in self.trees]
        # Average probability across all trees
        return [
            sum(all_tree_preds[t][i] for t in range(len(self.trees))) / len(self.trees)
            for i in range(len(X))
        ]

    def predict(self, X: List[List[float]], threshold: float = 0.5) -> List[int]:
        return [1 if p >= threshold else 0 for p in self.predict_proba(X)]

    def get_feature_importances(self, feature_names: List[str]) -> Dict[str, float]:
        total = sum(self.feature_importances_.values()) or 1.0
        return {
            name: round(self.feature_importances_.get(i, 0.0) / total, 4)
            for i, name in enumerate(feature_names)
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_estimators": self.n_estimators,
            "max_depth": self.max_depth,
            "min_samples_split": self.min_samples_split,
            "seed": self.seed,
            "trees": [t.root.to_dict() if t.root else None for t in self.trees],
            "feature_importances": self.feature_importances_,
            "n_features": self.n_features,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RandomForestBaseline:
        rf = cls(
            n_estimators=data.get("n_estimators", 10),
            max_depth=data.get("max_depth", 3),
            min_samples_split=data.get("min_samples_split", 2),
            seed=data.get("seed", 42),
        )
        rf.n_features = data.get("n_features", 0)
        rf.feature_importances_ = {
            int(k): v for k, v in data.get("feature_importances", {}).items()
        }
        rf.trees = []
        for tree_dict in data.get("trees", []):
            t = DecisionTreeModel(max_depth=rf.max_depth, min_samples_split=rf.min_samples_split)
            if tree_dict:
                t.root = DecisionTreeNode.from_dict(tree_dict)
            rf.trees.append(t)
        return rf


# ==============================================================================
# 3. Gradient Boosting Baseline
# ==============================================================================

class RegressionStump:
    """Single-split decision stump for fitting gradient residuals."""

    def __init__(self) -> None:
        self.feature_idx: Optional[int] = None
        self.threshold: Optional[float] = None
        self.left_value: float = 0.0
        self.right_value: float = 0.0
        self.gain: float = 0.0

    def fit(self, X: List[List[float]], residuals: List[float]) -> RegressionStump:
        n_samples = len(X)
        best_sse = float("inf")
        total_var = sum(r**2 for r in residuals)

        for feat_idx in range(len(X[0])):
            values = sorted(set(x[feat_idx] for x in X))
            for i in range(len(values) - 1):
                thresh = (values[i] + values[i + 1]) / 2.0
                left_r = [residuals[idx] for idx in range(n_samples) if X[idx][feat_idx] <= thresh]
                right_r = [residuals[idx] for idx in range(n_samples) if X[idx][feat_idx] > thresh]

                if not left_r or not right_r:
                    continue

                left_mean = sum(left_r) / len(left_r)
                right_mean = sum(right_r) / len(right_r)

                sse = sum((r - left_mean) ** 2 for r in left_r) + sum((r - right_mean) ** 2 for r in right_r)

                if sse < best_sse:
                    best_sse = sse
                    self.feature_idx = feat_idx
                    self.threshold = thresh
                    self.left_value = left_mean
                    self.right_value = right_mean
                    self.gain = max(0.0, total_var - sse)

        if self.feature_idx is None:
            self.left_value = sum(residuals) / n_samples if n_samples > 0 else 0.0
            self.right_value = self.left_value

        return self

    def predict_one(self, x: List[float]) -> float:
        if self.feature_idx is None or self.threshold is None:
            return self.left_value
        return self.left_value if x[self.feature_idx] <= self.threshold else self.right_value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_idx": self.feature_idx,
            "threshold": self.threshold,
            "left_value": self.left_value,
            "right_value": self.right_value,
            "gain": self.gain,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> RegressionStump:
        stump = cls()
        stump.feature_idx = d.get("feature_idx")
        stump.threshold = d.get("threshold")
        stump.left_value = d.get("left_value", 0.0)
        stump.right_value = d.get("right_value", 0.0)
        stump.gain = d.get("gain", 0.0)
        return stump


class GradientBoostingBaseline:
    """
    Sequential Gradient Boosted Decision Stumps for interpretable
    additive classification.
    """

    def __init__(
        self,
        n_estimators: int = 15,
        learning_rate: float = 0.1,
    ) -> None:
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.base_log_odds: float = 0.0
        self.stumps: List[RegressionStump] = []
        self.feature_importances_: Dict[int, float] = {}

    def fit(self, X: List[List[float]], y: List[float]) -> GradientBoostingBaseline:
        if not X or not y:
            raise ValueError("Training dataset cannot be empty.")
        n_samples = len(X)
        n_features = len(X[0])

        # Prior log odds: log(p / (1 - p))
        p_prior = sum(y) / n_samples
        p_prior = min(max(p_prior, 0.05), 0.95)
        self.base_log_odds = math.log(p_prior / (1.0 - p_prior))

        # Current log odds for all samples
        current_logits = [self.base_log_odds] * n_samples
        self.stumps = []
        self.feature_importances_ = {i: 0.0 for i in range(n_features)}

        for _ in range(self.n_estimators):
            # Compute current probabilities & negative gradient (pseudo-residuals)
            probs = [_sigmoid(logit) for logit in current_logits]
            residuals = [target - p for target, p in zip(y, probs)]

            stump = RegressionStump()
            stump.fit(X, residuals)
            self.stumps.append(stump)

            if stump.feature_idx is not None:
                self.feature_importances_[stump.feature_idx] = (
                    self.feature_importances_.get(stump.feature_idx, 0.0) + stump.gain
                )

            # Update sample logits with learning rate shrinkage
            for i in range(n_samples):
                current_logits[i] += self.learning_rate * stump.predict_one(X[i])

        return self

    def predict_proba(self, X: List[List[float]]) -> List[float]:
        results: List[float] = []
        for x in X:
            logit = self.base_log_odds
            for stump in self.stumps:
                logit += self.learning_rate * stump.predict_one(x)
            results.append(_sigmoid(logit))
        return results

    def predict(self, X: List[List[float]], threshold: float = 0.5) -> List[int]:
        return [1 if p >= threshold else 0 for p in self.predict_proba(X)]

    def get_feature_importances(self, feature_names: List[str]) -> Dict[str, float]:
        total = sum(self.feature_importances_.values()) or 1.0
        return {
            name: round(self.feature_importances_.get(i, 0.0) / total, 4)
            for i, name in enumerate(feature_names)
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_estimators": self.n_estimators,
            "learning_rate": self.learning_rate,
            "base_log_odds": self.base_log_odds,
            "stumps": [s.to_dict() for s in self.stumps],
            "feature_importances": self.feature_importances_,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GradientBoostingBaseline:
        gb = cls(
            n_estimators=data.get("n_estimators", 15),
            learning_rate=data.get("learning_rate", 0.1),
        )
        gb.base_log_odds = data.get("base_log_odds", 0.0)
        gb.feature_importances_ = {
            int(k): v for k, v in data.get("feature_importances", {}).items()
        }
        gb.stumps = [RegressionStump.from_dict(d) for d in data.get("stumps", [])]
        return gb
