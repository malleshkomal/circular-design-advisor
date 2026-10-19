# Methods note: Circular Design Advisor

**An independent, literature-based decision prototype for reuse, repair, reprocessing, recycling and disposal of a modular exhibition-booth aluminium panel.** Inputs combine published values with flagged assumptions; results illustrate the method and are not findings about a real product.

## 1. Question and scope

Should a company reuse, repair, reprocess, recycle or dispose of an aluminium booth panel, and how does the answer change with the number of uses, transport distance, damage, business model and data uncertainty? The prototype follows a cirKPI-style chain: product and lifecycle data, scenario simulation, circular KPIs, optimisation and machine learning, a recommendation with explanation, and a chatbot that reads the calculated results.

## 2. Functional unit and system boundary

**Functional unit: one use of one panel at one exhibition event ("per use").** The boundary is cradle-to-grave: panel production, transport between depot, event and recycler, cleaning, repair or reprocessing, and end of life. Burdens of a panel's whole life are spread over the events it is expected to serve (use-based allocation):

`impact per use = (production + expected uses x per-event burden + end of life - recycling credit) / expected uses`

Three design archetypes (welded, screwed modular, clip-fit lightweight; assumed, not real products) and three business models (sale, rental, product-as-a-service) are compared across five strategies.

## 3. Model

- **Expected uses.** With planned uses N and a per-event probability p of losing the panel, `E[uses] = (1 - (1-p)^N) / p`. `p = 1 - (1 - damage loss) x redeployment probability`; the redeployment probability depends on the business model. Repair converts damaged but repairable panels back into service with the design's repairability.
- **Production.** `m x EF_mix + m x fabrication energy x grid factor`, with `EF_mix` blending primary and recycled aluminium by recycled content.
- **Transport.** `mass x distance x freight factor / load factor`, per leg.
- **End of life.** Recycling: sorting energy and transport, with a net-scrap credit `m x max(yield - recycled content, 0) x (EF_primary - EF_secondary)`. A cut-off option gives no credit. Disposal: waste-to-energy burden; metal recovery from ash earns no credit under net scrap because it is below the recycled content.
- **Cost proxy.** Panel purchase, handling, storage, labour, repair material and transport, minus scrap revenue (or plus a gate fee), multiplied by a business-model margin.

## 4. KPIs

| KPI | Definition |
|---|---|
| Climate impact per use | kg CO2e per use (above) |
| Circularity score | Simplified Material Circularity Indicator after Ellen MacArthur Foundation (2015): `MCI = max(0, 1 - LFI x 0.9 / X)`, LFI from virgin input and unrecoverable waste, X = expected uses |
| Material-recovery rate | End-of-life metal yield of the route (collection x remelting yield) |
| Reuse cycles | Expected uses minus one |
| Cost per use | EUR per use |
| Feasibility | Strategy base score x design suitability x distance penalty x organisational reliability |
| Virgin aluminium per use | kg of net virgin metal per use |

**Recommendation.** Scores are scaled 0-1 across the five strategies and combined as 0.50 environment, 0.25 circularity, 0.15 economics, 0.10 feasibility (editable). A transparent rule layer (at least 3 expected cycles, repairability at least 0.70, distance at most 300 km, with a fallback) runs in parallel; disagreements and near-ties are flagged.

## 5. Data

Inputs live in `data/literature_sources.csv`, with value, range, type, quality rating, source and URL.

| Input | Value | Source |
|---|---|---|
| Primary aluminium, Europe | 6.3 kg CO2e/kg (2023); range up to 14.8 | European Aluminium 2024; IAI 2023 |
| Recycled aluminium | about 0.5 kg CO2e/kg | Hydro 2021 |
| German electricity | 0.344 kg CO2e/kWh (2025 estimate) | Umweltbundesamt, 2026 |
| Road freight | 0.058 kg CO2e/t-km (full artic.); upper bound 0.562 | GLEC v3.0 via Climatiq; BEIS 2022 |
| Collection at end of life | 0.95 | European Aluminium (building products) |
| Aluminium price | about 3,100 USD/t | alcircle market report (year not re-verified) |

