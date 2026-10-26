# Hypothetical account-rule simulator — semantics, tests, replays

**Scope.** `swingtrader/rules/account.py` replays a chronological equity path against configurable,
HYPOTHETICAL limits. It does not model, connect to, or claim compatibility with any real firm, evaluation
or funded-account programme. A simulated "target reached" is not a pass, not a forecast and not a
pass-rate estimate. No strategy parameter was tuned against these rules, leverage was not raised to reach
targets, and the scenarios were written into `config/etf.yaml` before any replay ran.

## Configurable rules
| Key | Meaning |
|---|---|
| `starting_balance` | account size at the start of each replay |
| `profit_target_pct` | target on close equity (`target_basis: equity`) or balance (`balance`) |
| `max_daily_loss_pct` | limit = % of the starting balance (`daily_loss_limit_basis: starting`) or of the day's reference (`reference`) |
| `daily_loss_reference` | start-of-day **equity** (realised + unrealised) or start-of-day **balance** (realised only) |
| `daily_loss_check` | `intraday` (worst intraday equity) or `eod` (close equity) |
| `max_total_loss_pct` | amount = % of the starting balance |
| `drawdown_type` | `static` (floor = start − amount) or `trailing` (floor = peak − amount) |
| `trailing_basis` | peak of intraday best equity, of close equity, or of balance |
| `trailing_lock_at_start` | the trailing floor stops rising at the starting balance |
| `total_loss_check` | `intraday` or `eod` |
| `intrabar_order` | `conservative`: with daily data, today's high-water mark counts BEFORE today's low |
| `min_trading_days`, `consistency_max_day_share_pct` | target only counts with enough active days / no single day above x % of the profit |
Unknown keys or invalid values raise (`test_unknown_or_invalid_rule_keys_rejected`). Breach checks run
before the target check of the same session (`test_breach_checked_before_target_in_same_session`).

## Inputs and their limits
The replay path comes from the ETF reference engine: `equity` (close marks), `balance` (realised P&L
only), `equity_worst` / `equity_best` (adverse / favourable intraday extremes: bar lows/highs of open
positions; positions closed by a stop count at their fill, positions closed at a target or the close count
at the session extreme) and `active` (a trade opened or closed that day). With daily bars the order of the
intraday high and low is unknown, so intraday checks are conservative by construction. Rolling starts
rescale one strategy path (sizing is a fixed fraction of equity, so this is an approximation).

## Boundary tests (`tests/test_account_rules.py`, 10 tests, all passing)
* static total loss: 90,000.01 survives, exactly 90,000.00 breaches (10 % on 100,000);
* an intraday dip of 5.1 % breaches a 5 % daily limit with intraday checks but not with EOD checks;
* daily resets: −4 % then −4 % (7.8 % cumulative) never breaches a 5 % daily limit; minimum headroom 1,000;
* reference equity vs balance with an open unrealised loss: the same day breaches with a balance reference
  and survives with an equity reference;
* trailing intraday: a session high of 106,000 and low of 99,900 breaches a 6 % trailing floor (peak first),
  the EOD-trailing variant does not;
* trailing lock at the starting balance stops a floor that would otherwise breach on day 3;
* a gap through the floor breaches on the gap session; target needs minimum trading days and the
  consistency rule; breach beats target on the same session; invalid configuration raises.

## Replays of the frozen ETF book (SPY+QQQ, 1 % risk/trade, 4 % open-risk cap)
Rolling monthly starts, fixed horizon, `results/etf/study/study.json → account_rules`.
"open" = neither target nor breach within the horizon.

| Scenario (hypothetical) | Path | Starts | Target first | Breach first | Neither | Non-overlapping starts: target / breach / neither |
|---|---|---|---|---|---|---|
| H1: static 10 %, daily 5 %, target 8 %, 60 sessions | train 2008–2020 | 153 | 2 | 0 | 151 | 1 / 0 / 50 |
| H1 | 2021–2025 (viewed) | 53 | 5 | 0 | 48 | 2 / 0 / 16 |
| H2: trailing intraday 6 % (locks at start), daily 3 %, target 6 %, 60 sessions | train | 153 | 9 | 16 | 128 | 5 / 6 / 40 |
| H2 | 2021–2025 (viewed) | 53 | 7 | 5 | 41 | 3 / 1 / 14 |
| H3: trailing EOD balance 5 %, daily 4 % EOD, target 10 %, 50 % consistency, 120 sessions | train | 150 | 6 | 35 | 109 | 1 / 5 / 19 |
| H3 | 2021–2025 (viewed) | 50 | 10 | 9 | 31 | 2 / 1 / 6 |

Reading: at 1 % risk per trade this book makes ≈ 3–6 % a year, so a fixed 6–10 % target inside 3–6 months
is rarely reached; under tight trailing rules the book breaches more often than it reaches the target in
the training period. Overlapping starts are serially dependent (the non-overlapping columns are the
honest sample sizes: 9–51 independent windows). Nothing here estimates a real-world pass rate.

## Strategy-side protective controls (separate from the replay)
The portfolio gate (`swingtrader/etf/risk.py`) enforces, before every simulated order: per-trade risk,
open-risk cap, optional cluster cap, gross and net caps, one position per ETF (or controlled stacking),
a close-to-close daily-loss lockout (next session blocked), a sticky drawdown lockout (flatten at the next
open, halt until a new session), and a dated kill switch. `tests/test_etf_research_adapter.py` proves an
LLM "recommendation" (multiplier 10, "ignore limits") cannot bypass any of them.

## Commands
```bash
python -m swingtrader etf-study --skip-wf     # includes the account-rule replays
```
