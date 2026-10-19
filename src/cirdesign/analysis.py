"""Simulation, uncertainty, sensitivity, Pareto and optimisation on top of model.evaluate."""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from .data import load_all, param_ranges
from .model import DEFAULT_CONTEXT, evaluate, evaluate_all

REUSE_FAMILY = ["reuse", "repair", "reprocessing"]
KPI_COLS = ["climate_per_use", "cost_per_use", "circularity", "material_recovery", "virgin_al_per_use",
            "feasibility", "expected_uses"]


def _T():
    return load_all()


# ------------------------------------------------------------------ simulation grid
def simulate_grid(n_range=range(1, 16), km_values=(50, 150, 300, 500, 700, 900), designs=None,
                  business_models=None, credit="net_scrap", params=None) -> pd.DataFrame:
    """Full factorial scenario grid: design x strategy x business model x planned uses x event distance."""
    T = _T()
    designs = designs or list(T["designs"].index)
    bms = business_models or list(T["business_models"].index)
    rows = []
    for d, s, b, km in itertools.product(designs, T["strategies"].index, bms, km_values):
        single = T["strategies"].loc[s, "family"] == "single"
        for n in ([1] if single else n_range):
            r = evaluate(dict(design=d, strategy=s, business_model=b, n_uses=n, event_km=km, credit=credit), params)
            rows.append({"design": d, "strategy": s, "business_model": b, "n_uses": n, "event_km": km,
                         **{k: r[k] for k in KPI_COLS}})
    return pd.DataFrame(rows)


def uses_sweep(ctx=None, n_max=15, params=None) -> pd.DataFrame:
    rows = []
    for n in range(1, n_max + 1):
        t = evaluate_all({**(ctx or {}), "n_uses": n}, params)
        t["n_uses"] = n
        t["strategy"] = t.index
        rows.append(t)
    return pd.concat(rows, ignore_index=True)


def distance_sweep(ctx=None, km_values=range(0, 1501, 50), params=None) -> pd.DataFrame:
    rows = []
    for km in km_values:
        t = evaluate_all({**(ctx or {}), "event_km": km}, params)
        t["event_km"] = km
        t["strategy"] = t.index
        rows.append(t)
    return pd.concat(rows, ignore_index=True)


def break_even_uses(ctx=None, params=None, family_strategy="reuse", n_max=40):
    """Smallest planned number of uses at which the chosen reuse strategy has lower climate impact per use than recycling."""
    for n in range(1, n_max + 1):
        t = evaluate_all({**(ctx or {}), "n_uses": n}, params)
        if t.loc[family_strategy, "climate_per_use"] < t.loc["recycling", "climate_per_use"] - 1e-9:
            return n
    return None


def break_even_distance(ctx=None, params=None, family_strategy="reuse", km_max=5000, step=50):
    """Event distance (km) above which recycling beats the chosen reuse strategy on climate; None if it never does within km_max."""
    prev = None
    for km in range(0, km_max + 1, step):
        t = evaluate_all({**(ctx or {}), "event_km": km}, params)
        better = t.loc[family_strategy, "climate_per_use"] < t.loc["recycling", "climate_per_use"]
        if prev is True and not better:
            return km
        prev = better
    return None


# ------------------------------------------------------------------ regime maps
def regime_map(ctx, x_name, xs, y_name, ys, params=None, metric="climate_per_use") -> pd.DataFrame:
    """Best strategy (by `metric`, lower is better) on a 2-D grid. x/y can be context keys or parameter ids."""
    ctx = {**DEFAULT_CONTEXT, **(ctx or {})}
    names = list(_T()["strategies"].index)
    code = pd.DataFrame(index=ys, columns=xs, dtype=object)
    for yv in ys:
        for xv in xs:
            c, p = dict(ctx), dict(params or {})
            for nm, v in ((x_name, xv), (y_name, yv)):
                (c if nm in c else p)[nm] = v
            t = evaluate_all(c, p)
            code.loc[yv, xv] = t[metric].idxmin()
    return code


