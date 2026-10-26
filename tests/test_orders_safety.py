import datetime as dt

import pandas as pd
import pytest

from swingtrader.orders import DuplicateOrderError, LiveTradingDisabledError, OrderGuard, OrderIntent
from swingtrader.safety import check_latest_bar, kill_switch_active, safe_shutdown


def intent(**kw):
    base = dict(strategy="s", instrument="MES", session="2024-01-02", purpose="entry", side=1, qty=1,
                order_type="market")
    base.update(kw)
    return OrderIntent(**base)


def test_client_id_is_deterministic():
    assert intent().client_id == intent().client_id
    assert intent().client_id != intent(session="2024-01-03").client_id
    assert intent().client_id != intent(purpose="exit", side=-1).client_id


def test_duplicate_prevention_persists(tmp_path):
    f = tmp_path / "orders.json"
    g = OrderGuard(f)
    g.submit(intent(), True, lambda i: "ok")
    with pytest.raises(DuplicateOrderError):
        g.submit(intent(), True, lambda i: "ok")
    g2 = OrderGuard(f)  # restart: state reloaded
    with pytest.raises(DuplicateOrderError):
        g2.check(intent(), True)


def test_failed_send_not_recorded(tmp_path):
    g = OrderGuard(tmp_path / "o.json")

    def boom(_):
        raise ConnectionError("broker down")
    with pytest.raises(ConnectionError):
        g.submit(intent(), True, boom)
    g.submit(intent(), True, lambda i: "ok")  # retry allowed


def test_live_is_refused():
    with pytest.raises(LiveTradingDisabledError):
        OrderGuard().check(intent(), broker_is_paper=False)


def test_session_order_cap():
    g = OrderGuard(max_orders_per_session=2)
    g.submit(intent(purpose="entry"), True, lambda i: 1)
    g.submit(intent(purpose="stop", order_type="stop", stop_price=3990.0, side=-1), True, lambda i: 1)
    with pytest.raises(DuplicateOrderError):
        g.submit(intent(purpose="exit", side=-1), True, lambda i: 1)


def test_intent_validation():
    with pytest.raises(ValueError):
        intent(qty=0).validate()
    with pytest.raises(ValueError):
        intent(order_type="stop").validate()


def _sess(day="2024-01-02", **over):
    row = {"open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "n_rth_bars": 390, **over}
    return pd.DataFrame([row], index=pd.DatetimeIndex([day]))


def test_data_checks():
    assert check_latest_bar(_sess(), dt.date(2024, 1, 3)).ok
    assert not check_latest_bar(_sess(), dt.date(2024, 1, 12)).ok          # stale
    assert not check_latest_bar(_sess(n_rth_bars=100), dt.date(2024, 1, 3)).ok
    assert not check_latest_bar(_sess(high=10.5), dt.date(2024, 1, 3)).ok  # high < close
    assert not check_latest_bar(_sess(close=float("nan")), dt.date(2024, 1, 3)).ok
    assert not check_latest_bar(pd.DataFrame(), dt.date(2024, 1, 3)).ok


def test_kill_switch(tmp_path):
    f = tmp_path / "KILL_SWITCH"
    assert not kill_switch_active(f)
    f.touch()
    assert kill_switch_active(f)


def test_safe_shutdown_runs_every_step():
    calls = []

    def bad():
        calls.append("cancel")
        raise RuntimeError("x")
    with pytest.raises(RuntimeError):
        safe_shutdown(bad, lambda: calls.append("persist"), flatten=lambda: calls.append("flatten"))
    assert calls == ["cancel", "flatten", "persist"]
