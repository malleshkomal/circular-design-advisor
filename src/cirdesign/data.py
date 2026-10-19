"""Load the four CSV files. Everything numeric in the model comes from here."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[2] / "data"


def load_all(data_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    d = Path(data_dir) if data_dir else DATA
    out = {
        "sources": pd.read_csv(d / "literature_sources.csv"),
        "designs": pd.read_csv(d / "product_data.csv").set_index("design"),
        "business_models": pd.read_csv(d / "business_models.csv").set_index("name"),
        "strategies": pd.read_csv(d / "strategies.csv").set_index("strategy"),
    }
    src = out["sources"]
    if src["id"].duplicated().any():
        raise ValueError("duplicate parameter ids in literature_sources.csv")
    return out


def central_params(tables: dict | None = None) -> dict[str, float]:
    """Parameters used by the model (central values)."""
    src = (tables or load_all())["sources"]
    used = src[src["used_in_model"]]
    return {r.id: float(r.value) for r in used.itertuples()}


def param_ranges(tables: dict | None = None) -> dict[str, tuple[float, float, float]]:
    """(low, mode, high) for every parameter that has a range."""
    src = (tables or load_all())["sources"]
    out = {}
    for r in src[src["used_in_model"]].itertuples():
        if pd.notna(r.low) and pd.notna(r.high) and r.low != r.high:
            out[r.id] = (float(r.low), float(r.value), float(r.high))
    return out
