"""Machine-learning screening models trained on simulated scenarios.

The models learn the physics-based model in model.py; they do not add new knowledge.
They are fast surrogates for screening and for explaining which inputs matter.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import qmc
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from .data import load_all, param_ranges
from .model import evaluate_all

PARAMS = ["ef_primary", "grid_ef", "damage_rate", "transport_ef", "collection_rate", "e_fab", "transport_load_factor"]
FEATURES = ["n_uses", "event_km", "repairability", "mass_kg", "redeploy", "is_reuse", "is_repair", "is_reprocessing",
            "is_recycling"] + PARAMS
NICE = {"n_uses": "Planned uses", "event_km": "Event distance", "repairability": "Repairability", "mass_kg": "Panel mass",
        "redeploy": "Redeployment probability", "is_reuse": "Strategy: direct reuse", "is_repair": "Strategy: repair",
        "is_reprocessing": "Strategy: reprocessing", "is_recycling": "Strategy: recycling",
        "ef_primary": "Primary Al footprint", "grid_ef": "Electricity mix", "damage_rate": "Damage rate",
        "transport_ef": "Freight emission factor", "collection_rate": "Collection rate", "e_fab": "Fabrication energy",
        "transport_load_factor": "Truck load factor"}


def build_dataset(n_contexts=2500, seed=7) -> pd.DataFrame:
    T = load_all()
    rng = np.random.default_rng(seed)
    rngs = param_ranges(T)
    sampler = qmc.LatinHypercube(d=len(PARAMS) + 2, seed=seed)
    u = sampler.random(n_contexts)
    designs, bms = list(T["designs"].index), list(T["business_models"].index)
    rows = []
    for i in range(n_contexts):
        p = {k: rngs[k][0] + u[i, j] * (rngs[k][2] - rngs[k][0]) for j, k in enumerate(PARAMS)}
        n = int(1 + u[i, len(PARAMS)] * 19)
        km = float(20 + u[i, len(PARAMS) + 1] * 1480)
        d, b = designs[rng.integers(len(designs))], bms[rng.integers(len(bms))]
        tab = evaluate_all(dict(design=d, business_model=b, n_uses=n, event_km=km), p)
        reuse_best = tab.loc[["reuse", "repair", "reprocessing"], "climate_per_use"].min()
        reuse_wins = int(reuse_best < tab.loc["recycling", "climate_per_use"])
        for s in tab.index:
            rows.append({"context": i, "design": d, "business_model": b, "strategy": s, "n_uses": n, "event_km": km,
                         "repairability": float(T["designs"].loc[d, "repairability"]), "mass_kg": float(T["designs"].loc[d, "mass_kg"]),
                         "redeploy": float(T["business_models"].loc[b, "redeploy"]), **p,
                         "is_reuse": int(s == "reuse"), "is_repair": int(s == "repair"), "is_reprocessing": int(s == "reprocessing"),
                         "is_recycling": int(s == "recycling"), "climate_per_use": tab.loc[s, "climate_per_use"],
                         "cost_per_use": tab.loc[s, "cost_per_use"], "reuse_wins": reuse_wins})
    return pd.DataFrame(rows)


def train(n_contexts=2500, seed=7) -> dict:
    df = build_dataset(n_contexts, seed)
    ctx_ids = df.context.unique()
    tr_ids, te_ids = train_test_split(ctx_ids, test_size=0.2, random_state=seed)   # split by scenario, not by row
    tr, te = df[df.context.isin(tr_ids)], df[df.context.isin(te_ids)]
    reg = RandomForestRegressor(n_estimators=200, random_state=seed, n_jobs=-1, min_samples_leaf=2).fit(tr[FEATURES], tr.climate_per_use)
    pred = reg.predict(te[FEATURES])
    # classifier: one row per context (reuse-family vs recycling)
    ctx_df = df.groupby("context").first().reset_index()
    ctr, cte = ctx_df[ctx_df.context.isin(tr_ids)], ctx_df[ctx_df.context.isin(te_ids)]
    clf_feats = [f for f in FEATURES if not f.startswith("is_")]
    clf = RandomForestClassifier(n_estimators=200, random_state=seed, n_jobs=-1, min_samples_leaf=2).fit(ctr[clf_feats], ctr.reuse_wins)
    pi = permutation_importance(reg, te[FEATURES], te.climate_per_use, n_repeats=5, random_state=seed, n_jobs=-1)
    imp = pd.DataFrame({"feature": FEATURES, "importance": pi.importances_mean}).sort_values("importance", ascending=False)
    imp["label"] = imp.feature.map(NICE)
    pic = permutation_importance(clf, cte[clf_feats], cte.reuse_wins, n_repeats=5, random_state=seed, n_jobs=-1)
    imp_c = pd.DataFrame({"feature": clf_feats, "importance": pic.importances_mean}).sort_values("importance", ascending=False)
    imp_c["label"] = imp_c.feature.map(NICE)
    return {"regressor": reg, "classifier": clf, "features": FEATURES, "clf_features": clf_feats,
            "metrics": {"r2": float(r2_score(te.climate_per_use, pred)), "mae": float(mean_absolute_error(te.climate_per_use, pred)),
                        "clf_accuracy": float(accuracy_score(cte.reuse_wins, clf.predict(cte[clf_feats]))),
                        "reuse_win_share_test": float(cte.reuse_wins.mean()), "n_train_rows": int(len(tr)), "n_test_rows": int(len(te))},
            "parity": pd.DataFrame({"actual": te.climate_per_use.to_numpy(), "predicted": pred, "strategy": te.strategy.to_numpy()}),
            "importance": imp, "importance_clf": imp_c}


def predict_reuse_probability(model: dict, ctx: dict, params: dict | None = None) -> float:
    T = load_all()
    from .data import central_params
    p = {**central_params(T), **(params or {})}
    d = ctx.get("design", "B"); b = ctx.get("business_model", "rental")
    row = {"n_uses": ctx.get("n_uses", 6), "event_km": ctx.get("event_km", 400.0),
           "repairability": float(T["designs"].loc[d, "repairability"]), "mass_kg": float(T["designs"].loc[d, "mass_kg"]),
           "redeploy": float(T["business_models"].loc[b, "redeploy"]), **{k: p[k] for k in PARAMS}}
    x = pd.DataFrame([row])[model["clf_features"]]
    proba = model["classifier"].predict_proba(x)[0]
    return float(proba[list(model["classifier"].classes_).index(1)]) if 1 in model["classifier"].classes_ else 0.0
