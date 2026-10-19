"""Circular Design Advisor: run with  streamlit run app.py"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from cirdesign import viz
from cirdesign.analysis import (REUSE_FAMILY, gap_map, break_even_uses, distance_sweep, monte_carlo, optimise, pareto_front,
                                regime_map, simulate_grid, tornado, uses_sweep)
from cirdesign.chatbot import HELP, Assistant, llm_polish
from cirdesign.data import central_params, load_all, param_ranges
from cirdesign.model import evaluate, evaluate_all
from cirdesign.recommend import LABELS, WEIGHTS, recommend, score_strategies

st.set_page_config(page_title="Circular Design Advisor", page_icon="♻️", layout="wide")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', sans-serif; }
.block-container { padding-top: 1.2rem; max-width: 1400px; }
@keyframes rise { from {opacity:0; transform: translateY(14px);} to {opacity:1; transform:none;} }
@keyframes drift { 0% {background-position: 0% 50%;} 50% {background-position: 100% 50%;} 100% {background-position: 0% 50%;} }
@keyframes pulse { 0%,100% {box-shadow: 0 0 0 0 rgba(10,158,114,.55);} 50% {box-shadow: 0 0 0 10px rgba(10,158,114,0);} }
.hero { background: linear-gradient(120deg,#14213D,#3B2D8F,#0A9E72,#1C7ED6); background-size: 300% 300%; animation: drift 14s ease infinite, rise .7s ease both;
        border-radius: 22px; padding: 28px 34px; color: #fff; margin-bottom: 14px; }
.hero h1 { color:#fff; font-weight:800; font-size: 2.1rem; margin:0 0 4px 0; letter-spacing:-.5px; }
.hero p { color: rgba(255,255,255,.88); margin:0; font-size: 1.02rem; max-width: 980px; }
.chip { display:inline-block; padding:4px 12px; margin:10px 8px 0 0; border-radius:99px; background:rgba(255,255,255,.16); font-size:.8rem; backdrop-filter: blur(6px);}
.reco { border-radius:18px; padding:18px 22px; background: linear-gradient(135deg,#ECFDF5,#EEF2FF); border:1px solid #D7E3F4; animation: rise .8s ease both; }
.reco h3 { margin:0 0 6px 0; color:#14213D; }
.badge { display:inline-block; padding:3px 12px; border-radius:99px; color:#fff; font-weight:600; font-size:.82rem; animation: pulse 2.2s infinite; }
.note { color:#5B6475; font-size:.85rem; }
div[data-testid="stTabs"] button { font-weight:600; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

T = load_all()
CENTRAL = central_params(T)
RANGES = param_ranges(T)
PLABEL = dict(zip(T["sources"].id, T["sources"].parameter))


def _key(d):
    return tuple(sorted(d.items()))


@st.cache_data(show_spinner=False)
def c_table(ctx_k, par_k):
    return evaluate_all(dict(ctx_k), dict(par_k))


@st.cache_data(show_spinner=False)
def c_scores(ctx_k, par_k, w_k):
    return score_strategies(dict(ctx_k), dict(par_k), dict(w_k))


@st.cache_data(show_spinner="Simulating scenario grid ...")
def c_grid(credit):
    return simulate_grid(credit=credit)


@st.cache_data(show_spinner="Running Monte Carlo ...")
def c_mc(ctx_k, n=1200):
    return monte_carlo(dict(ctx_k), n=n)


@st.cache_data(show_spinner=False)
def c_uses(ctx_k, par_k):
    return uses_sweep(dict(ctx_k), 15, dict(par_k))


@st.cache_data(show_spinner=False)
def c_dist(ctx_k, par_k):
    return distance_sweep(dict(ctx_k), range(0, 1501, 100), dict(par_k))


@st.cache_data(show_spinner=False)
def c_tornado(ctx_k, strategy):
    return tornado(dict(ctx_k), strategy)


@st.cache_data(show_spinner="Computing regime maps ...")
def c_regime(ctx_k, par_k, which):
    ctx, par = dict(ctx_k), dict(par_k)
    if which == "uses_damage":
        xs, ys = [1, 2, 3, 4, 6, 8, 10, 15], [0.02, 0.05, 0.08, 0.12, 0.16, 0.20, 0.25, 0.35, 0.50]
        return gap_map(ctx, "n_uses", xs, "damage_rate", ys, par)
    xs, ys = [0, 300, 600, 900, 1200, 1500, 2000, 3000], [0.058, 0.1, 0.15, 0.2, 0.3, 0.4, 0.562]
    return gap_map(ctx, "event_km", xs, "transport_ef", ys, par)


@st.cache_resource(show_spinner="Training machine-learning screening models (first run only) ...")
def get_ml():
    import joblib
    from cirdesign.ml import train
    f = ROOT / "results" / "ml_model.joblib"
    if f.exists():
        return joblib.load(f)
    m = train(1500)
    f.parent.mkdir(exist_ok=True)
    joblib.dump(m, f)
    return m


# ------------------------------------------------------------------ sidebar
sb = st.sidebar
sb.markdown("### Your product")
design = sb.selectbox("Panel design", list(T["designs"].index), index=1,
                      format_func=lambda d: f"{d}: {T['designs'].loc[d, 'name']}")
bm = sb.selectbox("Business model", list(T["business_models"].index), index=1, format_func=lambda b: T["business_models"].loc[b, "label"])
n_uses = sb.slider("Planned uses per panel", 1, 40, 6)
event_km = sb.slider("Distance depot to event (km)", 0, 1500, 400, 25)
eol_km = sb.slider("Distance to recycler (km)", 0, 500, 100, 10)
credit = sb.radio("Recycling credit method", ["net_scrap", "cut_off"], horizontal=True,
                  help="Net scrap credits recovery beyond recycled content; cut-off gives no end-of-life credit.")
focus = sb.selectbox("Strategy to inspect", list(T["strategies"].index), index=0, format_func=lambda s: LABELS[s])
with sb.expander("Literature and database inputs"):
    p_over = {}
    for k, nm, fmt in [("ef_primary", "Primary aluminium (kg CO2e/kg)", "%.1f"), ("ef_secondary", "Recycled aluminium (kg CO2e/kg)", "%.2f"),
                       ("grid_ef", "Electricity mix (kg CO2e/kWh)", "%.3f"), ("transport_ef", "Freight EF (kg CO2e/t-km)", "%.3f"),
                       ("collection_rate", "Collection rate", "%.2f")]:
        lo, mo, hi = RANGES[k]
        p_over[k] = st.slider(nm, float(lo), float(hi), float(CENTRAL[k]), step=(hi - lo) / 100, format=fmt)
with sb.expander("Assumptions (flagged)"):
    for k, nm in [("damage_rate", "Panel loss rate per event"), ("transport_load_factor", "Truck load factor"), ("recycled_content", "Recycled content of new panels"),
                  ("e_fab", "Fabrication energy (kWh/kg)")]:
        lo, mo, hi = RANGES[k]
        p_over[k] = st.slider(nm, float(lo), float(hi), float(CENTRAL[k]), step=(hi - lo) / 100)
with sb.expander("Recommendation weights"):
    w = {"environment": st.slider("Environment", 0.0, 1.0, WEIGHTS["environment"], 0.05), "circularity": st.slider("Circularity", 0.0, 1.0, WEIGHTS["circularity"], 0.05),
         "economics": st.slider("Economics", 0.0, 1.0, WEIGHTS["economics"], 0.05), "feasibility": st.slider("Feasibility", 0.0, 1.0, WEIGHTS["feasibility"], 0.05)}
    if sum(w.values()) == 0:
        w = dict(WEIGHTS)
sb.caption("Prototype built from literature and public data plus flagged assumptions. Not affiliated with cirKPI.")

ctx = dict(design=design, business_model=bm, n_uses=n_uses, event_km=float(event_km), eol_km=float(eol_km), credit=credit, strategy=focus)
changed = {k: v for k, v in p_over.items() if abs(v - CENTRAL[k]) > 1e-12}
ctxk, park, wk = _key(ctx), _key(changed), _key(w)
rec = recommend(ctx, changed, w)
table = c_table(ctxk, park)
scores = c_scores(ctxk, park, wk)

# ------------------------------------------------------------------ hero
st.markdown(f"""
<div class="hero">
  <h1>Circular Design Advisor</h1>
  <p>Should an exhibition-booth aluminium panel be reused, repaired, reprocessed, recycled or disposed of? A transparent, literature-based decision prototype
  with simulation, optimisation, machine learning and an assistant that explains every result.</p>
  <span class="chip">LCA per use</span><span class="chip">Circularity (MCI)</span><span class="chip">Monte Carlo</span><span class="chip">Random Forest</span><span class="chip">Grounded chatbot</span>
