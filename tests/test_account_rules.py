"""Exact semantics of the hypothetical account-rule replay, at and around every threshold."""

import numpy as np
import pandas as pd
import pytest

from swingtrader.rules.account import AccountRules, replay

S0 = 100_000.0


def path(eq, worst=None, best=None, bal=None, active=None):
    n = len(eq)
    idx = pd.bdate_range("2024-01-01", periods=n)
    eq = np.asarray(eq, float)
    return pd.DataFrame({"equity": eq, "equity_worst": eq if worst is None else np.asarray(worst, float),
                         "equity_best": eq if best is None else np.asarray(best, float),
                         "balance": eq if bal is None else np.asarray(bal, float),
                         "active": np.ones(n, bool) if active is None else np.asarray(active, bool)}, index=idx)


def test_static_total_loss_breaches_exactly_at_floor_not_above():
    r = AccountRules(max_total_loss_pct=10)
    assert replay(path([95_000, 90_000.01]), r).status == "open"
    out = replay(path([95_000, 90_000.0]), r)
    assert out.status == "breached" and out.date == "2024-01-02" and "total loss" in out.reason


def test_intraday_vs_eod_daily_loss_check():
    p = path([100_000, 99_000], worst=[100_000, 94_900])        # dips 5.1% intraday, closes -1%
    assert replay(p, AccountRules(max_daily_loss_pct=5, daily_loss_check="intraday")).status == "breached"
    assert replay(p, AccountRules(max_daily_loss_pct=5, daily_loss_check="eod")).status == "open"


def test_daily_loss_resets_each_session():
    # -4% then -4% again: each day is below a 5% daily limit, cumulative 7.8% is not a daily breach
    out = replay(path([96_000, 92_160]), AccountRules(max_daily_loss_pct=5))
    # headroom day 1 = 5,000 - 4,000 = 1,000; day 2 = 5,000 - 3,840 = 1,160 -> minimum 1,000
    assert out.status == "open" and out.min_daily_headroom_usd == pytest.approx(1_000)


def test_daily_reference_balance_vs_equity_with_open_position():
    # day 1 closes with an unrealised loss (balance unchanged); day 2 drops another 3,000
    p = path([97_000, 94_000], bal=[100_000, 100_000])
    eq_ref = replay(p, AccountRules(max_daily_loss_pct=5, daily_loss_reference="equity", daily_loss_check="eod"))
    bal_ref = replay(p, AccountRules(max_daily_loss_pct=5, daily_loss_reference="balance", daily_loss_check="eod"))
    assert eq_ref.status == "open"                       # 97,000 -> 94,000 = 3,000 < 5,000
    assert bal_ref.status == "breached"                  # 100,000 -> 94,000 = 6,000 >= 5,000


def test_trailing_intraday_peak_counts_before_same_session_low():
    # session high reaches 106,000, same session low 99,900: floor = 106,000 - 6,000 = 100,000
    p = path([103_000], worst=[99_900], best=[106_000])
    out = replay(p, AccountRules(max_total_loss_pct=6, drawdown_type="trailing", trailing_basis="intraday"))
    assert out.status == "breached"
    eod = replay(p, AccountRules(max_total_loss_pct=6, drawdown_type="trailing", trailing_basis="eod_equity"))
    assert eod.status == "open"                          # EOD peak is only the starting balance


def test_trailing_lock_at_starting_balance():
    p = path([110_000, 104_500, 100_500], worst=[110_000, 104_500, 100_500], best=[110_000, 110_000, 104_500])
    plain = replay(p, AccountRules(max_total_loss_pct=6, drawdown_type="trailing", trailing_basis="eod_equity"))
    locked = replay(p, AccountRules(max_total_loss_pct=6, drawdown_type="trailing", trailing_basis="eod_equity",
                                    trailing_lock_at_start=True))
    # EOD peak 110,000 -> floor 104,000: day 2 (104,500) survives, day 3 (100,500) breaches
    assert plain.status == "breached" and plain.date == "2024-01-03"
    assert locked.status == "open"


def test_gap_through_floor_is_a_breach_on_that_session():
    p = path([99_000, 98_000, 97_000], worst=[99_000, 98_000, 89_000])
    out = replay(p, AccountRules(max_total_loss_pct=10))
    assert out.status == "breached" and out.date == "2024-01-03"


def test_target_needs_min_trading_days_and_consistency():
    eq = [101_000, 109_000, 110_500]
    act = [True, True, True]
    r = AccountRules(profit_target_pct=10)
    assert replay(path(eq, active=act), r).date == "2024-01-03"
    r = AccountRules(profit_target_pct=10, min_trading_days=4)
    assert replay(path(eq, active=act), r).status == "open"
    # one session made 8,000 of 10,500 profit (76%) -> fails a 50% consistency rule
    r = AccountRules(profit_target_pct=10, consistency_max_day_share_pct=50)
    assert replay(path(eq, active=act), r).status == "open"


def test_breach_checked_before_target_in_same_session():
    p = path([111_000], worst=[94_000])
    out = replay(p, AccountRules(profit_target_pct=10, max_daily_loss_pct=5))
    assert out.status == "breached"


def test_unknown_or_invalid_rule_keys_rejected():
    with pytest.raises(ValueError):
        AccountRules.from_dict({"max_daily_loss": 5})
    with pytest.raises(ValueError):
        AccountRules.from_dict({"drawdown_type": "relative"})
