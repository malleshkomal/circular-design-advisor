"""Plotly figures. One fixed colour per strategy everywhere (colour follows the entity)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .data import load_all
from .recommend import LABELS

COL = {"reuse": "#0A9E72", "repair": "#7048E8", "reprocessing": "#C77700", "recycling": "#1C7ED6", "disposal": "#E03131"}
LAB = {k: LABELS[k] for k in COL}
INK, INK2, GRID = "#14213D", "#4A5568", "#E6E9F0"
FONT = "Inter, Segoe UI, Helvetica, Arial, sans-serif"
ORDER = list(COL)
COMP = {"Panel production": "#3B4A6B", "Transport (events)": "#8FA3C7", "Cleaning and repair": "#F2B134",
        "End-of-life processes": "#B8C2D6", "Recycling credit": "#0A9E72"}
SRC_COL = {"literature": "#1C7ED6", "database": "#7048E8", "assumption": "#F2B134"}
FOOT = "Sources: data/literature_sources.csv. Values not marked literature or database are labelled assumptions."


def _layout(fig, title=None, sub=None, h=420, legend=True, foot=True):
    t = f"<b>{title}</b>" + (f"<br><span style='font-size:12px;color:{INK2}'>{sub}</span>" if sub else "") if title else None
    fig.update_layout(title=dict(text=t, x=0.01, xanchor="left", y=0.97, font=dict(size=16, color=INK)) if t else None,
                      font=dict(family=FONT, color=INK2, size=12), paper_bgcolor="white", plot_bgcolor="white",
                      height=h, margin=dict(l=55, r=25, t=80 if t else 30, b=95 if legend else 55),
                      legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=11)) if legend else None, showlegend=legend,
                      hoverlabel=dict(font_family=FONT, bgcolor="white", bordercolor=GRID))
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, ticks="")
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, ticks="")
    return fig


def _play(fig, frame_ms=450, label="Play"):
    fig.update_layout(updatemenus=[dict(type="buttons", direction="left", x=0.0, y=1.14, xanchor="left", showactive=False,
                                        buttons=[dict(label=f"▶ {label}", method="animate",
                                                      args=[None, dict(frame=dict(duration=frame_ms, redraw=True), transition=dict(duration=300, easing="cubic-in-out"), fromcurrent=True)]),
                                                 dict(label="❚❚ Pause", method="animate",
                                                      args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate", transition=dict(duration=0))])])])
    return fig


# ---------------------------------------------------------------- overview
def fig_score_bars(score_table: pd.DataFrame, best: str):
    t = score_table.sort_values("score")
    fig = go.Figure(go.Bar(y=[LAB[i] + ("  ✓ recommended" if i == best else "") for i in t.index], x=t.score, orientation="h",
                           marker=dict(color=[COL[i] for i in t.index], cornerradius=6), text=[f"{v:.2f}" for v in t.score],
                           textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}<br>Weighted score %{x:.2f}<extra></extra>"))
    fig.update_xaxes(range=[0, 1.1], title="Weighted recommendation score (0 to 1, higher is better)")
    return _layout(fig, "Recommendation score by strategy", "50 % environment, 25 % circularity, 15 % economics, 10 % feasibility", 340, False)


def fig_radar(score_table: pd.DataFrame):
    cats = ["environment", "circularity", "economics", "feasibility"]
    names = ["Climate", "Circularity", "Cost", "Feasibility"]
    fig = go.Figure()
    for s in ORDER:
        v = [score_table.loc[s, c] for c in cats]
        fig.add_trace(go.Scatterpolar(r=v + v[:1], theta=names + names[:1], name=LAB[s], line=dict(color=COL[s], width=2.5),
                                      opacity=0.95,
                                      hovertemplate="%{theta}: %{r:.2f}<extra>" + LAB[s] + "</extra>"))
    fig.update_polars(radialaxis=dict(range=[0, 1], gridcolor=GRID, tickfont=dict(size=10)), angularaxis=dict(gridcolor=GRID))
    return _layout(fig, "KPI profile", "Larger is better on every axis (cost and climate are inverted)", 430)


def fig_breakdown(ctx_results: dict):
    """ctx_results: strategy -> breakdown_per_use dict."""
    fig = go.Figure()
    for k, c in COMP.items():
        fig.add_trace(go.Bar(name=k, x=[LAB[s] for s in ctx_results], y=[ctx_results[s][k] for s in ctx_results], marker=dict(color=c, line=dict(color="white", width=1.5)),
                             hovertemplate="%{x}<br>" + k + ": %{y:.2f} kg CO2e per use<extra></extra>"))
    fig.update_layout(barmode="relative")
    fig.update_yaxes(title="kg CO2e per use (net total shown as dot)")
    tot = [sum(ctx_results[s].values()) for s in ctx_results]
    fig.add_trace(go.Scatter(x=[LAB[s] for s in ctx_results], y=tot, mode="markers+text", name="Net total", text=[f"{v:.1f}" for v in tot],
                             textposition="top center", marker=dict(color=INK, size=10, line=dict(color="white", width=2)),
                             hovertemplate="Net total %{y:.1f}<extra></extra>"))
    return _layout(fig, "Where the climate impact comes from", "Per use; the recycling credit (green) offsets production", 440)


# ---------------------------------------------------------------- scenario lab
def fig_uses_animation(df: pd.DataFrame, metric="climate_per_use", title="Climate impact per use as planned uses increase", ytitle="kg CO2e per use"):
    d = df.copy()
    d["label"] = d.strategy.map(LAB)
    ymax = d[metric].max() * 1.12
    fig = px.bar(d, x="label", y=metric, color="strategy", animation_frame="n_uses", color_discrete_map=COL,
                 category_orders={"label": [LAB[s] for s in ORDER]}, range_y=[0, ymax],
                 labels={"label": "", metric: ytitle})
    fig.update_traces(marker=dict(cornerradius=6), hovertemplate="%{x}<br>%{y:.1f}<extra></extra>")
    fig.update_layout(sliders=[dict(currentvalue=dict(prefix="Planned uses per panel: "), pad=dict(t=40))])
    _layout(fig, title, "Press play or drag the slider; single-use routes do not change", 470, False, False)
    return _play(fig, 500)


def fig_uses_lines(df: pd.DataFrame, break_even: int | None = None):
    fig = go.Figure()
    for s in ORDER:
        d = df[df.strategy == s]
        fig.add_trace(go.Scatter(x=d.n_uses, y=d.climate_per_use, name=LAB[s], mode="lines+markers", line=dict(color=COL[s], width=3),
                                 marker=dict(size=7, line=dict(color="white", width=1.5)),
                                 hovertemplate="%{x} planned uses<br>%{y:.1f} kg CO2e per use<extra>" + LAB[s] + "</extra>"))
    if break_even:
        fig.add_vline(x=break_even, line=dict(color=INK2, width=1.2, dash="dot"))
        fig.add_annotation(x=break_even, y=0.62, yref="paper", text=f"  Break-even vs recycling: {break_even} uses", showarrow=False, xanchor="left", font=dict(size=11, color=INK))
    fig.update_xaxes(title="Planned uses per panel")
    fig.update_yaxes(title="kg CO2e per use", rangemode="tozero")
    return _layout(fig, "Break-even number of uses", "Reuse routes fall quickly as production is spread over more events", 440)


def fig_distance_animation(df: pd.DataFrame):
    d = df.copy(); d["label"] = d.strategy.map(LAB)
    fig = px.bar(d, x="label", y="climate_per_use", color="strategy", animation_frame="event_km", color_discrete_map=COL,
                 category_orders={"label": [LAB[s] for s in ORDER]}, range_y=[0, d.climate_per_use.max() * 1.12], labels={"label": "", "climate_per_use": "kg CO2e per use"})
    fig.update_traces(marker=dict(cornerradius=6))
    fig.update_layout(sliders=[dict(currentvalue=dict(prefix="Event distance (km): "), pad=dict(t=40))])
    _layout(fig, "Climate impact per use as event distance grows", "Transport matters little per 12 kg panel unless vehicles are small and partly loaded", 470, False, False)
    return _play(fig, 350)


_CODE = {s: i for i, s in enumerate(ORDER)}


def fig_regime(code: pd.DataFrame, xtitle, ytitle, title, sub, xfmt=None, base=None):
    fam = {"reuse": 0, "repair": 0, "reprocessing": 0, "recycling": 1, "disposal": 2}
    z = code.map(lambda s: fam[s]).to_numpy(dtype=float)
    fcol = [COL["reuse"], COL["recycling"], COL["disposal"]]
    scale = [[0, fcol[0]], [1 / 3, fcol[0]], [1 / 3, fcol[1]], [2 / 3, fcol[1]], [2 / 3, fcol[2]], [1, fcol[2]]]
    txt = np.vectorize(lambda s: LAB[s])(code.to_numpy())
    fig = go.Figure(go.Heatmap(z=z, x=list(code.columns), y=list(code.index), colorscale=scale, zmin=-0.5 + 0.5, zmax=3.0,
                               showscale=False, text=txt, xgap=2, ygap=2,
                               hovertemplate=xtitle + ": %{x}<br>" + ytitle + ": %{y}<br>Lowest climate impact: %{text}<extra></extra>"))
    for nm, c in (("Reuse family (reuse, repair or reprocessing)", fcol[0]), ("Recycling", fcol[1]), ("Disposal", fcol[2])):
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(size=11, color=c, symbol="square"), name=nm))
    fig.update_xaxes(title=xtitle, type="category"); fig.update_yaxes(title=ytitle, type="category")
    return _layout(fig, title, sub, 440)


def fig_sankey(m, rc, y, strategy_label, uses):
    nodes = ["Primary aluminium", "Recycled aluminium", "Panel", "Use phase", "Recovered metal", "Lost / landfilled", "Secondary pool"]
    src = [0, 1, 2, 3, 3, 4]
    tgt = [2, 2, 3, 4, 5, 6]
    val = [m * (1 - rc), m * rc, m, m * y, m * (1 - y), m * y]
    cols = ["#3B4A6B", "#0A9E72", "#7048E8", "#1C7ED6", "#E03131", "#0A9E72"]
    fig = go.Figure(go.Sankey(arrangement="snap",
        node=dict(label=nodes, color=["#3B4A6B", "#0A9E72", "#7048E8", "#1C7ED6", "#0A9E72", "#E03131", "#0A9E72"], pad=22, thickness=18, line=dict(color="white", width=1)),
        link=dict(source=src, target=tgt, value=val, color=[c + "55" for c in cols], hovertemplate="%{value:.1f} kg<extra></extra>")))
    return _layout(fig, "Material flow of one panel", f"{strategy_label}, {uses:.1f} events per panel; mass in kg, recycling yield {y:.0%}", 400, False)


# ---------------------------------------------------------------- trade-offs
def fig_pareto_animation(grid: pd.DataFrame, front_by_km: dict):
    d = grid[(grid.n_uses.isin([1, 2, 3, 4, 6, 8, 10, 12, 15]))].copy()
    d["label"] = d.strategy.map(LAB)
    d["circ_size"] = 8 + 22 * d.circularity.clip(0, 1)
    fig = px.scatter(d, x="cost_per_use", y="climate_per_use", color="strategy", size="circ_size", animation_frame="event_km", color_discrete_map=COL,
                     hover_data={"label": True, "design": True, "business_model": True, "n_uses": True, "circ_size": False, "strategy": False},
                     range_x=[0, d.cost_per_use.max() * 1.05], range_y=[0, d.climate_per_use.max() * 1.05],
                     labels={"cost_per_use": "Cost per use (EUR)", "climate_per_use": "kg CO2e per use"})
    fig.update_traces(marker=dict(opacity=0.75, line=dict(color="white", width=1)))
    fig.update_layout(sliders=[dict(currentvalue=dict(prefix="Event distance (km): "), pad=dict(t=40))])
    _layout(fig, "Climate vs cost trade-off across all scenarios", "Each bubble is a design, business model and planned-use combination; size = circularity. Lower left is better.", 540, True, False)
    fig.update_layout(legend=dict(orientation="h", y=1.10, x=0.28, title=dict(text="")), margin=dict(b=100))
    return _play(fig, 700)


def fig_business_models(df: pd.DataFrame):
    fig = go.Figure()
    for b, c in zip(df.business_model.unique(), ["#8FA3C7", "#0A9E72", "#7048E8"]):
        d = df[df.business_model == b]
        fig.add_trace(go.Bar(x=d.strategy.map(LAB), y=d.climate_per_use, name=b.capitalize() if b != "paas" else "Product-as-a-service", marker=dict(color=c, cornerradius=5),
                             hovertemplate="%{x}<br>%{y:.1f} kg CO2e per use<extra>" + b + "</extra>"))
    fig.update_layout(barmode="group"); fig.update_yaxes(title="kg CO2e per use")
    return _layout(fig, "Business model effect", "Redeployment behaviour per business model is an assumption, not a literature value", 400)


def fig_optimiser(top: pd.DataFrame):
    t = top.copy().iloc[::-1]
    lab = [f"{r.design} · {LAB[r.strategy]} · {r.business_model} · {int(r.n_uses)} uses · {int(r.event_km)} km" for r in t.itertuples()]
    fig = go.Figure(go.Bar(y=lab, x=-t.objective, orientation="h", marker=dict(color=[COL[s] for s in t.strategy], cornerradius=5),
                           text=[f"{v:.2f}" for v in -t.objective], textposition="outside", cliponaxis=False,
                           hovertemplate="%{y}<br>Objective (higher is better): %{x:.2f}<extra></extra>"))
    fig.update_xaxes(title="Score (higher is better)")
    fig.update_layout(margin=dict(l=330))
    return _layout(fig, "Best configurations found by the optimiser", "0.50 climate + 0.25 cost - 0.25 circularity, exhaustive search", 430, False)


# ---------------------------------------------------------------- uncertainty and ML
def fig_tornado(tor: pd.DataFrame, names: dict, strategy_label="Direct reuse"):
    t = tor.head(10).iloc[::-1]
    fig = go.Figure()
    base = t.base_gap.iloc[0]
    fig.add_trace(go.Bar(y=[names.get(p, p) for p in t.parameter], x=t.low_gap - base, base=base, orientation="h", name="Parameter at low end", marker=dict(color="#8FA3C7"),
                         hovertemplate="%{y}<br>gap at low value: %{customdata:.1f}<extra></extra>", customdata=t.low_gap))
    fig.add_trace(go.Bar(y=[names.get(p, p) for p in t.parameter], x=t.high_gap - base, base=base, orientation="h", name="Parameter at high end", marker=dict(color="#7048E8"),
                         hovertemplate="%{y}<br>gap at high value: %{customdata:.1f}<extra></extra>", customdata=t.high_gap))
    fig.add_vline(x=0, line=dict(color=INK, width=1)); fig.add_vline(x=base, line=dict(color=INK2, dash="dot"))
    fig.update_layout(barmode="overlay"); fig.update_xaxes(title=f"{strategy_label} minus recycling, kg CO2e per use (negative = reuse better)")
    fig.update_layout(margin=dict(l=250))
    return _layout(fig, "What moves the answer most", "One parameter at a time across its literature or assumed range; dotted line = baseline", 470)


def fig_mc(mc: pd.DataFrame, label=""):
    fig = go.Figure()
    for s in ORDER:
        if s in mc:
            fig.add_trace(go.Violin(y=mc[s], name=LAB[s], line_color=COL[s], fillcolor=COL[s], opacity=0.55, box_visible=True, meanline_visible=True, points=False,
                                    hovertemplate="%{y:.1f} kg CO2e per use<extra>" + LAB[s] + "</extra>"))
    fig.update_yaxes(title="kg CO2e per use"); fig.update_layout(showlegend=False)
    return _layout(fig, "Monte Carlo uncertainty" + label, "Each ranged input drawn from a triangular distribution (1,500 draws)", 430, False)


def fig_ml_parity(parity: pd.DataFrame, r2, mae):
    fig = px.scatter(parity, x="actual", y="predicted", color="strategy", color_discrete_map=COL, opacity=0.55, labels={"actual": "Physics model, kg CO2e per use", "predicted": "Random Forest prediction"})
    mx = float(max(parity.actual.max(), parity.predicted.max()))
    fig.add_trace(go.Scatter(x=[0, mx], y=[0, mx], mode="lines", line=dict(color=INK, dash="dot", width=1), name="Perfect", hoverinfo="skip"))
    return _layout(fig, "Machine-learning screening model", f"Held-out scenarios: R² = {r2:.3f}, mean absolute error = {mae:.1f} kg CO2e per use", 430)


def fig_importance(imp: pd.DataFrame, title="What the model relies on"):
    d = imp.copy()
    d["group"] = np.where(d.feature.str.startswith("is_"), "Strategy choice", d.label)
    d = d.groupby("group", as_index=False).importance.sum().sort_values("importance").tail(9)
    fig = go.Figure(go.Bar(y=d.group, x=d.importance, orientation="h", marker=dict(color="#7048E8", cornerradius=5), hovertemplate="%{y}: %{x:.3f}<extra></extra>"))
    fig.update_xaxes(title="Permutation importance (loss in R² when shuffled)")
    fig.update_layout(margin=dict(l=190))
    return _layout(fig, title, "Features ranked on held-out data", 430, False)


# ---------------------------------------------------------------- data
def fig_provenance(src: pd.DataFrame):
    d = src.copy()
    d["group"] = np.where(d.used_in_model, "Used in the model", "Benchmark or context only")
    d["type"] = d.type.str.capitalize()
    d["n"] = 1
    fig = px.sunburst(d, path=["group", "type"], values="n", color="type", color_discrete_map={"Literature": "#1C7ED6", "Database": "#7048E8", "Assumption": "#F2B134", "(?)": "#DDE3EE"})
    fig.update_traces(textinfo="label+value", insidetextorientation="horizontal", hovertemplate="%{label}: %{value} parameters<extra></extra>", marker=dict(line=dict(color="white", width=2)))
    return _layout(fig, "Where each input comes from", "Number of parameters by evidence type", 430, False)


def fig_validation(rows: pd.DataFrame, literature: float):
    fig = go.Figure(go.Bar(x=rows.label, y=rows.change * 100, marker=dict(color="#0A9E72", cornerradius=5), text=[f"{v*100:.0f} %" for v in rows.change], textposition="outside",
                           hovertemplate="%{x}: %{y:.0f} %<extra></extra>"))
    fig.add_hline(y=literature * 100, line=dict(color="#E03131", dash="dash", width=2))
    fig.add_annotation(x=1, xref="paper", y=literature * 100, text=f"Published: {literature*100:.0f} % (Skejić et al. 2026, tent frame)", showarrow=False, xanchor="right", yshift=14,
                       font=dict(color="#B42318", size=11), bgcolor="white")
    fig.update_yaxes(title="Change in climate impact, reuse vs recycling (%)", range=[min(-100, rows.change.min() * 130), 8])
    return _layout(fig, "Plausibility check against the literature", "Same direction as the published case, but the model shows larger reductions: different functional unit and system, so treat the magnitude with caution", 400, False)


def style_results_table(df: pd.DataFrame):
    return df


def fig_gap_map(gap: pd.DataFrame, xtitle, ytitle, title, sub):
    z = gap.to_numpy(dtype=float)
    zmin, zmax = min(float(np.nanmin(z)), -1.0), max(float(np.nanmax(z)), 1.0)
    mid = (0 - zmin) / (zmax - zmin)
    scale = [[0, "#0A9E72"], [mid, "#F1F3F8"], [1, "#1C7ED6"]]
    fig = go.Figure(go.Heatmap(z=z, x=[str(c) for c in gap.columns], y=[str(i) for i in gap.index], colorscale=scale, zmin=zmin, zmax=zmax, xgap=2, ygap=2,
                               texttemplate="%{z:.0f}", textfont=dict(size=10, color=INK),
                               colorbar=dict(title=dict(text="% vs recycling"), thickness=12, len=0.8),
                               hovertemplate=xtitle + ": %{x}<br>" + ytitle + ": %{y}<br>Best reuse route vs recycling: %{z:.0f} %<extra></extra>"))
    fig.update_xaxes(title=xtitle, type="category"); fig.update_yaxes(title=ytitle, type="category")
    return _layout(fig, title, sub, 450, False)
