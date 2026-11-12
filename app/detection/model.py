"""Isolation Forest training and raw scoring."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest


def train_isolation_forest(X_train: np.ndarray, seed: int, n_estimators: int,
                           contamination: float) -> IsolationForest:
    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination if X_train.shape[0] >= 50 else "auto",
        random_state=seed,
        n_jobs=1,
    )
    model.fit(X_train)
    return model


def raw_scores(model: IsolationForest, X: np.ndarray) -> np.ndarray:
    """Higher = more anomalous (negated sklearn score_samples)."""
    return -model.score_samples(X)