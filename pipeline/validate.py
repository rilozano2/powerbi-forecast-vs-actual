"""Sanity checks on the processed data, plus reference answers for checking the Power BI measures.

Writes data/processed/check_values.csv: full-year forecast vs actual and the operating income bridge
for every company-year, computed here in pandas. When a DAX measure is built, its value for a
company-year should match the same column in this file.
"""

from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "data" / "processed"

# Reported full-year revenue ($B) from annual reports, used to check that quarters (and derived Q4s) add up.
REPORTED = {
    ("WMT", 2025): 680.985, ("COST", 2024): 254.453, ("TGT", 2025): 106.566, ("MSFT", 2024): 245.122,
    ("NVDA", 2025): 130.497, ("AMZN", 2024): 637.959, ("GOOGL", 2024): 350.018, ("META", 2024): 164.501,
    ("AMD", 2024): 25.785, ("SCHW", 2024): 19.606, ("HOOD", 2024): 2.951, ("SOFI", 2024): 2.675,
    ("NRG", 2024): 28.130, ("VST", 2024): 17.224, ("CEG", 2024): 23.568,
}


def main() -> None:
    a = pd.read_csv(OUT / "fact_actuals.csv")
    f = pd.read_csv(OUT / "fact_forecast.csv")
    d = pd.read_csv(OUT / "fact_drivers.csv")

    fy = a.groupby(["Ticker", "FiscalYear"])["Revenue"].sum() / 1e9
    for key, reported in REPORTED.items():
        assert abs(fy[key] / reported - 1) < 0.001, f"{key}: {fy[key]:.3f}B vs reported {reported}B"
    assert a["PeriodKey"].is_unique and f["PeriodKey"].is_unique, "duplicate period keys"
    assert (a["Revenue"] > 0).all(), "non-positive revenue"
    print(f"OK: {len(REPORTED)} annual revenue totals match annual reports; keys unique; revenue positive")

    # Full-year bridge. Operating income = revenue x operating margin, so the change from forecast
    # splits exactly into a revenue (volume) effect and a margin effect; with a gross margin, the margin
    # effect further splits into gross margin and opex.
    m = f.merge(a, on="PeriodKey", suffixes=("Fcst", "Act"))
    g = m.groupby(["TickerFcst", "Vintage"]).agg(
        Quarters=("RevenueAct", "count"),
        RevenueFcst=("RevenueFcst", "sum"), RevenueAct=("RevenueAct", "sum"),
        GrossProfitFcst=("GrossProfitFcst", "sum"), GrossProfitAct=("GrossProfitAct", "sum"),
        OpexFcst=("OperatingExpensesFcst", "sum"), OpexAct=("OperatingExpensesAct", "sum"),
        OperatingIncomeFcst=("OperatingIncomeFcst", "sum"), OperatingIncomeAct=("OperatingIncomeAct", "sum"),
    ).reset_index().rename(columns={"TickerFcst": "Ticker"})
    g = g[g["Quarters"] == 4].merge(d[["Ticker", "Vintage", "HasGrossMargin"]], on=["Ticker", "Vintage"])

    om_f = g["OperatingIncomeFcst"] / g["RevenueFcst"]
    om_a = g["OperatingIncomeAct"] / g["RevenueAct"]
    g["RevenueVariance"] = g["RevenueAct"] - g["RevenueFcst"]
    g["RevenueVariancePct"] = g["RevenueVariance"] / g["RevenueFcst"]
    g["OperatingIncomeVariance"] = g["OperatingIncomeAct"] - g["OperatingIncomeFcst"]
    g["BridgeRevenueEffect"] = g["RevenueVariance"] * om_f
    g["BridgeMarginEffect"] = g["RevenueAct"] * (om_a - om_f)
    gm = g["HasGrossMargin"]
    g.loc[gm, "BridgeGrossMarginEffect"] = g["RevenueAct"] * (g["GrossProfitAct"] / g["RevenueAct"] - g["GrossProfitFcst"] / g["RevenueFcst"])
    g.loc[gm, "BridgeOpexEffect"] = -g["RevenueAct"] * (g["OpexAct"] / g["RevenueAct"] - g["OpexFcst"] / g["RevenueFcst"])

    gap = (g["BridgeRevenueEffect"] + g["BridgeMarginEffect"] - g["OperatingIncomeVariance"]).abs().max()
    gap_gm = (g.loc[gm, "BridgeGrossMarginEffect"] + g.loc[gm, "BridgeOpexEffect"] - g.loc[gm, "BridgeMarginEffect"]).abs().max()
    assert gap < 100 and gap_gm < 100, f"bridge does not tie out (gap ${gap:,.0f}, ${gap_gm:,.0f})"
    print(f"OK: operating income bridge ties out for {len(g)} company-years (largest gap ${max(gap, gap_gm):,.0f}, from rounding)")

    g.round(4).to_csv(OUT / "check_values.csv", index=False)
    w = g[(g.Ticker == "WMT")].tail(1).iloc[0]
    print(
        f"\nExample, Walmart FY{w.Vintage}: revenue forecast ${w.RevenueFcst/1e9:.1f}B, actual ${w.RevenueAct/1e9:.1f}B "
        f"({w.RevenueVariancePct:+.1%}); operating income variance ${w.OperatingIncomeVariance/1e9:+.2f}B = "
        f"revenue ${w.BridgeRevenueEffect/1e9:+.2f}B + gross margin ${w.BridgeGrossMarginEffect/1e9:+.2f}B + opex ${w.BridgeOpexEffect/1e9:+.2f}B"
    )


if __name__ == "__main__":
    main()
