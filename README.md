# Circular Design Advisor

**A literature-based, animated decision dashboard for reuse, repair, reprocessing, recycling and disposal of a modular exhibition-booth aluminium panel.**
It chains product and lifecycle data, per-use LCA, circularity KPIs, simulation, optimisation, machine learning and a chatbot that explains the calculated results.

> **Read this first.** Only 6 of 26 model inputs come from literature or public databases (European Aluminium, IAI, Hydro, Umweltbundesamt, GLEC). The other 20, including damage rate, costs, design archetypes and business-model behaviour, are flagged assumptions. Results illustrate the method, not a real product.

![Overview](docs/screenshots/01_overview.png)

## What is inside

| Layer | What it does |
|---|---|
| Data | `data/literature_sources.csv` (value, range, type, quality, source, URL), `product_data.csv`, `business_models.csv`, `strategies.csv` |
| LCA model | Climate, cost and circularity **per use** of one panel for five strategies; net-scrap or cut-off recycling credit |
| KPIs | Climate per use, circularity (simplified Material Circularity Indicator), material recovery, reuse cycles, cost, feasibility, virgin aluminium |
| Simulation | 2,538-scenario grid, uses and distance sweeps, percent-gap heatmaps |
| Uncertainty | 1,500-draw Monte Carlo over literature ranges, tornado chart |
| Optimisation | Exhaustive search of the decision space plus a Pareto front (climate, cost, feasibility) |
| Machine learning | Random Forest surrogate (R² 0.99) and a "does reuse beat recycling?" classifier |
| Recommendation | Weighted score (0.50 / 0.25 / 0.15 / 0.10) plus transparent rules; disagreements are flagged |
| Assistant | Rule-based chatbot grounded in the model output; optional LLM wrapper that may only rephrase |
| Dashboard | Streamlit with animated Plotly charts (press play), count-up KPI cards, streaming chat |

| Scenario lab (animated) | Trade-offs |
|---|---|
| ![Scenario lab](docs/screenshots/02_scenario_lab.png) | ![Trade-offs](docs/screenshots/03_tradeoffs.png) |

| Uncertainty and AI | Assistant |
|---|---|
| ![Uncertainty](docs/screenshots/04_uncertainty_ai.png) | ![Assistant](docs/screenshots/05_assistant.png) |

## Quick start

```bash
pip install -r requirements.txt
python run_analysis.py                # results/, ML model, docs/dashboard_static.html
streamlit run app.py                  # interactive dashboard
pytest                                # 16 tests
```

`docs/dashboard_static.html` is a self-contained animated export you can open in any browser without Python.
The first dashboard start trains the ML models if `results/ml_model.joblib` is missing (about 30 seconds).

Optional: set `ANTHROPIC_API_KEY` to let an LLM rephrase chatbot answers (`CHATBOT_LLM_MODEL` selects the model). The numbers always come from the model; this wrapper is untested in this repository.

## Illustrative baseline (design B, rental, 6 planned uses, 400 km)

| kg CO2e per use | Reuse | Repair | Reprocessing | Recycling | Disposal |
|---|---|---|---|---|---|
| Net scrap | 5.7 | 5.5 | 8.8 | 21.1 | 62.7 |

Reuse beats recycling from two planned uses because panel production dominates the footprint. It stops doing so only at one use, or with small partly loaded vehicles over very long distances. **Caveat:** the model shows a 43 to 80 % reuse benefit, while the one published comparison I found (aluminium tent frame, 2026) reports about 22 %. The direction agrees; the magnitude likely differs because of functional unit and credit method. See `docs/METHODS.pdf`.

## Sources

European Aluminium Environmental Profile Report 2024; International Aluminium Institute (2023 intensity); Hydro, carbon footprint of recycled aluminium (2021); Umweltbundesamt, CO2 per kWh electricity (2026); GLEC Framework v3.0 via Climatiq and BEIS 2022 freight factors; European Aluminium on end-of-life collection; AUMA resource-management guide (2026); Skejic et al., Buildings 16(13):2610 (2026). Full list with URLs and notes in `data/literature_sources.csv`.

## Limitations

Mostly assumed inputs; per-use allocation favours reuse; climate impact only; no Brightway or ecoinvent link yet; costs are a proxy; market and behavioural factors are not modelled; ML imitates the physics model and adds speed, not knowledge. Details in `docs/METHODS.md`.

## Next steps

Replace assumptions with measured damage and return data, add Brightway/ecoinvent foreground inventories, test other allocation methods, and extend beyond one component.