**Only 6 of 26 model parameters come from literature or public databases.** The other 20, including the damage rate, repair parameters, costs, design archetypes and business-model behaviour, are flagged assumptions. Benchmarks not used as inputs: AUMA's 70 % material-loop reference and the published 22 % lower net GWP for direct reuse versus recycling of an aluminium tent frame (Skejic et al., 2026).

## 6. Simulation, optimisation and machine learning

- **Simulation:** a factorial grid of design x strategy x business model x planned uses (1-15) x distance (50-900 km), 2,538 scenarios; plus uses, distance and 2-D gap maps.
- **Uncertainty:** 1,500 Monte Carlo draws from triangular distributions over every ranged parameter; one-at-a-time tornado analysis.
- **Optimisation:** exhaustive search of the discrete grid for the lowest `0.50 climate + 0.25 cost - 0.25 circularity` (each min-max normalised, circularity as is), keeping the best setting per design, strategy and business model. A Pareto front on climate, cost and feasibility shows the trade-offs.
- **Machine learning:** a Random Forest regressor (climate per use) and classifier (does a reuse route beat recycling?) trained on 2,500 Latin-hypercube scenarios, split by scenario. Held-out R² = 0.990, mean absolute error 2.4 kg CO2e per use; classifier accuracy 99 %, but reuse wins in 95 % of sampled scenarios, so accuracy must be read against that majority baseline. The model imitates the physics model; it adds speed, not knowledge.

## 7. Results (illustrative, baseline: design B, rental, 6 planned uses, 400 km)

| | Reuse | Repair | Reprocessing | Recycling | Disposal |
|---|---|---|---|---|---|
| Climate (kg CO2e/use) | 5.7 | 5.5 | 8.8 | 21.1 | 62.7 |
| Cost (EUR/use) | 48 | 46 | 57 | 151 | 178 |
| Circularity (0-1) | 0.92 | 0.93 | 0.93 | 0.64 | 0.33 |
| Expected events per panel | 4.5 | 5.2 | 4.8 | 1 | 1 |

Direct reuse is recommended (score 0.94; repair ties at 0.94). Reuse beats recycling on climate from two planned uses at all distances tested, because panel production dominates the footprint and is spread over more events. At one use, recycling is about 3 % better. Under cut-off crediting recycling rises to 63 kg CO2e per use. In 1,500 Monte Carlo draws a reuse route beat recycling in 100 % of draws at the baseline and in 91 % of a stress case (fragile design, sale model, two uses, 1,200 km). Transport only flips the result with small, partly loaded vehicles over very long distances. The largest uncertainties are the primary aluminium footprint, the end-of-life collection rate and fabrication energy.

**Plausibility check.** The published reduction for direct reuse versus recycling is about 22 %. The model reports 43 % to 80 % for 2 to 10 planned uses. The direction agrees, but the model's reuse benefit is clearly larger; the published case uses a different functional unit and system and probably credits recycling differently. This is a weakness, not a validation, and the dashboard says so.

## 8. Limitations

- Most inputs are assumptions; no measured damage, return or repair data exist here. Results are conditional on them.
- Per-use allocation favours reuse by construction; other allocation or credit methods give different numbers.
- Redeployment probabilities, margins, design archetypes and the feasibility score are modelling choices, not empirical values.
- Climate impact only; no toxicity, water or land use. Costs are a rough proxy with fixed prices.
- No Brightway or ecoinvent link; GLEC and electricity factors should be refreshed before real use.
- The chatbot is rule-based and grounded in the model output. An optional LLM wrapper only rephrases and is untested here.
- Market and behavioural factors (scrap price swings, customer acceptance, storage logistics) are not modelled.

## 9. Reproducibility

`python run_analysis.py` regenerates results, the ML model and the static animated report; `streamlit run app.py` starts the dashboard; `pytest` runs 16 tests.
