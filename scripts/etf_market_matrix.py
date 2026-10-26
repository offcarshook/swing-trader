"""Frozen SPY/QQQ book applied to each ETF separately + stacking ablation on the TRAIN window.

    python scripts/etf_market_matrix.py  -> results/etf/study/market_matrix.json

Nothing here selects anything: it shows whether the book generalises beyond the instruments it
was built on (it is not assumed to). Windows per ETF are the ETF's own data inside each period.
"""

import json

from swingtrader.config import load_config, resolve
from swingtrader.etf.analytics import report
from swingtrader.etf.data import BASKET, audit, load_basket
from swingtrader.etf.research import buy_hold
from swingtrader.etf.study import _params, _risk, stacking_ablation
from swingtrader.etf.engine import simulate

cfg = load_config(resolve("config/etf.yaml"))
sel = json.loads((resolve("results/etf/study") / "train_selection_corrected.json").read_text())
params = _params(sel)
bars = load_basket(resolve("data/raw/etf_full"), BASKET + ["XLV", "DBC"])
aud = audit(bars)
K = ("trades", "profit_factor", "expectancy_r", "total_return_pct", "cagr_pct", "max_dd_pct", "sharpe", "reliability")
out = {"selection": sel["selected"], "per_instrument": {}}
for s, b in bars.items():
    row = {"data": {k: aud[s][k] for k in ("first", "last", "rows", "price_basis")}}
    for name, (a, e) in (("train_2008_2020", ("2008-01-01", "2020-12-31")),
                         ("after_2020_viewed", ("2021-01-01", "2026-12-31"))):
        r = simulate({s: b}, params, a, e, _risk(cfg))
        x = report(r)
        row[name] = {k: x.get(k) for k in K} | {"window": x.get("window")}
        bh = buy_hold(b, a, e)
        row[name]["buy_hold_total_return_pct"] = bh["total_return_pct"] if bh else None
        r2 = simulate({s: b}, params, a, e, _risk(cfg, 2.0))
        row[name]["profit_factor_2x_costs"] = report(r2).get("profit_factor")
    out["per_instrument"][s] = row
spyqqq = {s: bars[s] for s in ("SPY", "QQQ")}
out["stacking_ablation_train_2008_2020"] = stacking_ablation(cfg, spyqqq, params, "2008-01-01", "2020-12-31")
(resolve("results/etf/study") / "market_matrix.json").write_text(json.dumps(out, indent=1, default=str))
for s, r in out["per_instrument"].items():
    t, v = r["train_2008_2020"], r["after_2020_viewed"]
    print(f"{s:4s} {r['data']['first']}..{r['data']['last']}  train: n={t['trades']} PF={t['profit_factor']} "
          f"PF2x={t['profit_factor_2x_costs']} ret={t['total_return_pct']}% bh={t['buy_hold_total_return_pct']}% | "
          f"2021+: n={v['trades']} PF={v['profit_factor']} ret={v['total_return_pct']}%")
for k, v in out["stacking_ablation_train_2008_2020"]["variants"].items():
    print(f"{k:45s}", {kk: v[kk] for kk in ("trades", "cagr_pct", "max_dd_pct", "sharpe", "avg_gross_exposure_pct", "cagr_per_100pct_avg_gross")})
