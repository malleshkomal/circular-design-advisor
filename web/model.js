// Browser port of the per-use model. Edit here, then run: python scripts/build_dashboard.py
// JavaScript port of src/cirdesign/model.py, recommend.py and parts of analysis.py.
// Functional unit: one use of one panel at one exhibition event.
const STRATS = ["reuse", "repair", "reprocessing", "recycling", "disposal"];
const LABELS = { reuse: "Direct reuse", repair: "Repair and reuse", reprocessing: "Reprocessing", recycling: "Recycling", disposal: "Disposal" };
const WEIGHTS = { environment: 0.5, circularity: 0.25, economics: 0.15, feasibility: 0.1 };

function makeModel(D) {
  const byKey = (rows, k) => Object.fromEntries(rows.map(r => [r[k], r]));
  const designs = byKey(D.designs, "design"), strategies = byKey(D.strategies, "strategy"), bms = byKey(D.bms, "name");
  const central = {}, ranges = {};
  for (const s of D.sources) {
    if (!s.used_in_model) continue;
    central[s.id] = +s.value;
    if (s.low != null && s.high != null && s.low !== s.high) ranges[s.id] = [+s.low, +s.value, +s.high];
  }

  function expectedUses(n, p) {
    n = Math.max(Math.round(n), 1);
    return p <= 1e-12 ? n : (1 - Math.pow(1 - p, n)) / p;
  }
  const creditMass = (m, y, rc, credit) => credit === "cut_off" ? 0 : m * Math.max(y - rc, 0);

  function evaluate(c, P) {
    const d = designs[c.design], st = strategies[c.strategy], bm = bms[c.business_model];
    const m = d.mass_kg, rc = P.recycled_content;
    const efMix = (1 - rc) * P.ef_primary + rc * P.ef_secondary;
    const legEf = P.transport_ef / P.transport_load_factor;
    const leg = km => m / 1000 * km * legEf, legCost = km => m / 1000 * km * P.transport_cost;
    const priceKg = P.lme_price_usd_t * P.usd_eur / 1000;
    const production = m * efMix + m * P.e_fab * d.fab_factor * P.grid_ef;
    const panelCost = m * (priceKg + P.manuf_cost * d.cost_factor);
    const recov = P.collection_rate * P.melt_yield, delta = P.ef_primary - P.ef_secondary, grid = P.grid_ef;
    const single = st.family === "single";
    let U, N, pLoss, perEvent, perEventCost, y, eol, credit, eolCost, inv;
    let clean = 0, maint = 0, repairE = 0, repairMat = 0, repairEvents = 0;
    if (single) {
      U = 1; N = 1; pLoss = 1;
      perEvent = leg(c.event_km);
      perEventCost = legCost(c.event_km) + P.handling_cost;
      if (c.strategy === "recycling") {
        y = recov; eol = leg(c.eol_km) + m * P.sort_energy * grid;
        eolCost = legCost(c.eol_km) - m * y * priceKg * P.scrap_price_ratio;
      } else {
        y = P.disposal_recovery; eol = leg(c.eol_km) + m * P.disposal_ef;
        eolCost = legCost(c.eol_km) + m * P.gate_fee;
      }
      credit = creditMass(m, y, rc, c.credit) * delta;
    } else {
      N = Math.min(Math.round(c.n_uses), d.technical_lifetime_events);
      const dmg = P.damage_rate * d.damage_mult * bm.damage_mult * st.damage_factor;
      const lossDmg = st.repair ? dmg * (1 - d.repairability) : dmg;
      pLoss = 1 - (1 - lossDmg) * bm.redeploy;
      U = expectedUses(N, pLoss);
      repairEvents = st.repair ? dmg * d.repairability : 0;
      clean = m * P.e_clean * grid;
      maint = m * P.e_reprocess * grid * st.reprocess;
      repairE = repairEvents * m * P.e_repair * grid;
      repairMat = repairEvents * m * P.repair_share * efMix;
      perEvent = 2 * leg(c.event_km) + clean + maint + repairE + repairMat;
      let labour = st.labour_h * P.labour_rate * (st.repair ? repairEvents : 1);
      if (st.repair) labour += 0.05 * P.labour_rate;
      const repairMatCost = repairEvents * P.repair_share * m * (priceKg + P.manuf_cost * d.cost_factor);
      perEventCost = 2 * legCost(c.event_km) + P.handling_cost + P.storage_cost + labour + repairMatCost;
      y = recov; eol = leg(c.eol_km) + m * P.sort_energy * grid;
      credit = creditMass(m, y, rc, c.credit) * delta;
      eolCost = legCost(c.eol_km) - m * y * priceKg * P.scrap_price_ratio;
    }
    const total = production + U * perEvent + eol - credit;
    const totalCost = panelCost + U * perEventCost + eolCost;
    const cm = creditMass(m, y, rc, c.credit);
    const virgin = Math.max(m * (1 - rc) - cm, 0);
    const V = m * (1 - rc), W = m * (1 - y);
    const mci = Math.max(0, 1 - (V + W) / (2 * m) * 0.9 / Math.max(U, 1));
    const suit = single ? 1 : (st.repair ? 0.5 + 0.5 * d.repairability : 0.5 + 0.5 * d.disassembly);
    const dist = Math.max(0, 1 - c.event_km / 2000);
    const org = single ? 1 : 0.6 + 0.4 * bm.redeploy;
    const legs = single ? 1 : 2;
    const tkmEvents = U * legs * m / 1000 * c.event_km;
    inv = [ // [stage, flow, unit, amount per life, kg CO2e per unit]
      ["Production", "Primary aluminium, ingot", "kg", m * (1 - rc), P.ef_primary],
      ["Production", "Secondary aluminium", "kg", m * rc, P.ef_secondary],
      ["Production", "Electricity, fabrication", "kWh", m * P.e_fab * d.fab_factor, grid],
      ["Use", "Road freight, events", "t·km", tkmEvents, legEf],
      ["Use", "Electricity, cleaning and inspection", "kWh", single ? 0 : U * m * P.e_clean, grid],
      ["Use", "Electricity, reprocessing", "kWh", single ? 0 : U * m * P.e_reprocess * st.reprocess, grid],
      ["Use", "Electricity, repair", "kWh", U * repairEvents * m * P.e_repair, grid],
      ["Use", "Repair parts, primary aluminium", "kg", U * repairEvents * m * P.repair_share * (1 - rc), P.ef_primary],
      ["Use", "Repair parts, secondary aluminium", "kg", U * repairEvents * m * P.repair_share * rc, P.ef_secondary],
      ["End of life", "Road freight, to end of life", "t·km", m / 1000 * c.eol_km, legEf],
      ["End of life", "Electricity, dismantling and sorting", "kWh", c.strategy === "disposal" ? 0 : m * P.sort_energy, grid],
      ["End of life", "Waste-to-energy treatment", "kg", c.strategy === "disposal" ? m : 0, P.disposal_ef],
      ["Credit", "Avoided primary aluminium", "kg", -cm, delta],
    ];
    return {
      expected_uses: U, reuse_cycles: U - 1, planned_uses: N, p_loss: pLoss,
      climate_per_use: total / U, cost_per_use: totalCost / U * (1 + bm.margin),
      circularity: mci, material_recovery: y, virgin_al_per_use: virgin / U,
      feasibility: st.feasibility_base * suit * dist * org, mass_kg: m,
      breakdown: {
        production: production / U,
        transport: legs * leg(c.event_km),
        cleaning: single ? 0 : clean + maint + repairE + repairMat,
        eol: eol / U,
        credit: -credit / U,
      },
      recovered_kg: m * y, lost_kg: m * (1 - y), virgin_in_kg: V, recycled_in_kg: m * rc,
      inventory: inv,
    };
  }

  function evaluateAll(ctx, P) {
    const out = {};
    for (const s of STRATS) out[s] = evaluate({ ...ctx, strategy: s }, P);
    return out;
  }

  function norm(vals, higherBetter) {
    const mn = Math.min(...vals), mx = Math.max(...vals), span = mx - mn;
    if (span < 1e-12) return vals.map(() => 0.5);
    return vals.map(v => { const z = (v - mn) / span; return higherBetter ? z : 1 - z; });
  }

  function score(t, w = WEIGHTS) {
    const env = norm(STRATS.map(s => t[s].climate_per_use), false);
    const eco = norm(STRATS.map(s => t[s].cost_per_use), false);
    const tot = w.environment + w.circularity + w.economics + w.feasibility;
    const out = {};
    STRATS.forEach((s, i) => {
      const circ = Math.min(1, Math.max(0, t[s].circularity)), feas = Math.min(1, Math.max(0, t[s].feasibility));
      out[s] = { environment: env[i], circularity: circ, economics: eco[i], feasibility: feas,
        score: (env[i] * w.environment + circ * w.circularity + eco[i] * w.economics + feas * w.feasibility) / (tot || 1) };
    });
    return out;
  }

  function ruleBased(ctx, t, sc) {
    const rep = designs[ctx.design].repairability;
    const reuseBest = ["reuse", "repair", "reprocessing"].reduce((a, b) => sc[b].score > sc[a].score ? b : a);
    const cyc = t[reuseBest].reuse_cycles;
    const trace = [
      { rule: "R1", test: "Expected reuse cycles ≥ 3", value: cyc, threshold: 3, pass: cyc >= 3 },
      { rule: "R2", test: "Repairability ≥ 0.70", value: rep, threshold: 0.7, pass: rep >= 0.7 },
      { rule: "R3", test: "Event transport distance ≤ 300 km", value: ctx.event_km, threshold: 300, pass: ctx.event_km <= 300 },
    ];
    if (trace.every(x => x.pass)) return { rule: reuseBest, trace };
    const gain = 1 - t[reuseBest].climate_per_use / t.recycling.climate_per_use;
    const ok = cyc >= 1.5 && gain >= 0.15;
    trace.push({ rule: "R4", test: "Fallback: reuse ≥ 15 % lower climate than recycling and ≥ 1.5 cycles", value: gain, threshold: 0.15, pass: ok, pct: true });
    if (ok) return { rule: reuseBest, trace };
    return { rule: t.recycling.climate_per_use < t.disposal.climate_per_use ? "recycling" : "disposal", trace };
  }

  function recommend(ctx, P, w) {
    const t = evaluateAll(ctx, P), sc = score(t, w);
    const best = STRATS.reduce((a, b) => sc[b].score > sc[a].score ? b : a);
    const { rule, trace } = ruleBased(ctx, t, sc);
    const sorted = STRATS.map(s => sc[s].score).sort((a, b) => b - a);
    const warns = [];
    if (rule !== best) warns.push(`The transparent rules point to ${LABELS[rule]}, the weighted score to ${LABELS[best]}: the two methods weigh trade-offs differently.`);
    if (t[best].climate_per_use > 0 && Math.abs(sorted[0] - sorted[1]) < 0.03) warns.push("The top two options are within 0.03 score points: treat the ranking as unclear.");
    return { t, sc, best, rule, trace, warns };
  }

  function breakEvenUses(ctx, P, strat = "reuse", nMax = 40) {
    for (let n = 1; n <= nMax; n++) {
      const t = evaluateAll({ ...ctx, n_uses: n }, P);
      if (t[strat].climate_per_use < t.recycling.climate_per_use - 1e-9) return n;
    }
    return null;
  }

  // seeded PRNG (mulberry32) + triangular sampling
  function rng(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  function tri(u, a, c, b) { const f = (c - a) / (b - a); return u < f ? a + Math.sqrt(u * (b - a) * (c - a)) : b - Math.sqrt((1 - u) * (b - a) * (b - c)); }

  function monteCarlo(ctx, P, n = 1000, seed = 42) {
    const r = rng(seed), out = STRATS.reduce((o, s) => (o[s] = [], o), {});
    for (let i = 0; i < n; i++) {
      const p = { ...P };
      for (const [k, [lo, mo, hi]] of Object.entries(ranges)) {
        // scale the range around the user's current value so edits carry through
        const ratio = P[k] / mo;
        p[k] = tri(r(), lo * ratio, P[k], hi * ratio);
      }
      const t = evaluateAll(ctx, p);
      for (const s of STRATS) out[s].push(t[s].climate_per_use);
    }
    return out;
  }

  function tornado(ctx, P, strat = "reuse", ref = "recycling") {
    const base = evaluateAll(ctx, P), baseGap = base[strat].climate_per_use - base[ref].climate_per_use;
    const rows = [];
    for (const [k, [lo, , hi]] of Object.entries(ranges)) {
      const g = [lo, hi].map(v => { const t = evaluateAll(ctx, { ...P, [k]: v }); return t[strat].climate_per_use - t[ref].climate_per_use; });
      rows.push({ parameter: k, low_gap: g[0], high_gap: g[1], base_gap: baseGap, swing: Math.abs(g[1] - g[0]) });
    }
    return rows.sort((a, b) => b.swing - a.swing);
  }

  // Full factorial grid: design x strategy x business model x planned uses x event distance (analysis.simulate_grid)
  function simulateGrid(ctx, P, nMax = 15, kms = [50, 150, 300, 500, 700, 900]) {
    const rows = [];
    for (const d of Object.keys(designs)) for (const s of STRATS) for (const b of Object.keys(bms)) for (const km of kms) {
      const single = strategies[s].family === "single";
      for (let n = 1; n <= (single ? 1 : nMax); n++) {
        const r = evaluate({ ...ctx, design: d, strategy: s, business_model: b, n_uses: n, event_km: km }, P);
        rows.push({ design: d, strategy: s, business_model: b, n_uses: n, event_km: km, climate_per_use: r.climate_per_use,
          cost_per_use: r.cost_per_use, circularity: r.circularity, feasibility: r.feasibility, expected_uses: r.expected_uses });
      }
    }
    return rows;
  }

  // Non-dominated rows, minimising climate, cost and infeasibility (analysis.pareto_front)
  function paretoFront(rows) {
    const v = rows.map(r => [r.climate_per_use, r.cost_per_use, 1 - r.feasibility]);
    const keep = rows.map(() => true);
    for (let i = 0; i < rows.length; i++) {
      if (!keep[i]) continue;
      for (let j = 0; j < rows.length; j++) {
        if (j !== i && v[j].every((x, k) => x <= v[i][k]) && v[j].some((x, k) => x < v[i][k])) { keep[i] = false; break; }
      }
    }
    return rows.filter((_, i) => keep[i]);
  }

  // Exhaustive search with objective = w_clim*norm(climate) + w_cost*norm(cost) - w_circ*circularity (analysis.optimise)
  function optimise(rows, wClim = 0.5, wCost = 0.25, wCirc = 0.25, top = 10) {
    const nz = k => { const a = rows.map(r => r[k]), mn = Math.min(...a), mx = Math.max(...a); return x => (x - mn) / (mx - mn + 1e-12); };
    const nc = nz("climate_per_use"), nk = nz("cost_per_use");
    const g = rows.map(r => ({ ...r, objective: wClim * nc(r.climate_per_use) + wCost * nk(r.cost_per_use) - wCirc * r.circularity }))
      .sort((a, b) => a.objective - b.objective);
    const seen = new Set(), out = [];
    for (const r of g) { const key = r.design + r.strategy + r.business_model; if (seen.has(key)) continue; seen.add(key); out.push(r); if (out.length === top) break; }
    return out;
  }

  // % change in climate per use of the best reuse route vs recycling (negative = reuse better) (analysis.gap_map)
  function gapMap(ctx, P, ns, kms) {
    return ns.map(n => kms.map(km => {
      const t = evaluateAll({ ...ctx, n_uses: n, event_km: km }, P);
      return (Math.min(t.reuse.climate_per_use, t.repair.climate_per_use, t.reprocessing.climate_per_use) / t.recycling.climate_per_use - 1) * 100;
    }));
  }

  return { simulateGrid, paretoFront, optimise, gapMap, central, ranges, designs, strategies, bms, evaluate, evaluateAll, score, recommend, breakEvenUses, monteCarlo, tornado, expectedUses };
}
if (typeof module !== "undefined") module.exports = { makeModel, STRATS, LABELS, WEIGHTS };
