"""Preprocessing: imputation + robust scaling, persisted with the model artifact."""
from __future__ import annotations

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import RobustScaler


def fit_preprocessor(X_train: np.ndarray) -> dict:
    imputer = SimpleImputer(strategy="median")
    scaler = RobustScaler()
    X1 = imputer.fit_transform(X_train)
    scaler.fit(X1)
    return {"imputer": imputer, "scaler": scaler}


def transform(pre: dict, X: np.ndarray) -> np.ndarray:
    return pre["scaler"].transform(pre["imputer"].transform(X))