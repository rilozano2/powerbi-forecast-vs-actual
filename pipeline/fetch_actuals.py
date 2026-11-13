"""Download quarterly actuals from SEC XBRL company facts and write data/processed/fact_actuals.csv.

Each company is kept on its own fiscal calendar, the way its FP&A team reports. Quarters are
built from the actual start and end dates in the filings, not SEC's calendar "frames", because
frames skip periods that don't line up with calendar quarters (Costco's 16-week fourth quarter,
Microsoft's June year end).

Fourth quarters are rarely tagged on their own, so Q4 = full fiscal year minus Q1 to Q3.
Fiscal years are named by the calendar year they end in (Walmart's year ending January 2026 is FY2026).

Usage: SEC_USER_AGENT="Your Name you@example.com" python3 pipeline/fetch_actuals.py
"""

import json
import math
import os
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from companies import COMPANIES, FIRST_YEAR, NO_GROSS_MARGIN_GROUPS, OVERRIDES, TAGS

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

UA = os.environ.get("SEC_USER_AGENT")
if not UA:
    sys.exit('Set SEC_USER_AGENT to "Your Name your@email.com" (SEC fair-access policy requires a real contact).')

Period = tuple[date, date]


def company_facts(cik: int) -> dict:
    """Fetch company facts, cached in data/raw for a day."""
    path = RAW / f"CIK{cik:010d}.json"
    if path.exists() and time.time() - path.stat().st_mtime < 86400:
        return json.loads(path.read_text())
    req = urllib.request.Request(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", headers={"User-Agent": UA}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    RAW.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    time.sleep(0.2)  # stay well under SEC's 10 requests/second
    return data


def periods(facts: dict, tag: str) -> tuple[dict[Period, float], dict[Period, float]]:
    """Quarterly and annual duration facts for one tag, latest filing winning on duplicates."""
    node = facts.get("facts", {}).get("us-gaap", {}).get(tag)
    if not node:
        return {}, {}
    latest: dict[Period, tuple[str, float]] = {}
    for x in node["units"].get("USD", []):
        if "start" not in x:
            continue
        p = (date.fromisoformat(x["start"]), date.fromisoformat(x["end"]))
        if p not in latest or x["filed"] > latest[p][0]:
            latest[p] = (x["filed"], float(x["val"]))
    quarters, annuals = {}, {}
    for p, (_, v) in latest.items():
        days = (p[1] - p[0]).days + 1
        if 80 <= days <= 120:
            quarters[p] = v
        elif 350 <= days <= 380:
            annuals[p] = v
    return quarters, annuals


def near(a: date, b: date, tol: int = 4) -> bool:
    return abs((a - b).days) <= tol


def with_q4(quarters: dict[Period, float], annuals: dict[Period, float]) -> dict[Period, float]:
    """Add each missing fourth quarter as the annual total minus the three reported quarters."""
    out = dict(quarters)
    for (s, e), total in annuals.items():
        chain, cursor = [], s
        for _ in range(3):
            nxt = next((p for p in quarters if near(p[0], cursor)), None)
            if not nxt:
                break
            chain.append(nxt)
            cursor = nxt[1] + timedelta(days=1)
        if len(chain) == 3 and not any(near(p[0], cursor) and near(p[1], e) for p in quarters):
            out[(cursor, e)] = total - sum(quarters[p] for p in chain)
    return out


def merged(facts: dict, tags: list[str]) -> tuple[dict[Period, float], dict[Period, str], list[date]]:
    """Quarterly values across tags (first tag with a value wins), plus fiscal year end dates."""
    values: dict[Period, float] = {}
    source: dict[Period, str] = {}
    year_ends: set[date] = set()
    for tag in tags:
        q, a = periods(facts, tag)
        year_ends |= {e for _, e in a}
        for p, v in with_q4(q, a).items():
            if not any(near(p[0], k[0]) and near(p[1], k[1]) for k in values):
                values[p] = v
                source[p] = tag
    return values, source, sorted(year_ends)


def lookup(values: dict[Period, float], p: Period):
    return next((v for k, v in values.items() if near(k[0], p[0]) and near(k[1], p[1])), None)


def fiscal_label(end: date, year_ends: list[date]) -> tuple[int, int]:
    """(fiscal year, fiscal quarter) for a quarter ending on `end`."""
    fye = next((y for y in year_ends if y >= end - timedelta(days=4)), None)
    if fye is None:  # current, not yet completed fiscal year
        last = year_ends[-1]
        fye = last.replace(year=last.year + 1) if not (last.month == 2 and last.day == 29) else date(last.year + 1, 2, 28)
    prev = max((y for y in year_ends if y < fye - timedelta(days=300)), default=fye - timedelta(days=364))
    months = (end - prev).days / 30.44
    quarter = min(4, max(1, math.ceil(months / 3 - 0.25)))
    return fye.year, quarter


def main() -> None:
    rows = []
    for ticker, (cik, name, group) in COMPANIES.items():
        facts = company_facts(cik)
        rev_tags = OVERRIDES.get(ticker, {}).get("revenue_tags", []) + TAGS["Revenue"]
        revenue, _, year_ends = merged(facts, rev_tags)
        cogs, _, _ = merged(facts, TAGS["CostOfRevenue"]) if group not in NO_GROSS_MARGIN_GROUPS else ({}, {}, [])
        oi, oi_src, _ = merged(facts, TAGS["OperatingIncome"])
        ni, _, _ = merged(facts, TAGS["NetIncome"])

        seen: dict[tuple[int, int], dict] = {}
        for p in sorted(revenue, key=lambda k: k[1]):
            fy, fq = fiscal_label(p[1], year_ends)
            if fy < FIRST_YEAR:
                continue
            c, o = lookup(cogs, p), lookup(oi, p)
            rev = revenue[p]
            gp = rev - c if c is not None else None
            seen[(fy, fq)] = {
                "Ticker": ticker,
                "PeriodKey": f"{ticker}-FY{fy}Q{fq}",
                "FiscalYear": fy,
                "FiscalQuarter": fq,
                "PeriodStart": p[0],
                "PeriodEnd": p[1],
                "Revenue": rev,
                "CostOfRevenue": c,
                "GrossProfit": gp,
                # Implied operating expenses: everything between gross profit (or revenue) and operating income.
                "OperatingExpenses": ((gp if gp is not None else rev) - o) if o is not None else None,
                "OperatingIncome": o,
                "NetIncome": lookup(ni, p),
                "OperatingIncomeIsPreTax": next(
                    (s.startswith("IncomeLoss") for k, s in oi_src.items() if near(k[0], p[0]) and near(k[1], p[1])), False
                ),
            }
        company_rows = [seen[k] for k in sorted(seen)]
        # A cost line that only exists for part of the history would make gross margin jump around.
        if company_rows and sum(r["CostOfRevenue"] is not None for r in company_rows) / len(company_rows) < 0.9:
            for r in company_rows:
                r["CostOfRevenue"] = r["GrossProfit"] = None
                r["OperatingExpenses"] = r["Revenue"] - r["OperatingIncome"] if r["OperatingIncome"] is not None else None
        rows += company_rows
        first, last = company_rows[0], company_rows[-1]
        print(f"{ticker:6} {facts.get('entityName', '?'):35} {len(company_rows):3} quarters  FY{first['FiscalYear']}Q{first['FiscalQuarter']} to FY{last['FiscalYear']}Q{last['FiscalQuarter']} (ends {last['PeriodEnd']})")

    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "fact_actuals.csv", index=False)
    has_gm = df.groupby("Ticker")["GrossProfit"].apply(lambda s: s.notna().any())
    pd.DataFrame(
        [
            {"Ticker": t, "CIK": c, "Company": n, "PeerGroup": g, "HasGrossMargin": bool(has_gm.get(t, False))}
            for t, (c, n, g) in COMPANIES.items()
        ]
    ).to_csv(OUT / "dim_company.csv", index=False)
    print(f"\nWrote {len(df)} rows to data/processed/fact_actuals.csv")


if __name__ == "__main__":
    main()
