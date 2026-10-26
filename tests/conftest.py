import numpy as np
import pandas as pd
import pytest

from swingtrader.config import load_config
from swingtrader.contracts import SPECS
from swingtrader.costs import CostModel
from swingtrader.risk import RiskLimits, RiskManager


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def spec():
    return SPECS["MES"]


@pytest.fixture
def costs(spec, cfg):
    return CostModel.from_config(spec, cfg["costs"])


@pytest.fixture
def zero_costs(spec):
    return CostModel(spec, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


@pytest.fixture
def limits(cfg):
    return RiskLimits.from_config(cfg["risk"])


@pytest.fixture
def risk(limits, spec, costs):
    return RiskManager(limits, spec, costs)


def make_bars(closes, start="2021-01-04", spread=2.0, gap=0.0) -> pd.DataFrame:
    """Synthetic session bars with all engine columns. Business days, flat intraday ranges."""
    closes = np.asarray(closes, dtype=float)
    idx = pd.bdate_range(start, periods=len(closes))
    prev = np.r_[closes[0], closes[:-1]]
    open_ = prev + gap
    rth_open = open_
    high = np.maximum.reduce([open_, closes]) + spread
    low = np.minimum.reduce([open_, closes]) - spread
    df = pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": closes, "volume": 1000,
        "rth_open": rth_open, "rth_close": closes,
        "pre_high": np.maximum(open_, rth_open) + 0.0, "pre_low": np.minimum(open_, rth_open) - 0.0,
        "post_high": high, "post_low": low,
        "n_bars": 1380, "n_rth_bars": 390, "max_gap_min": 1.0, "merged_holiday": False,
        "short_session": False,
    }, index=idx)
    df.index.name = "session"
    return df
