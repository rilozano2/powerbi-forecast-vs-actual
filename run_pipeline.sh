#!/bin/sh
# Refresh everything: pull actuals from SEC, rebuild forecasts, run checks.
# Needs SEC_USER_AGENT, set in .env (see .env.example).
set -e
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
python3 pipeline/fetch_actuals.py
python3 pipeline/build_forecasts.py
python3 pipeline/validate.py
