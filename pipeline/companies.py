"""Companies in scope, grouped into peer sets for benchmarking."""

# ticker: (SEC CIK, display name, peer group)
COMPANIES = {
    "WMT": (104169, "Walmart", "Retail"),
    "COST": (909832, "Costco", "Retail"),
    "TGT": (27419, "Target", "Retail"),
    "AMZN": (1018724, "Amazon", "Mega-cap tech"),
    "GOOGL": (1652044, "Alphabet", "Mega-cap tech"),
    "META": (1326801, "Meta Platforms", "Mega-cap tech"),
    "MSFT": (789019, "Microsoft", "Mega-cap tech"),
    "NVDA": (1045810, "NVIDIA", "AI semiconductors"),
    "AMD": (2488, "Advanced Micro Devices", "AI semiconductors"),
    "CEG": (1868275, "Constellation Energy", "Power & nuclear"),
    "VST": (1692819, "Vistra", "Power & nuclear"),
    "NRG": (1013871, "NRG Energy", "Power & nuclear"),
    "SCHW": (316709, "Charles Schwab", "Brokers & fintech"),
    "HOOD": (1783879, "Robinhood", "Brokers & fintech"),
    "SOFI": (1818874, "SoFi Technologies", "Brokers & fintech"),
}

# XBRL tags to try, in priority order. The first tag with a value for a period wins.
TAGS = {
    "Revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "RevenuesNetOfInterestExpense",
        "SalesRevenueNet",
    ],
    "CostOfRevenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "OperatingIncome": [
        "OperatingIncomeLoss",
        # Banks and brokers often report no operating income line; pre-tax income stands in.
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "NetIncome": ["NetIncomeLoss", "ProfitLoss"],
}

# Per-company overrides. revenue_tags are tried before the defaults
# (SoFi's "Revenues" tag is only part of its revenue).
OVERRIDES = {
    "SOFI": {"revenue_tags": ["RevenuesNetOfInterestExpense"]},
}
# Business models without a meaningful cost-of-revenue line: power generators report fuel and
# purchased power inconsistently, and banks and brokers have none. These use operating margin instead.
NO_GROSS_MARGIN_GROUPS = {"Power & nuclear", "Brokers & fintech"}

FIRST_YEAR = 2015  # earliest fiscal year of actuals to keep
FIRST_VINTAGE = 2019  # first year we "stand in the past" and forecast
