"""Recommendation engine: transparent rules plus a weighted multi-criteria score, with explanations."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .data import load_all
from .model import evaluate, evaluate_all

WEIGHTS = {"environment": 0.50, "circularity": 0.25, "economics": 0.15, "feasibility": 0.10}
LABELS = {"reuse": "Direct reuse", "repair": "Repair and reuse", "reprocessing": "Reprocessing",
          "recycling": "Recycling", "disposal": "Disposal"}


@dataclass
class Recommendation:
    strategy: str
    score_table: pd.DataFrame
    rule_strategy: str
    rule_trace: list
    reasons: list
    warnings: list = field(default_factory=list)

    @property
    def label(self):
        return LABELS[self.strategy]


def _norm(s, higher_better):
    span = s.max() - s.min()
    if span < 1e-12:
        return pd.Series(0.5, index=s.index)
    z = (s - s.min()) / span
    return z if higher_better else 1 - z


def score_strategies(ctx=None, params=None, weights=None) -> pd.DataFrame:
    """Weighted recommendation score (0-1) per strategy, scaled across the five strategies."""
    w = weights or WEIGHTS
    t = evaluate_all(ctx, params)
    out = pd.DataFrame(index=t.index)
    out["environment"] = _norm(t.climate_per_use, False)
    out["circularity"] = t.circularity.clip(0, 1)
    out["economics"] = _norm(t.cost_per_use, False)
    out["feasibility"] = t.feasibility.clip(0, 1)
    tot = sum(w.values())
    out["score"] = sum(out[k] * v for k, v in w.items()) / tot
    return out.join(t[["climate_per_use", "cost_per_use", "expected_uses", "reuse_cycles"]])


def rule_based(ctx, table) -> tuple[str, list]:
    """Ordered, readable rules (thresholds follow the project brief)."""
    T = load_all()
    c = {"design": "B", "event_km": 400.0, **(ctx or {})}
    rep = float(T["designs"].loc[c["design"], "repairability"])
    reuse_best = table.loc[["reuse", "repair", "reprocessing"], "score"].idxmax()
    trace = []
    tests = [("R1", "Expected reuse cycles >= 3", table.loc[reuse_best, "reuse_cycles"], 3.0, table.loc[reuse_best, "reuse_cycles"] >= 3),
             ("R2", "Repairability >= 0.70", rep, 0.70, rep >= 0.70),
             ("R3", "Event transport distance <= 300 km", c["event_km"], 300.0, c["event_km"] <= 300)]
    for rid, txt, v, th, ok in tests:
        trace.append({"rule": rid, "test": txt, "value": float(v), "threshold": th, "pass": bool(ok)})
    if all(t["pass"] for t in trace):
        return reuse_best, trace
    # relaxed reuse: climate clearly better than recycling and expected cycles >= 1.5
    gain = 1 - table.loc[reuse_best, "climate_per_use"] / table.loc["recycling", "climate_per_use"]
    ok = table.loc[reuse_best, "reuse_cycles"] >= 1.5 and gain >= 0.15
    trace.append({"rule": "R4", "test": "Fallback: reuse still >= 15 % lower climate impact than recycling and >= 1.5 cycles",
                  "value": float(gain), "threshold": 0.15, "pass": bool(ok)})
    if ok:
        return reuse_best, trace
    return ("recycling" if table.loc["recycling", "climate_per_use"] < table.loc["disposal", "climate_per_use"] else "disposal"), trace


def recommend(ctx=None, params=None, weights=None) -> Recommendation:
    table = score_strategies(ctx, params, weights)
    best = table.score.idxmax()
    rule, trace = rule_based(ctx, table)
    r = table.loc[best]
    rec = table.loc["recycling"]
    reasons = [f"{LABELS[best]} has the highest weighted score ({r.score:.2f}).",
               f"Climate impact is {r.climate_per_use:.1f} kg CO2e per use, against {rec.climate_per_use:.1f} for recycling.",
               f"Cost per use is {r.cost_per_use:.0f} EUR, against {rec.cost_per_use:.0f} EUR for recycling."]
    if r.expected_uses > 1.05:
        reasons.append(f"It serves {r.expected_uses:.1f} events per panel on average ({r.reuse_cycles:.1f} reuse cycles).")
    warns = []
    if rule != best:
        warns.append(f"The transparent rules point to {LABELS[rule]}, the weighted score to {LABELS[best]}: the two methods weigh trade-offs differently.")
    if r.get("climate_per_use", 0) > 0 and table.score.nlargest(2).diff().abs().iloc[-1] < 0.03:
        warns.append("The top two options are within 0.03 score points: treat the ranking as unclear.")
    return Recommendation(best, table, rule, trace, reasons, warns)