def gap_map(ctx, x_name, xs, y_name, ys, params=None) -> pd.DataFrame:
    """Percent change in climate impact per use of the best reuse route versus recycling (negative = reuse better)."""
    ctx = {**DEFAULT_CONTEXT, **(ctx or {})}
    out = pd.DataFrame(index=ys, columns=xs, dtype=float)
    for yv in ys:
        for xv in xs:
            c, p = dict(ctx), dict(params or {})
            for nm, v in ((x_name, xv), (y_name, yv)):
                (c if nm in c else p)[nm] = v
            t = evaluate_all(c, p)["climate_per_use"]
            out.loc[yv, xv] = (t[REUSE_FAMILY].min() / t["recycling"] - 1) * 100
    return out


# ------------------------------------------------------------------ uncertainty
def monte_carlo(ctx=None, n=1500, seed=42, strategies=("reuse", "repair", "recycling", "disposal")) -> pd.DataFrame:
    """Sample every ranged parameter from a triangular(low, mode, high) distribution and re-evaluate."""
    rng = np.random.default_rng(seed)
    ranges = param_ranges()
    draws = {k: rng.triangular(lo, mo, hi, n) for k, (lo, mo, hi) in ranges.items()}
    rows = []
    for i in range(n):
        p = {k: float(v[i]) for k, v in draws.items()}
        row = {}
        for s in strategies:
            r = evaluate({**(ctx or {}), "strategy": s}, p)
            row[s] = r["climate_per_use"]
            row[f"{s}_cost"] = r["cost_per_use"]
        rows.append(row)
    df = pd.DataFrame(rows)
    for k in ("ef_primary", "damage_rate", "transport_ef", "grid_ef"):
        df[f"p_{k}"] = draws[k]
    return df


def tornado(ctx=None, strategy="reuse", reference="recycling") -> pd.DataFrame:
    """One-at-a-time effect of each parameter's low/high on (strategy - reference) climate per use."""
    base = evaluate_all(ctx)["climate_per_use"]
    base_gap = base[strategy] - base[reference]
    rows = []
    for k, (lo, mo, hi) in param_ranges().items():
        gaps = []
        for v in (lo, hi):
            t = evaluate_all(ctx, {k: v})["climate_per_use"]
            gaps.append(t[strategy] - t[reference])
        rows.append({"parameter": k, "low_gap": gaps[0], "high_gap": gaps[1], "base_gap": base_gap,
                     "swing": abs(gaps[1] - gaps[0])})
    return pd.DataFrame(rows).sort_values("swing", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------ Pareto and optimisation
def pareto_front(df: pd.DataFrame, cols=("climate_per_use", "cost_per_use", "infeasibility")) -> pd.DataFrame:
    """Non-dominated rows (minimise every column). infeasibility = 1 - feasibility."""
    df = df.assign(infeasibility=1 - df.feasibility)
    vals = df[list(cols)].to_numpy()
    keep = np.ones(len(df), bool)
    for i in range(len(df)):
        if keep[i]:
            dom = np.all(vals <= vals[i], axis=1) & np.any(vals < vals[i], axis=1)
            if dom.any():
                keep[i] = False
    return df[keep]


def optimise(grid: pd.DataFrame, w_clim=0.50, w_cost=0.25, w_circ=0.25, top=10) -> pd.DataFrame:
    """Exhaustive search of the discrete decision space for the lowest weighted objective:
    objective = w_clim * normalised climate + w_cost * normalised cost - w_circ * circularity."""
    g = grid.copy()
    nz = lambda s: (s - s.min()) / (s.max() - s.min() + 1e-12)
    g["objective"] = w_clim * nz(g.climate_per_use) + w_cost * nz(g.cost_per_use) - w_circ * g.circularity
    # keep the best planned-use / distance setting of every design x strategy x business-model combination
    g = g.sort_values("objective").drop_duplicates(["design", "strategy", "business_model"])
    return g.head(top).reset_index(drop=True)
