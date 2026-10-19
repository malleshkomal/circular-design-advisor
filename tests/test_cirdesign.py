import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
import pytest

from cirdesign.analysis import break_even_uses, gap_map, monte_carlo, optimise, pareto_front, simulate_grid
from cirdesign.chatbot import Assistant
from cirdesign.data import central_params, load_all, param_ranges
from cirdesign.model import evaluate, evaluate_all, expected_uses
from cirdesign.recommend import recommend


def test_sources_have_urls_for_literature_and_database_rows():
    s = load_all()["sources"]
    lit = s[s.type.isin(["literature", "database"])]
    assert lit.url.notna().all() and lit.source.notna().all()
    assert s.id.is_unique


def test_ranges_bracket_central_values():
    for k, (lo, mo, hi) in param_ranges().items():
        assert lo <= mo <= hi, k


def test_expected_uses_limits():
    assert expected_uses(6, 0.0) == 6
    assert expected_uses(1, 0.5) == 1
    assert expected_uses(5, 1.0) == pytest.approx(1.0)
    brute = sum((1 - 0.2) ** k for k in range(10))
    assert expected_uses(10, 0.2) == pytest.approx(brute)


def test_breakdown_sums_to_total():
    for s in ("reuse", "repair", "reprocessing", "recycling", "disposal"):
        r = evaluate({"strategy": s})
        assert sum(r["breakdown_per_use"].values()) == pytest.approx(r["climate_per_use"])


def test_cut_off_never_better_than_net_scrap_for_recycling():
    a = evaluate({"strategy": "recycling", "credit": "net_scrap"})["climate_per_use"]
    b = evaluate({"strategy": "recycling", "credit": "cut_off"})["climate_per_use"]
    assert b >= a


def test_more_uses_lower_impact_per_use_for_reuse():
    vals = [evaluate({"strategy": "reuse", "n_uses": n})["climate_per_use"] for n in (1, 2, 4, 8)]
    assert vals == sorted(vals, reverse=True)


def test_single_use_routes_ignore_planned_uses():
    assert evaluate({"strategy": "recycling", "n_uses": 1})["climate_per_use"] == pytest.approx(
        evaluate({"strategy": "recycling", "n_uses": 20})["climate_per_use"])


def test_disposal_is_worst_climate_in_baseline():
    t = evaluate_all()
    assert t.climate_per_use.idxmax() == "disposal"


def test_circularity_bounded_and_ordered():
    t = evaluate_all()
    assert ((t.circularity >= 0) & (t.circularity <= 1)).all()
    assert t.loc["reuse", "circularity"] > t.loc["recycling", "circularity"] > t.loc["disposal", "circularity"]


def test_recycling_can_win_when_transport_is_extreme():
    t = evaluate_all({"design": "A", "business_model": "sale", "n_uses": 2, "event_km": 3000}, {"transport_ef": 0.562, "damage_rate": 0.25})
    assert t.loc[["reuse", "repair", "reprocessing"], "climate_per_use"].min() > t.loc["recycling", "climate_per_use"]


def test_break_even_is_small_but_exists():
    assert break_even_uses() in (2, 3)


def test_recommendation_is_conditional_and_explained():
    rec = recommend()
    assert rec.strategy in ("reuse", "repair", "reprocessing") and len(rec.reasons) >= 3
    stressed = recommend({"n_uses": 1, "event_km": 1400})
    assert stressed.strategy in ("recycling", "disposal", "reuse", "repair", "reprocessing")
    assert abs(rec.score_table.score.max() - 1) <= 1


def test_grid_and_pareto_and_optimiser():
    g = simulate_grid(n_range=range(1, 4), km_values=(50, 500))
    assert {"design", "strategy", "business_model", "climate_per_use"} <= set(g.columns)
    pf = pareto_front(g)
    assert 1 <= len(pf) < len(g)
    top = optimise(g, top=5)
    assert len(top) == 5 and top.objective.is_monotonic_increasing


def test_monte_carlo_shape_and_reproducibility():
    a = monte_carlo(n=40, seed=1)
    b = monte_carlo(n=40, seed=1)
    pd.testing.assert_frame_equal(a, b)
    assert (a.disposal > a.recycling).mean() > 0.9


def test_gap_map_signs():
    g = gap_map({}, "n_uses", [1, 6], "damage_rate", [0.05])
    assert g.iloc[0, 1] < 0 < g.iloc[0, 0]


def test_chatbot_answers_use_computed_numbers_only():
    a = Assistant()
    out = a.answer("what happens if transport increases to 900 km?")
    assert "900 km" in out and "kg CO2e" in out
    assert "break-even" in a.answer("what is the break-even number of uses").lower()
    assert "assumption" in a.answer("where does the data come from").lower()
    assert "did not match" in a.answer("tell me a joke")
