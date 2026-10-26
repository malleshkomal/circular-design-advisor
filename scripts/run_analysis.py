"""Reproduce every table, the ML model and the static animated report:  python run_analysis.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import joblib
import pandas as pd
import plotly.io as pio

from cirdesign import viz
from cirdesign.analysis import (break_even_distance, break_even_uses, distance_sweep, gap_map, monte_carlo, optimise,
                                pareto_front, simulate_grid, tornado, uses_sweep)
from cirdesign.data import load_all
from cirdesign.ml import predict_reuse_probability, train
from cirdesign.model import evaluate, evaluate_all
from cirdesign.recommend import recommend, score_strategies

R = ROOT / "results"
R.mkdir(exist_ok=True)


def main():
    T = load_all()
    ctx = dict(design="B", business_model="rental", n_uses=6, event_km=400.0, eol_km=100.0, credit="net_scrap")
    base = evaluate_all(ctx)
    base.to_csv(R / "baseline_kpis.csv")
    rec = recommend(ctx)
    rec.score_table.to_csv(R / "baseline_scores.csv")
    grid = simulate_grid()
    grid.to_csv(R / "scenario_grid.csv", index=False)
    mc = monte_carlo(ctx, n=1500)
    stress = dict(design="C", business_model="sale", n_uses=2, event_km=1200.0, eol_km=100.0, credit="net_scrap")
    mcs = monte_carlo(stress, n=1500)
    tor = tornado(ctx)
    tor.to_csv(R / "tornado.csv", index=False)
    ml = train(2500)
    joblib.dump(ml, R / "ml_model.joblib")
    ml["importance"].to_csv(R / "ml_importance.csv", index=False)
    g = grid[(grid.event_km <= 500) & (grid.n_uses <= 8)]
    opt = optimise(g)
    opt.to_csv(R / "optimiser_top10.csv", index=False)
    pf = pareto_front(g)
    cut = evaluate_all({**ctx, "credit": "cut_off"})
    names = dict(zip(T["sources"].id, T["sources"].parameter))
    used = T["sources"][T["sources"].used_in_model]
    val = {n: float(evaluate_all({**ctx, "n_uses": n}).loc[["reuse", "repair"], "climate_per_use"].min() / evaluate_all({**ctx, "n_uses": n}).loc["recycling", "climate_per_use"] - 1) for n in (2, 3, 4, 6, 10)}
    summary = {
        "context": ctx, "recommended": rec.strategy, "rule_based": rec.rule_strategy,
        "climate_per_use": base.climate_per_use.round(2).to_dict(), "cost_per_use": base.cost_per_use.round(1).to_dict(),
        "circularity": base.circularity.round(3).to_dict(), "expected_uses": base.expected_uses.round(2).to_dict(),
        "climate_cut_off": cut.climate_per_use.round(2).to_dict(), "scores": rec.score_table.score.round(3).to_dict(),
        "break_even_uses": {s: break_even_uses(ctx, None, s) for s in ("reuse", "repair", "reprocessing")},
        "mc_prob_reuse_better_current": float((mc[["reuse", "repair"]].min(axis=1) < mc.recycling).mean()),
        "mc_prob_reuse_better_stress": float((mcs[["reuse", "repair"]].min(axis=1) < mcs.recycling).mean()),
        "mc_median_climate": mc[["reuse", "recycling", "disposal"]].median().round(2).to_dict(),
        "ml_metrics": ml["metrics"], "ml_rf_probability_baseline": predict_reuse_probability(ml, ctx),
        "tornado_top5": [{"parameter": names.get(r.parameter, r.parameter), "swing": round(r.swing, 2)} for r in tor.head(5).itertuples()],
        "optimiser_best": opt.iloc[0][["design", "strategy", "business_model", "n_uses", "event_km", "climate_per_use", "cost_per_use", "circularity"]].to_dict(),
        "pareto_size": int(len(pf)), "n_params_used": int(len(used)), "n_params_literature_or_database": int(used.type.isin(["literature", "database"]).sum()),
        "validation_reduction_vs_recycling": val, "published_reduction": -0.22,
        "recycling_vs_reuse_gap_at_1_use_pct": float(((evaluate_all({**ctx, "n_uses": 1}).loc[["reuse", "repair"], "climate_per_use"].min() / evaluate_all({**ctx, "n_uses": 1}).loc["recycling", "climate_per_use"]) - 1) * 100),
    }
    (R / "summary.json").write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")
    build_static(T, ctx, rec, grid, mc, mcs, tor, ml, opt, names, val)
    return summary


def build_static(T, ctx, rec, grid, mc, mcs, tor, ml, opt, names, val):
    us, dd = uses_sweep(ctx, 15), distance_sweep(ctx, range(0, 1501, 100))
    bd = {s: evaluate({**ctx, "strategy": s})["breakdown_per_use"] for s in viz.ORDER}
    r = evaluate({**ctx, "strategy": rec.strategy})
    figs = [("Recommendation", viz.fig_score_bars(rec.score_table, rec.strategy)), ("KPI profile", viz.fig_radar(rec.score_table)),
            ("Climate impact breakdown", viz.fig_breakdown(bd)),
            ("Material flow", viz.fig_sankey(r["mass_kg"], 0.30, r["material_recovery"], viz.LAB[rec.strategy], r["expected_uses"])),
            ("Animated: planned uses", viz.fig_uses_animation(us)), ("Break-even", viz.fig_uses_lines(us, break_even_uses(ctx, None, "reuse"))),
            ("Animated: distance", viz.fig_distance_animation(dd)),
            ("Uses vs damage", viz.fig_gap_map(gap_map(ctx, "n_uses", [1, 2, 3, 4, 6, 8, 10, 15], "damage_rate", [0.02, 0.05, 0.08, 0.12, 0.16, 0.2, 0.25, 0.35, 0.5]), "Planned uses per panel", "Panel loss rate per event", "How much better is reuse than recycling?", "Percent change in climate per use; green = reuse better, blue = recycling better")),
            ("Distance vs freight", viz.fig_gap_map(gap_map(ctx, "event_km", [0, 300, 600, 900, 1200, 1500, 2000, 3000], "transport_ef", [0.058, 0.1, 0.15, 0.2, 0.3, 0.4, 0.562]), "Event distance (km)", "Freight emission factor (kg CO2e/t-km)", "Does transport ever change the winner?", "Small partly loaded vehicles have about 10 times the factor of a full truck")),
            ("Animated: trade-offs", viz.fig_pareto_animation(grid, {})), ("Optimiser", viz.fig_optimiser(opt)),
            ("Monte Carlo", viz.fig_mc(mc, " (baseline)")), ("Monte Carlo stress", viz.fig_mc(mcs, " (stress: 2 uses, sale, 1,200 km)")),
            ("Tornado", viz.fig_tornado(tor, names)), ("ML parity", viz.fig_ml_parity(ml["parity"], ml["metrics"]["r2"], ml["metrics"]["mae"])),
            ("ML importance", viz.fig_importance(ml["importance"])), ("Provenance", viz.fig_provenance(T["sources"])),
            ("Validation", viz.fig_validation(pd.DataFrame([{"label": f"{n} planned uses", "change": c} for n, c in val.items()]), -0.22))]
    parts, first = [], True
    for title, f in figs:
        parts.append(f'<section class="card">{pio.to_html(f, full_html=False, include_plotlyjs=True if first else False, auto_play=False, default_width="100%", config={"displaylogo": False, "responsive": True})}</section>')
        first = False
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Circular Design Advisor</title><style>
:root{{--ink:#14213D;--mut:#5B6475;--bg:#F7F8FC}}
body{{margin:0;background:var(--bg);font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif;color:var(--ink)}}
.hero{{background:linear-gradient(120deg,#14213D,#3B2D8F,#0A9E72,#1C7ED6);background-size:300% 300%;animation:drift 14s ease infinite;color:#fff;padding:34px 6vw}}
@keyframes drift{{0%{{background-position:0 50%}}50%{{background-position:100% 50%}}100%{{background-position:0 50%}}}}
@keyframes rise{{from{{opacity:0;transform:translateY(18px)}}to{{opacity:1;transform:none}}}}
h1{{margin:0 0 6px;font-size:2rem}}.hero p{{margin:0;max-width:900px;opacity:.9}}
main{{padding:18px 4vw;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,560px),1fr));gap:16px}}
.card{{background:#fff;border-radius:16px;padding:8px;border:1px solid #E6E9F0;box-shadow:0 6px 18px rgba(20,33,61,.07);animation:rise .7s ease both;overflow:hidden}}
.wide{{grid-column:1/-1}}.note{{padding:6px 6vw 24px;color:var(--mut);font-size:.9rem;max-width:1100px}}
</style></head><body>
<div class="hero"><h1>Circular Design Advisor</h1><p>Static, animated export of the dashboard for an aluminium exhibition-booth panel: reuse, repair, reprocessing, recycling or disposal. Baseline: design B, rental, 6 planned uses, 400 km.
Recommended: <b>{viz.LAB[rec.strategy]}</b>. Press the play buttons on the animated charts.</p></div>
<main>{''.join(parts)}</main>
<div class="note">Illustrative model. Only {int(T['sources'][T['sources'].used_in_model].type.isin(['literature','database']).sum())} of {int(T['sources'].used_in_model.sum())} model inputs come from literature or public databases; the rest are flagged assumptions. Full sources: data/literature_sources.csv.</div>
</body></html>"""
    (ROOT / "outputs" / "dashboard_static.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    s = main()
    print(json.dumps({k: v for k, v in s.items() if k in ("recommended", "climate_per_use", "mc_prob_reuse_better_current", "mc_prob_reuse_better_stress", "ml_metrics")}, indent=1, default=float))
