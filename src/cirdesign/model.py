"""Transparent per-use LCA, cost and circularity model for one aluminium booth panel.

Functional unit: ONE USE of one panel at ONE exhibition event ("per use").
All burdens of a panel's life are spread over the number of events it expected to serve:
    per use = (production + sum of per-event burdens + end-of-life) / expected uses.
Single-use routes (recycling, disposal) serve exactly one event. Reuse routes (direct reuse,
repair, reprocessing) serve up to N events, reduced by loss probability.

Inputs come from data/*.csv. Defaults are literature or database values where available and
flagged assumptions otherwise (see data/literature_sources.csv).
"""
from __future__ import annotations

from functools import lru_cache

from .data import central_params, load_all

DEFAULT_CONTEXT = dict(design="B", strategy="reuse", business_model="rental", n_uses=6,
                       event_km=400.0, eol_km=100.0, credit="net_scrap")
CREDITS = ("net_scrap", "cut_off")


@lru_cache(maxsize=1)
def _tables():
    return load_all()


@lru_cache(maxsize=1)
def _central():
    return central_params(_tables())


def expected_uses(n_planned: float, p_loss: float) -> float:
    """E[uses] = sum_{k=0..N-1} (1-p)^k : a panel must survive k events to serve event k+1."""
    n = max(int(round(n_planned)), 1)
    if p_loss <= 1e-12:
        return float(n)
    return (1 - (1 - p_loss) ** n) / p_loss


def _credit_mass(m, yield_, rc, credit):
    return 0.0 if credit == "cut_off" else m * max(yield_ - rc, 0.0)


def evaluate(ctx: dict | None = None, params: dict | None = None) -> dict:
    """Return all KPIs and the burden breakdown for one decision context."""
    c = {**DEFAULT_CONTEXT, **(ctx or {})}
    P = {**_central(), **(params or {})}
    T = _tables()
    d, st, bm = T["designs"].loc[c["design"]], T["strategies"].loc[c["strategy"]], T["business_models"].loc[c["business_model"]]
    if c["credit"] not in CREDITS:
        raise ValueError(f"credit must be one of {CREDITS}")

    m, rc = float(d.mass_kg), P["recycled_content"]
    ef_mix = (1 - rc) * P["ef_primary"] + rc * P["ef_secondary"]
    leg_ef = P["transport_ef"] / P["transport_load_factor"]

    def leg(km):
        return m / 1000 * km * leg_ef

    def leg_cost(km):
        return m / 1000 * km * P["transport_cost"]

    price_kg = P["lme_price_usd_t"] * P["usd_eur"] / 1000
    production = m * ef_mix + m * P["e_fab"] * float(d.fab_factor) * P["grid_ef"]
    panel_cost = m * (price_kg + P["manuf_cost"] * float(d.cost_factor))
    recov_yield = P["collection_rate"] * P["melt_yield"]
    delta = P["ef_primary"] - P["ef_secondary"]
    grid = P["grid_ef"]

    single = st.family == "single"
    if single:
        U, N = 1.0, 1
        p_loss = 1.0
        per_event = leg(c["event_km"])
        per_event_cost = leg_cost(c["event_km"]) + P["handling_cost"]
        repair_events = 0.0
        if c["strategy"] == "recycling":
            y = recov_yield
            eol = leg(c["eol_km"]) + m * P["sort_energy"] * grid
            credit = _credit_mass(m, y, rc, c["credit"]) * delta
            eol_cost = leg_cost(c["eol_km"]) - m * y * price_kg * P["scrap_price_ratio"]
        else:
            y = P["disposal_recovery"]
            eol = leg(c["eol_km"]) + m * P["disposal_ef"]
            credit = _credit_mass(m, y, rc, c["credit"]) * delta
            eol_cost = leg_cost(c["eol_km"]) + m * P["gate_fee"]
    else:
        N = min(int(round(c["n_uses"])), int(d.technical_lifetime_events))
        dmg = P["damage_rate"] * float(d.damage_mult) * float(bm.damage_mult) * float(st.damage_factor)
        loss_dmg = dmg * (1 - float(d.repairability)) if st.repair else dmg
        p_loss = 1 - (1 - loss_dmg) * float(bm.redeploy)
        U = expected_uses(N, p_loss)
        repair_events = dmg * float(d.repairability) if st.repair else 0.0
        clean = m * P["e_clean"] * grid
        maint = m * P["e_reprocess"] * grid * float(st.reprocess)
        repair = repair_events * (m * P["e_repair"] * grid + m * P["repair_share"] * ef_mix)
        per_event = 2 * leg(c["event_km"]) + clean + maint + repair
        labour = float(st.labour_h) * P["labour_rate"] * (repair_events if st.repair else 1.0)
        if st.repair:
            labour += 0.05 * P["labour_rate"]
        repair_mat_cost = repair_events * P["repair_share"] * m * (price_kg + P["manuf_cost"] * float(d.cost_factor))
        per_event_cost = (2 * leg_cost(c["event_km"]) + P["handling_cost"] + P["storage_cost"] + labour + repair_mat_cost)
        y = recov_yield
        eol = leg(c["eol_km"]) + m * P["sort_energy"] * grid
        credit = _credit_mass(m, y, rc, c["credit"]) * delta
        eol_cost = leg_cost(c["eol_km"]) - m * y * price_kg * P["scrap_price_ratio"]

    total = production + U * per_event + eol - credit
    total_cost = panel_cost + U * per_event_cost + eol_cost
    virgin_net = max(m * (1 - rc) - _credit_mass(m, y, rc, c["credit"]), 0.0)

    # Circularity: simplified Material Circularity Indicator (Ellen MacArthur Foundation, 2015)
    V, W = m * (1 - rc), m * (1 - y)
    lfi = (V + W) / (2 * m)
    mci = max(0.0, 1 - lfi * 0.9 / max(U, 1.0))

    # Feasibility: base score x design suitability x distance penalty x organisational reliability
    suit = 1.0 if single else (0.5 + 0.5 * float(d.repairability) if st.repair else 0.5 + 0.5 * float(d.disassembly))
    dist = max(0.0, 1 - c["event_km"] / 2000)
    org = 1.0 if single else 0.6 + 0.4 * float(bm.redeploy)
    feas = float(st.feasibility_base) * suit * dist * org

    return {
        "context": c, "expected_uses": U, "reuse_cycles": U - 1, "p_loss": p_loss, "planned_uses": N,
        "climate_per_use": total / U, "cost_per_use": total_cost / U * (1 + float(bm.margin)),
        "circularity": mci, "material_recovery": y, "virgin_al_per_use": virgin_net / U,
        "feasibility": feas,
        "breakdown_per_use": {"Panel production": production / U, "Transport (events)": U * (2 if not single else 1) * leg(c["event_km"]) / U,
                              "Cleaning and repair": (per_event - (2 if not single else 1) * leg(c["event_km"])) * U / U,
                              "End-of-life processes": eol / U, "Recycling credit": -credit / U},
        "mass_kg": m,
    }


def evaluate_all(ctx: dict | None = None, params: dict | None = None):
    """Evaluate every strategy for the given context. Returns a DataFrame indexed by strategy."""
    import pandas as pd
    T = _tables()
    rows = {}
    for s in T["strategies"].index:
        r = evaluate({**(ctx or {}), "strategy": s}, params)
        rows[s] = {k: r[k] for k in ("expected_uses", "reuse_cycles", "climate_per_use", "cost_per_use", "circularity",
                                      "material_recovery", "virgin_al_per_use", "feasibility")}
    return pd.DataFrame(rows).T
