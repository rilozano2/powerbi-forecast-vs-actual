"""Build point-in-time, driver-based forecasts and write fact_forecast.csv, fact_drivers.csv and dim_period.csv.

For each company and each fiscal year V (the "vintage"), we stand at the start of V, right after Q4 of
V-1 is reported, and forecast Q1 to Q4 of V using only actuals through Q4 of V-1. No later data leaks in.

Drivers (all measured on the trailing four quarters at the forecast date):
  Revenue growth   blend of last year's growth and the 3-year growth rate, capped to a sane range.
                   Applied to the same quarter of the prior year, so seasonality is kept.
  Gross margin     trailing gross profit / revenue (companies with no cost-of-revenue line skip it).
  Opex % revenue   trailing operating expenses / revenue.
  Net margin       trailing net income / revenue.

Forecast operating income = revenue x (gross margin - opex %), or revenue x operating margin when
there is no gross margin. That identity is what lets Power BI split each variance into a revenue
effect, a margin effect and an opex effect that add up exactly.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from companies import FIRST_VINTAGE

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"

GROWTH_CAP = (-0.20, 0.60)
GROWTH_WEIGHT_RECENT = 0.5  # weight on last year's growth vs the 3-year rate


def ttm(df: pd.DataFrame, end_idx: int, col: str, offset: int = 0) -> float:
    """Sum of col over the 4 quarters ending at end_idx - offset (NaN if any quarter missing)."""
    lo, hi = end_idx - offset - 3, end_idx - offset
    if lo < 0:
        return np.nan
    window = df.iloc[lo : hi + 1][col]
    return window.sum() if window.notna().all() and len(window) == 4 else np.nan


def drivers_at(df: pd.DataFrame, origin: int) -> dict:
    """Drivers using quarters up to and including row `origin` (the last reported quarter)."""
    rev0 = ttm(df, origin, "Revenue")
    rev1 = ttm(df, origin, "Revenue", 4)
    rev3 = ttm(df, origin, "Revenue", 12)
    g1 = rev0 / rev1 - 1 if rev1 and rev1 > 0 else np.nan
    g3 = (rev0 / rev3) ** (1 / 3) - 1 if rev3 and rev3 > 0 and rev0 > 0 else np.nan
    if np.isnan(g1) and np.isnan(g3):
        growth = np.nan
    elif np.isnan(g1) or np.isnan(g3):
        growth = g3 if np.isnan(g1) else g1
    else:
        growth = GROWTH_WEIGHT_RECENT * g1 + (1 - GROWTH_WEIGHT_RECENT) * g3
    growth = float(np.clip(growth, *GROWTH_CAP)) if not np.isnan(growth) else np.nan

    gp = ttm(df, origin, "GrossProfit")
    opex = ttm(df, origin, "OperatingExpenses")
    oi = ttm(df, origin, "OperatingIncome")
    ni = ttm(df, origin, "NetIncome")
    has_gm = not np.isnan(gp)
    return {
        "RevenueGrowth": growth,
        "GrossMargin": gp / rev0 if has_gm else np.nan,
        "OpexPct": opex / rev0 if has_gm else np.nan,
        "OperatingMargin": oi / rev0,
        "NetMargin": ni / rev0,
        "HasGrossMargin": has_gm,
    }


def main() -> None:
    actuals = pd.read_csv(OUT / "fact_actuals.csv", parse_dates=["PeriodStart", "PeriodEnd"])
    forecasts, drivers = [], []

    for ticker, df in actuals.groupby("Ticker"):
        df = df.sort_values("PeriodEnd").reset_index(drop=True)
        pos = {(r.FiscalYear, r.FiscalQuarter): i for i, r in df.iterrows()}
        last_year = int(df["FiscalYear"].max())
        for vintage in range(FIRST_VINTAGE, last_year + 1):
            origin = pos.get((vintage - 1, 4))
            if origin is None:
                continue
            d = drivers_at(df, origin)
            if np.isnan(d["RevenueGrowth"]) or np.isnan(d["OperatingMargin"]):
                continue
            drivers.append({"Ticker": ticker, "Vintage": vintage, "OriginPeriodEnd": df.loc[origin, "PeriodEnd"].date(), **d})

            for q in (1, 2, 3, 4):
                base = pos.get((vintage - 1, q))
                if base is None:
                    continue
                base_rev = df.loc[base, "Revenue"]
                rev = base_rev * (1 + d["RevenueGrowth"])
                if d["HasGrossMargin"]:
                    gp = rev * d["GrossMargin"]
                    opex = rev * d["OpexPct"]
                    oi = gp - opex
                else:
                    gp = opex = np.nan
                    oi = rev * d["OperatingMargin"]
                forecasts.append(
                    {
                        "Ticker": ticker,
                        "Vintage": vintage,
                        "PeriodKey": f"{ticker}-FY{vintage}Q{q}",
                        "FiscalYear": vintage,
                        "FiscalQuarter": q,
                        "Revenue": rev,
                        "GrossProfit": gp,
                        "OperatingExpenses": opex,
                        "OperatingIncome": oi,
                        "NetIncome": rev * d["NetMargin"],
                        # Drivers on each row so scenario measures can flex them in Power BI.
                        "BaseRevenue": base_rev,
                        "RevenueGrowth": d["RevenueGrowth"],
                        "OperatingMargin": d["OperatingMargin"],
                    }
                )

    fc = pd.DataFrame(forecasts).round({"Revenue": 0, "GrossProfit": 0, "OperatingExpenses": 0, "OperatingIncome": 0, "NetIncome": 0, "RevenueGrowth": 6, "OperatingMargin": 6})
    fc.to_csv(OUT / "fact_forecast.csv", index=False)
    pd.DataFrame(drivers).round(6).to_csv(OUT / "fact_drivers.csv", index=False)

    # One row per company fiscal quarter, in actuals or forecasts. Quarters not reported yet get an
    # estimated end date one year after the same quarter last year.
    periods = actuals[["PeriodKey", "Ticker", "FiscalYear", "FiscalQuarter", "PeriodStart", "PeriodEnd"]].assign(IsReported=True)
    future = fc.loc[~fc["PeriodKey"].isin(periods["PeriodKey"]), ["PeriodKey", "Ticker", "FiscalYear", "FiscalQuarter"]].drop_duplicates()
    prior = periods.assign(FiscalYear=periods["FiscalYear"] + 1)[["Ticker", "FiscalYear", "FiscalQuarter", "PeriodStart", "PeriodEnd"]]
    future = future.merge(prior, on=["Ticker", "FiscalYear", "FiscalQuarter"], how="left")
    future["PeriodStart"] += pd.DateOffset(years=1)
    future["PeriodEnd"] += pd.DateOffset(years=1)
    dim = pd.concat([periods, future.assign(IsReported=False)], ignore_index=True)
    dim["FiscalLabel"] = "FY" + dim["FiscalYear"].astype(str) + " Q" + dim["FiscalQuarter"].astype(str)
    dim["PeriodStart"] = dim["PeriodStart"].dt.date
    dim["PeriodEnd"] = dim["PeriodEnd"].dt.date
    dim.sort_values(["Ticker", "PeriodEnd"]).to_csv(OUT / "dim_period.csv", index=False)
    print(f"{len(fc)} forecast rows across {len(drivers)} company-vintages; {len(dim)} company-quarters")


if __name__ == "__main__":
    main()
