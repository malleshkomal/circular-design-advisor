"""The offline dashboard (web/model.js) must stay in sync with the data and reproduce the Python model."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_dashboard import OUT, model_data, render  # noqa: E402
from cirdesign.analysis import break_even_uses  # noqa: E402
from cirdesign.model import evaluate_all  # noqa: E402
from cirdesign.recommend import recommend  # noqa: E402

CASES = [
    dict(design="B", business_model="rental", n_uses=6, event_km=400, eol_km=100, credit="net_scrap"),
    dict(design="A", business_model="sale", n_uses=3, event_km=800, eol_km=250, credit="cut_off"),
    dict(design="C", business_model="paas", n_uses=12, event_km=50, eol_km=20, credit="net_scrap"),
    dict(design="B", business_model="rental", n_uses=1, event_km=1500, eol_km=100, credit="net_scrap"),
]

JS = """
const fs = require("fs");
const { makeModel, STRATS } = require(process.argv[1]);
const M = makeModel(JSON.parse(fs.readFileSync(0, "utf8")).data);
const cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(c => {
  const r = M.recommend(c, M.central);
  return { t: r.t, score: Object.fromEntries(STRATS.map(s => [s, r.sc[s].score])), best: r.best, rule: r.rule,
           be: M.breakEvenUses(c, M.central) };
})));
"""


def test_built_dashboard_is_up_to_date():
    assert OUT.exists(), "run python scripts/build_dashboard.py"
    assert OUT.read_text(encoding="utf-8") == render(), "outputs/dashboard_offline.html is stale: run python scripts/build_dashboard.py"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_js_model_matches_python():
    out = subprocess.run(["node", "-e", JS, str(ROOT / "web" / "model.js"), json.dumps(CASES)],
                         input=json.dumps({"data": model_data()}), capture_output=True, text=True, check=True)
    js = json.loads(out.stdout)
    for c, j in zip(CASES, js):
        rec, t = recommend(c), evaluate_all(c)
        assert j["best"] == rec.strategy and j["rule"] == rec.rule_strategy
        assert j["be"] == break_even_uses(c)
        for s in t.index:
            for k in t.columns:
                assert j["t"][s][k] == pytest.approx(t.loc[s, k], rel=1e-9, abs=1e-12), (c, s, k)
            assert j["score"][s] == pytest.approx(rec.score_table.loc[s, "score"], rel=1e-9, abs=1e-12)
