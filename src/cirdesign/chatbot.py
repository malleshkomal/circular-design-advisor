"""Grounded assistant: answers only from computed results. No invented numbers.

Every answer is built from the model outputs for the current context. If an optional LLM is configured
(ANTHROPIC_API_KEY), it may only rephrase the already computed answer; it never supplies numbers.
"""
from __future__ import annotations

import os
import re

import pandas as pd

from .analysis import break_even_distance, break_even_uses, tornado
from .data import load_all
from .model import DEFAULT_CONTEXT, evaluate_all
from .recommend import LABELS, recommend

HELP = ("I can explain this scenario using the calculated results. Try:\n"
        "- *Why is this strategy recommended?*\n- *What is the break-even number of uses?*\n"
        "- *Which parameter has the biggest influence?*\n- *What happens if transport increases to 900 km?*\n"
        "- *What if the damage rate is 20%?*\n- *Would a rental model improve the result?*\n"
        "- *Which design improvement should we prioritise?*\n- *Where does the data come from?*")


class Assistant:
    def __init__(self, ctx=None, params=None):
        self.ctx = {**DEFAULT_CONTEXT, **(ctx or {})}
        self.params = params or {}
        self.T = load_all()

    # -------- helpers
    def _table(self, ctx=None, params=None):
        return evaluate_all(ctx or self.ctx, params if params is not None else self.params)

    def _best_reuse(self, t):
        return t.loc[["reuse", "repair", "reprocessing"], "climate_per_use"].idxmin()

    @staticmethod
    def _num(pattern, q):
        m = re.search(pattern, q)
        return float(m.group(1).replace(",", ".")) if m else None

    # -------- intents
    def why(self):
        rec = recommend(self.ctx, self.params)
        t = rec.score_table
        s = rec.strategy
        lines = [f"**Recommendation: {rec.label}.**"] + [f"- {r}" for r in rec.reasons]
        lines.append(f"- Ranking by weighted score: " + ", ".join(f"{LABELS[i]} {v:.2f}" for i, v in t.score.sort_values(ascending=False).items()) + ".")
        if s in ("reuse", "repair", "reprocessing"):
            n = break_even_uses({**self.ctx}, self.params, s)
            if n:
                lines.append(f"- It beats recycling on climate once a panel is planned for at least {n} uses (at {self.ctx['event_km']:.0f} km).")
        for w in rec.warnings:
            lines.append(f"- Note: {w}")
        lines.append("\n*Based on the current sidebar settings. Main uncertainties: damage rate, return logistics and the aluminium supply footprint.*")
        return "\n".join(lines)

    def break_even(self):
        out = []
        for s in ("reuse", "repair", "reprocessing"):
            n = break_even_uses(self.ctx, self.params, s)
            out.append(f"- {LABELS[s]}: {'from ' + str(n) + ' planned uses' if n else 'does not beat recycling within 40 uses'}")
        km = break_even_distance(self.ctx, self.params, self.ctx["strategy"] if self.ctx["strategy"] in ("reuse", "repair", "reprocessing") else "reuse")
        out.append(f"- Distance: {'recycling overtakes reuse above about ' + str(km) + ' km' if km else 'reuse stays ahead of recycling at all distances tested (up to 5,000 km)'} for the current assumptions.")
        return "**Break-even against single-use recycling (climate per use):**\n" + "\n".join(out) + \
               "\n\nThe break-even is low because panel production dominates the footprint, so spreading it over a second use already helps. It rises sharply if panels are often damaged or lost."

    def influence(self):
        tor = tornado(self.ctx)
        top = tor.head(4)
        names = dict(zip(self.T["sources"].id, self.T["sources"].parameter))
        rows = [f"- **{names.get(r.parameter, r.parameter)}**: moves the reuse-minus-recycling gap by {r.swing:.1f} kg CO2e per use across its literature range" for r in top.itertuples()]
        flips = (tor[["low_gap", "high_gap"]] > 0).any(axis=1).sum()
        tail = ("No single parameter flips the preference on its own for this scenario." if flips == 0 else
                f"{flips} parameter(s) flip the preference at one end of their range.")
        return "**Most influential parameters (one at a time):**\n" + "\n".join(rows) + "\n\n" + tail

    def what_if(self, q):
        ctx, params, notes = dict(self.ctx), dict(self.params), []
        if (km := self._num(r"(\d[\d.,]*)\s*km", q)) is not None:
            ctx["event_km"] = km; notes.append(f"event distance {km:.0f} km")
        if (n := self._num(r"(\d+)\s*(?:uses|events|cycles|times)", q)) is not None:
            ctx["n_uses"] = int(n); notes.append(f"{int(n)} planned uses")
        if (dm := self._num(r"damage[^0-9]*(\d[\d.,]*)\s*%", q)) is not None:
            params["damage_rate"] = dm / 100; notes.append(f"damage rate {dm:.0f}%")
        if "cut-off" in q or "cut off" in q:
            ctx["credit"] = "cut_off"; notes.append("cut-off crediting")
        for b in self.T["business_models"].index:
            if b in q or self.T["business_models"].loc[b, "label"].lower() in q:
                ctx["business_model"] = b; notes.append(f"business model {b}")
        if not notes:
            return None
        old, new = self._table(), self._table(ctx, params)
        s_old = recommend(self.ctx, self.params).strategy
        s_new = recommend(ctx, params).strategy
        best_old, best_new = self._best_reuse(old), self._best_reuse(new)
        lines = [f"**What if: {', '.join(notes)}**",
                 f"- Climate per use, best reuse route ({LABELS[best_new]}): {new.loc[best_new, 'climate_per_use']:.1f} kg CO2e (before: {old.loc[best_old, 'climate_per_use']:.1f}).",
                 f"- Recycling: {new.loc['recycling', 'climate_per_use']:.1f} kg CO2e (before: {old.loc['recycling', 'climate_per_use']:.1f}).",
                 f"- Cost per use, best reuse route: {new.loc[best_new, 'cost_per_use']:.0f} EUR; recycling: {new.loc['recycling', 'cost_per_use']:.0f} EUR.",
                 f"- Recommendation: **{LABELS[s_new]}**" + ("" if s_new == s_old else f" (changed from {LABELS[s_old]})") + "."]
        if new.loc[best_new, "climate_per_use"] > new.loc["recycling", "climate_per_use"]:
            lines.append("- Under these assumptions recycling has the lower climate impact; reuse only wins on other criteria, if at all.")
        return "\n".join(lines)

    def business(self):
        rows = []
        for b in self.T["business_models"].index:
            c = {**self.ctx, "business_model": b}
            t = self._table(c)
            br = self._best_reuse(t)
            rows.append((b, br, t.loc[br, "climate_per_use"], t.loc[br, "cost_per_use"], t.loc[br, "expected_uses"]))
        lines = [f"- {self.T['business_models'].loc[b, 'label']}: {LABELS[br]}, {c:.1f} kg CO2e and {e:.0f} EUR per use, {u:.1f} events per panel" for b, br, c, e, u in rows]
        best = min(rows, key=lambda r: r[2])[0]
        return "**Business model comparison (best reuse route each):**\n" + "\n".join(lines) + \
               f"\n\nRental or service models help because the provider keeps control of return and maintenance, which raises the redeployment probability. {self.T['business_models'].loc[best, 'label']} gives the lowest climate impact here. Redeployment probabilities and margins are assumptions, not literature values."

    def design_priority(self):
        base = self._table()
        br = self._best_reuse(base)
        b = base.loc[br, "climate_per_use"]
        levers = []
        for name, params in (("Cut the damage rate by half", {"damage_rate": self.params.get("damage_rate", 0.08) / 2}),
                             ("Source low-carbon primary aluminium (4.0 kg CO2e/kg, hydropower-based)", {"ef_primary": 4.0}),
                             ("Cut fabrication energy by a third", {"e_fab": 1.0}),
                             ("Cleaner electricity (0.10 kg CO2e/kWh)", {"grid_ef": 0.10}),
                             ("Raise recycled content to 60%", {"recycled_content": 0.60})):
            t = self._table(self.ctx, {**self.params, **params})
            bb = self._best_reuse(t)
            levers.append((name, t.loc[bb, "climate_per_use"] - b))
        levers.sort(key=lambda x: x[1])
        designs = []
        for d in self.T["designs"].index:
            t = self._table({**self.ctx, "design": d})
            bd = self._best_reuse(t)
            designs.append(f"{d} ({self.T['designs'].loc[d, 'name']}): {t.loc[bd, 'climate_per_use']:.1f} kg CO2e, {t.loc[bd, 'cost_per_use']:.0f} EUR per use")
        return ("**Design and supply levers, ranked by climate effect per use** (best reuse route):\n" +
                "\n".join(f"- {n}: {d:+.1f} kg CO2e" for n, d in levers) +
                "\n\n**Design archetypes (assumed designs):**\n" + "\n".join(f"- {x}" for x in designs) +
                "\n\nThe lightest panel wins on climate because production dominates, but it is also the most fragile in the assumptions; check damage data before choosing it.")

    def sources(self):
        s = self.T["sources"]
        used = s[s.used_in_model]
        n_lit = int(used.type.isin(["literature", "database"]).sum())
        key = s[s.id.isin(["ef_primary", "ef_secondary", "grid_ef", "transport_ef", "collection_rate"])]
        lines = [f"- {r.parameter}: {r.value:g} {r.unit} ({r.source}, {r.year})" for r in key.itertuples()]
        return (f"**Data provenance:** {n_lit} of {len(used)} model parameters come from literature or public databases; "
                f"the other {len(used) - n_lit} are labelled assumptions (damage rate, costs, design archetypes, business-model behaviour).\n" +
                "\n".join(lines) + "\n\nSee the Data & methodology page for every source and URL.")

    # -------- routing
    def answer(self, question: str) -> str:
        q = question.lower().strip()
        if not q:
            return HELP
        w = self.what_if(q) if re.search(r"what (happens )?if|increase|decrease|reduce|\d\s*km|damage|cut-?off|if the|suppose|assume", q) else None
        if w:
            return w
        if re.search(r"break.?even|how many uses|number of uses|how often", q):
            return self.break_even()
        if re.search(r"influen|sensitiv|biggest|most important|which parameter|uncertain", q):
            return self.influence()
        if re.search(r"rental|rent|service|business model|sale", q):
            return self.business()
        if re.search(r"design|improve|priorit|lever|reduce impact", q):
            return self.design_priority()
        if re.search(r"source|data|literature|where.*from|database|reference|valid", q):
            return self.sources()
        if re.search(r"why|recommend|explain|best|which strateg|should", q):
            return self.why()
        return "I did not match that to a calculated result.\n\n" + HELP


def llm_polish(question: str, grounded_answer: str) -> str:
    """Optional: let an LLM rephrase the grounded answer. Returns the original text if unavailable."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return grounded_answer
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=os.environ.get("CHATBOT_LLM_MODEL", "claude-sonnet-4-5"), max_tokens=600,
            system="Rephrase the supplied analysis for a non-expert. Use ONLY the numbers and statements in it. "
                   "Do not add data. Keep assumptions and uncertainties. If something is missing, say it is unavailable.",
            messages=[{"role": "user", "content": f"Question: {question}\n\nGrounded analysis:\n{grounded_answer}"}])
        return msg.content[0].text
    except Exception:
        return grounded_answer
