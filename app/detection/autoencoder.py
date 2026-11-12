"""Optional autoencoder comparison model (FR-19).

Requires torch (see requirements-optional.txt). Degrades gracefully when absent.
"""
from __future__ import annotations

import numpy as np


def is_available() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def train_autoencoder(X_train: np.ndarray, seed: int = 42, hidden: int = 12,
                      epochs: int = 60, lr: float = 1e-3) -> dict:
    import torch
    from sklearn.preprocessing import StandardScaler

    torch.manual_seed(seed)
    scaler = StandardScaler().fit(X_train)
    Xs = scaler.transform(X_train).astype("float32")
    d = Xs.shape[1]

    model = torch.nn.Sequential(
        torch.nn.Linear(d, hidden),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden, d),
    )
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = torch.nn.MSELoss()
    t = torch.from_numpy(Xs)
    for _ in range(epochs):
        opt.zero_grad()
        loss = loss_fn(model(t), t)
        loss.backward()
        opt.step()
    return {"model": model, "scaler": scaler, "seed": seed,
            "hidden": hidden, "epochs": epochs, "final_loss": float(loss.item())}


def reconstruction_errors(ae: dict, X: np.ndarray) -> np.ndarray:
    import torch
    Xs = ae["scaler"].transform(X).astype("float32")
    with torch.no_grad():
        recon = ae["model"](torch.from_numpy(Xs)).numpy()
    return ((Xs - recon) ** 2).mean(axis=1)