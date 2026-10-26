#!/usr/bin/env bash
# Create the two environments this project needs (see docs/ARCHITECTURE.md).
#   .venv         core + LumiBot 4.6.30 (pandas 2.x)
#   .venv-agents  core + TradingAgents v0.7.0 @ e8f5503 (pandas 3.x)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3.13}
TA_COMMIT=e8f5503e9b86d5c2710b0c76b1f686703968c9df

if command -v uv >/dev/null 2>&1; then
  uv venv .venv --python "$PY"
  uv pip install --python .venv/bin/python -e ".[dev,lumibot]"
  uv venv .venv-agents --python "$PY"
  uv pip install --python .venv-agents/bin/python -e ".[dev]" \
    "tradingagents @ git+https://github.com/TauricResearch/TradingAgents@${TA_COMMIT}"
else
  "$PY" -m venv .venv
  .venv/bin/pip install -e ".[dev,lumibot]"
  "$PY" -m venv .venv-agents
  .venv-agents/bin/pip install -e ".[dev]" \
    "tradingagents @ git+https://github.com/TauricResearch/TradingAgents@${TA_COMMIT}"
fi
echo "done: .venv (LumiBot) and .venv-agents (TradingAgents)"