</div>""", unsafe_allow_html=True)

best = rec.strategy
br = table.loc[best]
rc = table.loc["recycling"]
delta = (br.climate_per_use / rc.climate_per_use - 1) * 100


def counter(label, value, unit, decimals, color, sub=""):
    return f"""<div class="k" style="--c:{color}"><div class="l">{label}</div><div class="v"><span data-v="{value}" data-d="{decimals}">0</span><small>{unit}</small></div><div class="s">{sub}</div></div>"""


cards = "".join([
    counter("Climate impact per use", br.climate_per_use, " kg CO2e", 1, "#0A9E72", f"{delta:+.0f} % vs recycling" if best != "recycling" else "baseline route"),
    counter("Circularity score (MCI)", br.circularity, "", 2, "#7048E8", "0 = linear, 1 = fully circular"),
    counter("Cost per use", br.cost_per_use, " EUR", 0, "#C77700", f"recycling: {rc.cost_per_use:.0f} EUR"),
    counter("Expected events per panel", br.expected_uses, "", 1, "#1C7ED6", f"{br.reuse_cycles:.1f} reuse cycles"),
])
components.html(f"""
<style>
body{{margin:0;font-family:Inter,Segoe UI,sans-serif}}
.row{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}
.k{{background:#fff;border-radius:16px;padding:14px 18px;border:1px solid #E6E9F0;border-top:5px solid var(--c);box-shadow:0 6px 18px rgba(20,33,61,.07);animation:rise .8s ease both}}
@keyframes rise{{from{{opacity:0;transform:translateY(16px)}}to{{opacity:1;transform:none}}}}
.l{{font-size:12px;color:#5B6475;font-weight:600;text-transform:uppercase;letter-spacing:.4px}}
.v{{font-size:32px;font-weight:800;color:#14213D;margin-top:4px}}.v small{{font-size:14px;color:#5B6475;font-weight:600}}
.s{{font-size:12px;color:#5B6475;margin-top:2px}}
@media(max-width:720px){{.row{{grid-template-columns:1fr 1fr}}}}
</style>
<div class="row">{cards}</div>
<script>
document.querySelectorAll('[data-v]').forEach(function(el){{
  var t=parseFloat(el.dataset.v),d=parseInt(el.dataset.d),s=performance.now(),dur=1100;
  function f(n){{var p=Math.min((n-s)/dur,1),e=1-Math.pow(1-p,3);el.textContent=(t*e).toFixed(d);if(p<1)requestAnimationFrame(f);}}
  requestAnimationFrame(f);}});
</script>""", height=125)

st.markdown(f"""<div class="reco"><h3>Recommended under these assumptions: <span class="badge" style="background:{viz.COL[best]}">{LABELS[best]}</span></h3>
<div>{'<br>'.join('• ' + r for r in rec.reasons)}</div>
{''.join(f'<div class="note" style="margin-top:6px">⚠ {x}</div>' for x in rec.warnings)}
<div class="note" style="margin-top:8px">Conditional on the inputs in the sidebar; there is no universal best route.</div></div>""", unsafe_allow_html=True)
st.write("")

tabs = st.tabs(["Overview", "Scenario lab", "Trade-offs", "Uncertainty and AI", "Ask the assistant", "Data and methods"])

# ------------------------------------------------------------------ Overview
with tabs[0]:
    c1, c2 = st.columns([1.15, 1])
    c1.plotly_chart(viz.fig_score_bars(scores, best), width="stretch")
    c2.plotly_chart(viz.fig_radar(scores), width="stretch")
    bd = {s: evaluate({**ctx, "strategy": s}, changed)["breakdown_per_use"] for s in viz.ORDER}
    c3, c4 = st.columns([1.15, 1])
    c3.plotly_chart(viz.fig_breakdown(bd), width="stretch")
    r = evaluate({**ctx, "strategy": best if best in viz.ORDER else focus}, changed)
    c4.plotly_chart(viz.fig_sankey(r["mass_kg"], p_over.get("recycled_content", CENTRAL["recycled_content"]), r["material_recovery"], LABELS[best], r["expected_uses"]), width="stretch")
    show = table.rename(columns={"climate_per_use": "Climate (kg CO2e/use)", "cost_per_use": "Cost (EUR/use)", "circularity": "Circularity (MCI)",
                                 "material_recovery": "Material recovery", "virgin_al_per_use": "Virgin Al (kg/use)", "feasibility": "Feasibility", "expected_uses": "Events per panel", "reuse_cycles": "Reuse cycles"})
    show.index = [LABELS[i] for i in show.index]
    st.dataframe(show.style.background_gradient(cmap="RdYlGn_r", subset=["Climate (kg CO2e/use)", "Cost (EUR/use)", "Virgin Al (kg/use)"])
                 .background_gradient(cmap="RdYlGn", subset=["Circularity (MCI)", "Material recovery", "Feasibility"]).format("{:.2f}"), width="stretch")
    ref = float(T["sources"].set_index("id").loc["material_loop_ref", "value"])
    st.caption(f"AUMA reference for the material loop of a booth: {ref:.0%}. Material recovery above is the end-of-life metal yield of each route.")

# ------------------------------------------------------------------ Scenario lab
with tabs[1]:
    st.markdown("#### Press play to watch the answer move")
    us = c_uses(ctxk, park)
    st.plotly_chart(viz.fig_uses_animation(us), width="stretch")
    be = break_even_uses(ctx, changed, focus if focus in REUSE_FAMILY else "reuse")
    st.plotly_chart(viz.fig_uses_lines(us, be), width="stretch")
    dd = c_dist(ctxk, park)
    st.plotly_chart(viz.fig_distance_animation(dd), width="stretch")
    a, b = st.columns(2)
    code1 = c_regime(ctxk, park, "uses_damage")
    a.plotly_chart(viz.fig_gap_map(code1, "Planned uses per panel", "Panel loss rate per event", "How much better is reuse than recycling?", "Percent change in climate per use; green = reuse better, blue = recycling better"), width="stretch")
    code2 = c_regime(ctxk, park, "dist_ef")
    b.plotly_chart(viz.fig_gap_map(code2, "Event distance (km)", "Freight emission factor (kg CO2e/t-km)", "Does transport ever change the winner?", "Small partly loaded vehicles have about 10 times the factor of a full truck"), width="stretch")
    st.caption("Heatmaps use the sidebar design, business model and end-of-life settings; the two axes of each map override the matching sliders. Where a cell turns blue, recycling has the lower climate impact.")

# ------------------------------------------------------------------ Trade-offs
with tabs[2]:
    grid = c_grid(credit)
    st.plotly_chart(viz.fig_pareto_animation(grid, {}), width="stretch")
    st.caption("Press play to see how the cloud of options moves as the event gets further away. Illustrative model; inputs mix literature values and flagged assumptions.")
    s1, s2 = st.columns(2)
    max_km = s1.slider("Optimise only for event distances up to (km)", 50, 900, 500, 50)
    max_n = s2.slider("Maximum planned uses allowed", 2, 15, 8)
    g = grid[(grid.event_km <= max_km) & (grid.n_uses <= max_n)]
    wc, wk_, wr = st.columns(3)
    w_clim = wc.slider("Weight: climate", 0.0, 1.0, 0.50, 0.05)
    w_cost = wk_.slider("Weight: cost", 0.0, 1.0, 0.25, 0.05)
    w_circ = wr.slider("Weight: circularity", 0.0, 1.0, 0.25, 0.05)
    top = optimise(g, w_clim, w_cost, w_circ, 10)
    o1, o2 = st.columns([1.2, 1.1])
    o1.plotly_chart(viz.fig_optimiser(top), width="stretch")
    pf = pareto_front(g)
    o2.markdown("**Pareto-optimal options (climate, cost and feasibility)**")
    pfs = pf.sort_values("climate_per_use").head(10)[["design", "strategy", "business_model", "n_uses", "event_km", "climate_per_use", "cost_per_use", "feasibility"]].copy()
    pfs["strategy"] = pfs.strategy.map(LABELS)
    o2.dataframe(pfs.round(2), width="stretch", hide_index=True)
    rows = []
    for bname in T["business_models"].index:
        t = c_table(_key({**ctx, "business_model": bname}), park)
        t = t.assign(business_model=bname, strategy=t.index)
        rows.append(t)
    st.plotly_chart(viz.fig_business_models(pd.concat(rows, ignore_index=True)), width="stretch")

# ------------------------------------------------------------------ Uncertainty and AI
with tabs[3]:
    mc = c_mc(ctxk)
    m1, m2 = st.columns([1, 1])
    m1.plotly_chart(viz.fig_mc(mc, " (current settings)"), width="stretch")
    p_reuse = float((mc[["reuse", "repair"]].min(axis=1) < mc.recycling).mean())
    stress_ctx = dict(design="C", business_model="sale", n_uses=2, event_km=1200.0, eol_km=100.0, credit=credit)
    mcs = c_mc(_key(stress_ctx))
    p_stress = float((mcs[["reuse", "repair"]].min(axis=1) < mcs.recycling).mean())
    m2.plotly_chart(viz.fig_mc(mcs, " (stress case: 2 uses, sale, 1,200 km)"), width="stretch")
    st.info(f"Probability that a reuse route has lower climate impact than recycling: **{p_reuse:.0%}** for the current settings and **{p_stress:.0%}** in the stress case "
            "(fragile design, sale model, two uses, 1,200 km). The preference is robust only if panels really are reused several times.")
    tor = c_tornado(ctxk, focus if focus in REUSE_FAMILY else "reuse")
    st.plotly_chart(viz.fig_tornado(tor, PLABEL, LABELS[focus] if focus in REUSE_FAMILY else "Direct reuse"), width="stretch")
    st.markdown("#### Machine-learning screening model")
    ml = get_ml()
    mt = ml["metrics"]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("R² (held-out scenarios)", f"{mt['r2']:.3f}")
    k2.metric("Mean absolute error", f"{mt['mae']:.1f} kg CO2e")
    k3.metric("Classifier accuracy", f"{mt['clf_accuracy']:.1%}")
    k4.metric("Share where reuse wins (test)", f"{mt['reuse_win_share_test']:.0%}")
    from cirdesign.ml import predict_reuse_probability
    prob = predict_reuse_probability(ml, ctx, changed)
    st.progress(min(max(prob, 0.0), 1.0), text=f"Random Forest: probability that reuse beats recycling here = {prob:.0%}")
    ml1, ml2 = st.columns(2)
    ml1.plotly_chart(viz.fig_ml_parity(ml["parity"], mt["r2"], mt["mae"]), width="stretch")
    ml2.plotly_chart(viz.fig_importance(ml["importance"]), width="stretch")
    st.caption("The Random Forest imitates the physics-based model; it is a fast screening tool and is accurate only inside the sampled ranges. "
               f"Because reuse wins in {mt['reuse_win_share_test']:.0%} of sampled scenarios, accuracy must be read against that majority-class baseline.")

# ------------------------------------------------------------------ Assistant
with tabs[4]:
    st.markdown("#### Ask about this scenario")
    st.caption("Answers are computed from the model results for the current sidebar settings. The assistant does not invent numbers.")
    if "chat" not in st.session_state:
        st.session_state.chat = [("assistant", "Hello. I can explain the recommendation, break-even points, sensitivities and data sources.\n\n" + HELP)]
    sugg = ["Why is this strategy recommended?", "What is the break-even number of uses?", "Which parameter has the biggest influence?",
            "What happens if transport increases to 900 km?", "Would a rental model improve the result?", "Which design improvement should we prioritise?"]
    cols = st.columns(3)
    clicked = None
    for i, sq in enumerate(sugg):
        if cols[i % 3].button(sq, key=f"s{i}", width="stretch"):
            clicked = sq
    for role, text in st.session_state.chat:
        with st.chat_message(role):
            st.markdown(text)
    q = st.chat_input("Ask a question, e.g. what if the damage rate is 20%?") or clicked
    if q:
        st.session_state.chat.append(("user", q))
        with st.chat_message("user"):
            st.markdown(q)
        ans = llm_polish(q, Assistant(ctx, changed).answer(q))

        def stream():
            for tok in ans.split(" "):
                yield tok + " "
                time.sleep(0.012)
        with st.chat_message("assistant"):
            st.write_stream(stream())
        st.session_state.chat.append(("assistant", ans))

# ------------------------------------------------------------------ Data and methods
with tabs[5]:
    s = T["sources"]
    st.plotly_chart(viz.fig_provenance(s), width="stretch")
    used = s[s.used_in_model]
    n_lit = int(used.type.isin(["literature", "database"]).sum())
    st.warning(f"Only {n_lit} of {len(used)} model parameters come from literature or public databases. The other {len(used) - n_lit} are flagged assumptions "
               "(for example the damage rate, costs and design archetypes). Replace them with measured data before drawing real conclusions.")
    view = s[["parameter", "value", "low", "high", "unit", "type", "quality", "source", "year", "url", "note"]]
    st.dataframe(view, width="stretch", hide_index=True, column_config={"url": st.column_config.LinkColumn("link")})
    base = evaluate_all({"design": "B", "business_model": "rental", "event_km": 400.0, "n_uses": 2})
    vr = []
    for n in (2, 3, 4, 6, 10):
        t = evaluate_all({"design": "B", "business_model": "rental", "event_km": 400.0, "n_uses": n})
        vr.append({"label": f"{n} planned uses", "change": t.loc[["reuse", "repair"], "climate_per_use"].min() / t.loc["recycling", "climate_per_use"] - 1})
    lit = float(s.set_index("id").loc["validation_reuse_vs_recycling", "value"])
    st.plotly_chart(viz.fig_validation(pd.DataFrame(vr), lit), width="stretch")
    st.markdown((ROOT / "docs" / "METHODS.md").read_text(encoding="utf-8") if (ROOT / "docs" / "METHODS.md").exists() else "Methods note not built yet.")
