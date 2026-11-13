"""Generate the Power BI project (PBIP: TMDL semantic model + PBIR report) from code.

    python3 powerbi/generate_pbip.py

Writes powerbi/ForecastVsActual.pbip plus the .SemanticModel and .Report folders. Open the .pbip in
Power BI Desktop, then Refresh to load the CSVs from data/processed. Regenerating overwrites both
folders, so make layout changes either here or in Desktop (not both).
"""

import json
import shutil
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "ForecastVsActual"
MODEL = HERE / f"{NAME}.SemanticModel"
REPORT = HERE / f"{NAME}.Report"
DEFAULT_FOLDER = "\\\\Mac\\Home\\forecast-vs-actual\\data\\processed\\"

T = "\t"


def tag(*parts: str) -> str:
    """Stable lineage tag so regenerating doesn't churn every object."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "forecast-vs-actual/" + "/".join(parts)))


def q(name: str) -> str:
    """Quote a TMDL object name when it isn't a plain identifier."""
    return name if name.replace("_", "").isalnum() and not name[0].isdigit() else "'" + name.replace("'", "''") + "'"


def block(text: str, level: int) -> str:
    return "\n".join((T * level + line) if line.strip() else "" for line in text.strip("\n").splitlines())


# ---------------------------------------------------------------- semantic model

CSV_TABLES = {
    # table: (file, [(column, dataType, formatString or None, summarizeBy, hidden)])
    "DimCompany": ("dim_company.csv", [
        ("Ticker", "string", None, "none", False),
        ("CIK", "int64", "0", "none", True),
        ("Company", "string", None, "none", False),
        ("PeerGroup", "string", None, "none", False),
        ("HasGrossMargin", "boolean", None, "none", False),
    ]),
    "DimPeriod": ("dim_period.csv", [
        ("PeriodKey", "string", None, "none", True),
        ("Ticker", "string", None, "none", True),
        ("FiscalYear", "int64", "0", "none", False),
        ("FiscalQuarter", "int64", "0", "none", False),
        ("PeriodStart", "dateTime", "yyyy-mm-dd", "none", False),
        ("PeriodEnd", "dateTime", "yyyy-mm-dd", "none", False),
        ("IsReported", "boolean", None, "none", False),
        ("FiscalLabel", "string", None, "none", False),
        ("PeriodSort", "int64", "0", "none", True),
    ]),
    "FactActuals": ("fact_actuals.csv", [
        ("Ticker", "string", None, "none", True),
        ("PeriodKey", "string", None, "none", True),
        ("FiscalYear", "int64", "0", "none", True),
        ("FiscalQuarter", "int64", "0", "none", True),
        ("PeriodStart", "dateTime", "yyyy-mm-dd", "none", True),
        ("PeriodEnd", "dateTime", "yyyy-mm-dd", "none", True),
        ("Revenue", "double", '$#,0,,,.00"B"', "sum", True),
        ("CostOfRevenue", "double", '$#,0,,,.00"B"', "sum", True),
        ("GrossProfit", "double", '$#,0,,,.00"B"', "sum", True),
        ("OperatingExpenses", "double", '$#,0,,,.00"B"', "sum", True),
        ("OperatingIncome", "double", '$#,0,,,.00"B"', "sum", True),
        ("NetIncome", "double", '$#,0,,,.00"B"', "sum", True),
        ("OperatingIncomeIsPreTax", "boolean", None, "none", False),
    ]),
    "FactForecast": ("fact_forecast.csv", [
        ("Ticker", "string", None, "none", True),
        ("Vintage", "int64", "0", "none", False),
        ("PeriodKey", "string", None, "none", True),
        ("FiscalYear", "int64", "0", "none", True),
        ("FiscalQuarter", "int64", "0", "none", True),
        ("Revenue", "double", '$#,0,,,.00"B"', "sum", True),
        ("GrossProfit", "double", '$#,0,,,.00"B"', "sum", True),
        ("OperatingExpenses", "double", '$#,0,,,.00"B"', "sum", True),
        ("OperatingIncome", "double", '$#,0,,,.00"B"', "sum", True),
        ("NetIncome", "double", '$#,0,,,.00"B"', "sum", True),
        ("BaseRevenue", "double", '$#,0,,,.00"B"', "sum", True),
        ("RevenueGrowth", "double", "0.0%", "none", True),
        ("OperatingMargin", "double", "0.0%", "none", True),
    ]),
    "FactDrivers": ("fact_drivers.csv", [
        ("Ticker", "string", None, "none", True),
        ("Vintage", "int64", "0", "none", False),
        ("OriginPeriodEnd", "dateTime", "yyyy-mm-dd", "none", False),
        ("RevenueGrowth", "double", "0.0%", "none", False),
        ("GrossMargin", "double", "0.0%", "none", False),
        ("OpexPct", "double", "0.0%", "none", False),
        ("OperatingMargin", "double", "0.0%", "none", False),
        ("NetMargin", "double", "0.0%", "none", False),
        ("HasGrossMargin", "boolean", None, "none", True),
    ]),
    "CheckValues": ("check_values.csv", [
        ("Ticker", "string", None, "none", False),
        ("Vintage", "int64", "0", "none", False),
        ("RevenueVariance", "double", '$#,0,,,.000"B"', "sum", False),
        ("RevenueVariancePct", "double", "0.00%", "none", False),
        ("OperatingIncomeVariance", "double", '$#,0,,,.000"B"', "sum", False),
        ("BridgeRevenueEffect", "double", '$#,0,,,.000"B"', "sum", False),
        ("BridgeMarginEffect", "double", '$#,0,,,.000"B"', "sum", False),
        ("BridgeGrossMarginEffect", "double", '$#,0,,,.000"B"', "sum", False),
        ("BridgeOpexEffect", "double", '$#,0,,,.000"B"', "sum", False),
    ]),
}
HIDDEN_TABLES = {"CheckValues"}
SORT_BY = {("DimPeriod", "FiscalLabel"): "PeriodSort"}

M_TYPES = {"string": "type text", "int64": "Int64.Type", "double": "type number", "dateTime": "type date", "boolean": "type logical"}

# Measures: (name, folder, format, expression, description)
MEASURES = [
    # Actuals
    ("Revenue Actual", "Actuals", "$B", "SUM ( FactActuals[Revenue] )", "Reported revenue."),
    ("Gross Profit Actual", "Actuals", "$B", "SUM ( FactActuals[GrossProfit] )", None),
    ("Opex Actual", "Actuals", "$B", "SUM ( FactActuals[OperatingExpenses] )", "Implied operating expenses: gross profit (or revenue) minus operating income."),
    ("Operating Income Actual", "Actuals", "$B", "SUM ( FactActuals[OperatingIncome] )", None),
    ("Net Income Actual", "Actuals", "$B", "SUM ( FactActuals[NetIncome] )", None),
    ("Operating Margin (reported)", "Actuals", "%", "DIVIDE ( [Operating Income Actual], [Revenue Actual] )", None),
    ("Revenue PY", "Actuals", "$B", """
VAR yrs = SELECTCOLUMNS ( VALUES ( DimPeriod[FiscalYear] ), "y", DimPeriod[FiscalYear] - 1 )
VAR qs = VALUES ( DimPeriod[FiscalQuarter] )
RETURN
    CALCULATE ( [Revenue Actual], REMOVEFILTERS ( DimPeriod ), TREATAS ( yrs, DimPeriod[FiscalYear] ), qs )
""", "Same fiscal quarters one fiscal year earlier. Shifts by fiscal year instead of SAMEPERIODLASTYEAR because every company's quarters end on different dates."),
    ("Revenue YoY %", "Actuals", "%", "DIVIDE ( [Revenue Actual] - [Revenue PY], [Revenue PY] )", None),
    ("Revenue TTM", "Actuals", "$B", """
VAR e = MAX ( DimPeriod[PeriodEnd] )
RETURN
    CALCULATE ( [Revenue Actual], REMOVEFILTERS ( DimPeriod ), DATESINPERIOD ( 'Calendar'[Date], e, -12, MONTH ) )
""", "Trailing twelve months of revenue ending at the latest quarter in context."),
    # Forecast
    ("Revenue Forecast", "Forecast", "$B", "SUM ( FactForecast[Revenue] )", "Forecast made at the start of each fiscal year using only data available then."),
    ("Gross Profit Forecast", "Forecast", "$B", "SUM ( FactForecast[GrossProfit] )", None),
    ("Opex Forecast", "Forecast", "$B", "SUM ( FactForecast[OperatingExpenses] )", None),
    ("Operating Income Forecast", "Forecast", "$B", "SUM ( FactForecast[OperatingIncome] )", None),
    ("Net Income Forecast", "Forecast", "$B", "SUM ( FactForecast[NetIncome] )", None),
    # Comparable: only quarters that have both a forecast and an actual
    ("Comparable Quarters", "Comparable", "0", """
COUNTROWS (
    FILTER ( DimPeriod, NOT ISBLANK ( [Revenue Forecast] ) && NOT ISBLANK ( [Revenue Actual] ) )
)
""", "Quarters with both a forecast and an actual. Variances only count these, so unreported quarters don't show up as misses."),
]
for metric, base in [("Revenue", "Revenue"), ("Gross Profit", "Gross Profit"), ("Opex", "Opex"), ("Operating Income", "Operating Income")]:
    MEASURES.append((f"{metric} Act (c)", "Comparable", "$B",
                     f"SUMX ( FILTER ( DimPeriod, NOT ISBLANK ( [{base} Forecast] ) ), [{base} Actual] )", None))
    MEASURES.append((f"{metric} Fcst (c)", "Comparable", "$B",
                     f"SUMX ( FILTER ( DimPeriod, NOT ISBLANK ( [{base} Actual] ) ), [{base} Forecast] )", None))
MEASURES += [
    # Variance
    ("Revenue Variance", "Variance", "$B", "[Revenue Act (c)] - [Revenue Fcst (c)]", "Actual minus forecast. Positive is favorable for revenue."),
    ("Revenue Variance %", "Variance", "%", "DIVIDE ( [Revenue Variance], [Revenue Fcst (c)] )", None),
    ("Revenue Variance % (full years)", "Variance", "%", "IF ( [Comparable Quarters] = 4, [Revenue Variance %] )", "Only for a single company-year with all four quarters reported."),
    ("Operating Income Variance", "Variance", "$B", "[Operating Income Act (c)] - [Operating Income Fcst (c)]", None),
    ("Operating Income Variance %", "Variance", "%", "DIVIDE ( [Operating Income Variance], ABS ( [Operating Income Fcst (c)] ) )", None),
    ("Revenue Variance Flag", "Variance", None, 'IF ( NOT ISBLANK ( [Revenue Variance] ), IF ( [Revenue Variance] >= 0, "Favorable", "Unfavorable" ) )', None),
    ("Opex Variance Flag", "Variance", None, 'IF ( NOT ISBLANK ( [Opex Act (c)] ), IF ( [Opex Act (c)] <= [Opex Fcst (c)], "Favorable", "Unfavorable" ) )', "Spending less than forecast is favorable."),
    # Margins
    ("Operating Margin Actual", "Margins", "%", "DIVIDE ( [Operating Income Act (c)], [Revenue Act (c)] )", None),
    ("Operating Margin Forecast", "Margins", "%", "DIVIDE ( [Operating Income Fcst (c)], [Revenue Fcst (c)] )", None),
    ("Gross Margin Actual", "Margins", "%", "DIVIDE ( [Gross Profit Act (c)], [Revenue Act (c)] )", None),
    ("Gross Margin Forecast", "Margins", "%", "DIVIDE ( [Gross Profit Fcst (c)], [Revenue Fcst (c)] )", None),
    # Bridge
    ("Bridge Revenue Effect", "Bridge", "$B", "[Revenue Variance] * [Operating Margin Forecast]", "Operating income gained or lost from selling more or less than forecast, at the forecast margin."),
    ("Bridge Margin Effect", "Bridge", "$B", "[Revenue Act (c)] * ( [Operating Margin Actual] - [Operating Margin Forecast] )", "Operating income gained or lost from a different operating margin, on actual revenue."),
    ("Bridge Gross Margin Effect", "Bridge", "$B", "[Revenue Act (c)] * ( [Gross Margin Actual] - [Gross Margin Forecast] )", None),
    ("Bridge Opex Effect", "Bridge", "$B", """
-1 * [Revenue Act (c)]
    * ( DIVIDE ( [Opex Act (c)], [Revenue Act (c)] ) - DIVIDE ( [Opex Fcst (c)], [Revenue Fcst (c)] ) )
""", "Negative when opex ran higher than forecast as a share of revenue."),
    ("Has Gross Margin (all selected)", "Bridge", None, "ISEMPTY ( FILTER ( DimCompany, NOT DimCompany[HasGrossMargin] ) )", None),
    ("Bridge Value", "Bridge", "$B", """
VAR gm = [Has Gross Margin (all selected)]
RETURN
    SWITCH (
        SELECTEDVALUE ( BridgeSteps[Step] ),
        "Forecast operating income", [Operating Income Fcst (c)],
        "Revenue effect", [Bridge Revenue Effect],
        "Gross margin effect", IF ( gm, [Bridge Gross Margin Effect] ),
        "Opex effect", IF ( gm, [Bridge Opex Effect] ),
        "Operating margin effect", IF ( NOT gm, [Bridge Margin Effect] )
    )
""", "Feeds the waterfall. The steps add up exactly to actual operating income."),
    # Accuracy
    ("Revenue Abs % Error", "Accuracy", "%", "ABS ( [Revenue Variance %] )", None),
    ("Revenue MAPE (company-years)", "Accuracy", "%", """
AVERAGEX (
    FILTER (
        CROSSJOIN ( VALUES ( DimCompany[Ticker] ), VALUES ( DimPeriod[FiscalYear] ) ),
        [Comparable Quarters] = 4
    ),
    [Revenue Abs % Error]
)
""", "Average absolute full-year revenue miss, each company-year counted once."),
    ("Share Within 5%", "Accuracy", "%", """
VAR years =
    FILTER (
        CROSSJOIN ( VALUES ( DimCompany[Ticker] ), VALUES ( DimPeriod[FiscalYear] ) ),
        [Comparable Quarters] = 4
    )
RETURN
    DIVIDE ( COUNTROWS ( FILTER ( years, [Revenue Abs % Error] <= 0.05 ) ), COUNTROWS ( years ) )
""", None),
    ("Company-Years Scored", "Accuracy", "0", """
COUNTROWS (
    FILTER (
        CROSSJOIN ( VALUES ( DimCompany[Ticker] ), VALUES ( DimPeriod[FiscalYear] ) ),
        [Comparable Quarters] = 4
    )
)
""", None),
    ("Revenue Bias (company-years)", "Accuracy", "%", """
AVERAGEX (
    FILTER (
        CROSSJOIN ( VALUES ( DimCompany[Ticker] ), VALUES ( DimPeriod[FiscalYear] ) ),
        [Comparable Quarters] = 4
    ),
    [Revenue Variance %]
)
""", "Average signed miss. Positive means actual revenue tended to beat the forecast (the forecast was conservative)."),
    ("Naive Fcst (c)", "Accuracy", "$B", """
SUMX (
    FILTER ( DimPeriod, NOT ISBLANK ( [Revenue Forecast] ) && NOT ISBLANK ( [Revenue Actual] ) ),
    VAR t = DimPeriod[Ticker]
    RETURN CALCULATE ( [Revenue PY], DimCompany[Ticker] = t )
)
""", "Benchmark forecast: the same quarters' revenue one year earlier (no growth)."),
    ("Naive Abs % Error", "Accuracy", "%", "ABS ( DIVIDE ( [Revenue Act (c)] - [Naive Fcst (c)], [Naive Fcst (c)] ) )", None),
    ("Revenue MAPE (naive)", "Accuracy", "%", """
AVERAGEX (
    FILTER (
        CROSSJOIN ( VALUES ( DimCompany[Ticker] ), VALUES ( DimPeriod[FiscalYear] ) ),
        [Comparable Quarters] = 4 && NOT ISBLANK ( [Naive Fcst (c)] )
    ),
    [Naive Abs % Error]
)
""", "Average miss of the same-as-last-year benchmark, on the same company-years as the model."),
    ("Beats Naive Share", "Accuracy", "%", """
VAR years =
    FILTER (
        CROSSJOIN ( VALUES ( DimCompany[Ticker] ), VALUES ( DimPeriod[FiscalYear] ) ),
        [Comparable Quarters] = 4 && NOT ISBLANK ( [Naive Fcst (c)] )
    )
RETURN
    DIVIDE ( COUNTROWS ( FILTER ( years, [Revenue Abs % Error] < [Naive Abs % Error] ) ), COUNTROWS ( years ) )
""", "Share of company-years where the driver model was closer than the naive benchmark."),
    # Drivers
    ("Assumed Revenue Growth", "Drivers", "%", "CALCULATE ( AVERAGE ( FactDrivers[RevenueGrowth] ), TREATAS ( VALUES ( DimPeriod[FiscalYear] ), FactDrivers[Vintage] ) )", "Growth rate the forecast assumed for the fiscal year in context."),
    ("Assumed Operating Margin", "Drivers", "%", "CALCULATE ( AVERAGE ( FactDrivers[OperatingMargin] ), TREATAS ( VALUES ( DimPeriod[FiscalYear] ), FactDrivers[Vintage] ) )", None),
    # Scenario
    ("Revenue Base (latest)", "Scenario", "$B", "SUMX ( FILTER ( FactForecast, FactForecast[Is Latest Vintage Row] ), FactForecast[Revenue] )", "The current fiscal year's forecast before any slider adjustments."),
    ("Revenue Scenario", "Scenario", "$B", """
SUMX (
    FILTER ( FactForecast, FactForecast[Is Latest Vintage Row] ),
    FactForecast[BaseRevenue] * ( 1 + FactForecast[RevenueGrowth] + [Growth Adjustment Value] )
)
""", "Current-year forecast with the growth slider applied."),
    ("Operating Income Scenario", "Scenario", "$B", """
SUMX (
    FILTER ( FactForecast, FactForecast[Is Latest Vintage Row] ),
    FactForecast[BaseRevenue] * ( 1 + FactForecast[RevenueGrowth] + [Growth Adjustment Value] )
        * ( FactForecast[OperatingMargin] + [Margin Adjustment Value] )
)
""", None),
    ("Revenue Actual (current year)", "Scenario", "$B", """
VAR keys =
    SELECTCOLUMNS ( FILTER ( FactForecast, FactForecast[Is Latest Vintage Row] ), "k", FactForecast[PeriodKey] )
RETURN
    CALCULATE ( [Revenue Actual], TREATAS ( keys, FactActuals[PeriodKey] ) )
""", "Reported revenue, limited to the quarters of the current forecast year."),
    ("Revenue Outlook", "Scenario", "$B", """
SUMX (
    FILTER ( FactForecast, FactForecast[Is Latest Vintage Row] ),
    VAR k = FactForecast[PeriodKey]
    VAR scenario = FactForecast[BaseRevenue] * ( 1 + FactForecast[RevenueGrowth] + [Growth Adjustment Value] )
    RETURN
        IF ( RELATED ( DimPeriod[IsReported] ), CALCULATE ( SUM ( FactActuals[Revenue] ), FactActuals[PeriodKey] = k ), scenario )
)
""", "Reported quarters at actual, the rest of the year at the scenario."),
]
FORMATS = {"$B": '$#,0,,,.00"B"', "%": "0.0%", "0": "#,0"}

RELATIONSHIPS = [
    ("FactActuals", "Ticker", "DimCompany", "Ticker"),
    ("FactForecast", "Ticker", "DimCompany", "Ticker"),
    ("FactDrivers", "Ticker", "DimCompany", "Ticker"),
    ("FactActuals", "PeriodKey", "DimPeriod", "PeriodKey"),
    ("FactForecast", "PeriodKey", "DimPeriod", "PeriodKey"),
    ("DimPeriod", "PeriodEnd", "Calendar", "Date"),
]


def csv_table(name: str) -> str:
    file, cols = CSV_TABLES[name]
    out = [f"table {q(name)}", f"{T}lineageTag: {tag('table', name)}"]
    if name in HIDDEN_TABLES:
        out.insert(1, f"{T}isHidden")
    out.append("")
    for col, dtype, fmt, summ, hidden in cols:
        lines = [f"{T}column {q(col)}", f"{T*2}dataType: {dtype}"]
        if hidden:
            lines.append(f"{T*2}isHidden")
        if fmt:
            lines.append(f"{T*2}formatString: {fmt}")
        lines += [f"{T*2}lineageTag: {tag('col', name, col)}", f"{T*2}summarizeBy: {summ}", f"{T*2}sourceColumn: {col}"]
        if (name, col) in SORT_BY:
            lines.append(f"{T*2}sortByColumn: {SORT_BY[(name, col)]}")
        lines += ["", f"{T*2}annotation SummarizationSetBy = Automatic", ""]
        out += lines
    if name == "FactForecast":
        out += [
            f"{T}/// TRUE on rows from each company's most recent forecast vintage (the current fiscal year).",
            f"{T}column 'Is Latest Vintage Row' =",
            block("FactForecast[Vintage] = CALCULATE ( MAX ( FactForecast[Vintage] ), ALLEXCEPT ( FactForecast, FactForecast[Ticker] ) )", 3),
            f"{T*2}dataType: boolean",
            f"{T*2}isHidden",
            f"{T*2}lineageTag: {tag('col', name, 'IsLatestVintageRow')}",
            f"{T*2}summarizeBy: none",
            "",
            f"{T*2}annotation SummarizationSetBy = Automatic",
            "",
        ]
    types = ", ".join(f'{{"{c}", {M_TYPES[d]}}}' for c, d, *_ in cols if not (name == "DimPeriod" and c == "PeriodSort"))
    extra = ""
    if name == "DimPeriod":
        extra = ',\n    #"Added PeriodSort" = Table.AddColumn(Typed, "PeriodSort", each [FiscalYear] * 10 + [FiscalQuarter], Int64.Type)'
    last = '#"Added PeriodSort"' if extra else "Typed"
    m = f"""let
    Source = Csv.Document(File.Contents(DataFolder & "{file}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    // Empty CSV cells (no gross margin, unreported quarters) become nulls before typing.
    Blanks = Table.TransformColumns(#"Promoted Headers", {{}}, each if _ = "" then null else _),
    Typed = Table.TransformColumnTypes(Blanks, {{{types}}}, "en-US"){extra}
in
    {last}"""
    out += [f"{T}partition {q(name)} = m", f"{T*2}mode: import", f"{T*2}source =", block(m, 4), "",
            f"{T}annotation PBI_ResultType = Table", ""]
    return "\n".join(out)


def measures_table() -> str:
    out = ["table _Measures", f"{T}lineageTag: {tag('table', '_Measures')}", ""]
    for name, folder, fmt, expr, desc in MEASURES:
        expr = expr.strip("\n")
        if desc:
            out.append(f"{T}/// {desc}")
        if "\n" in expr:
            out += [f"{T}measure {q(name)} =", block(expr, 3)]
        else:
            out.append(f"{T}measure {q(name)} = {expr}")
        if fmt:
            out.append(f"{T*2}formatString: {FORMATS[fmt]}")
        out += [f"{T*2}displayFolder: {folder}", f"{T*2}lineageTag: {tag('measure', name)}", ""]
    out += [
        f"{T}column Placeholder",
        f"{T*2}dataType: int64",
        f"{T*2}isHidden",
        f"{T*2}formatString: 0",
        f"{T*2}lineageTag: {tag('col', '_Measures', 'Placeholder')}",
        f"{T*2}summarizeBy: none",
        f"{T*2}isNameInferred",
        f"{T*2}sourceColumn: [Placeholder]",
        "",
        f"{T}partition _Measures = calculated",
        f"{T*2}mode: import",
        f'{T*2}source = ROW ( "Placeholder", 0 )',
        "",
    ]
    return "\n".join(out)


def calc_column(table: str, name: str, dtype: str, fmt, hidden=False, key=False, sort_by=None) -> list[str]:
    lines = [f"{T}column {q(name)}", f"{T*2}dataType: {dtype}"]
    if key:
        lines.append(f"{T*2}isKey")
    if hidden:
        lines.append(f"{T*2}isHidden")
    if fmt:
        lines.append(f"{T*2}formatString: {fmt}")
    lines += [f"{T*2}lineageTag: {tag('col', table, name)}", f"{T*2}summarizeBy: none", f"{T*2}isNameInferred", f"{T*2}sourceColumn: [{name}]"]
    if sort_by:
        lines.append(f"{T*2}sortByColumn: {q(sort_by)}")
    return lines + ["", f"{T*2}annotation SummarizationSetBy = Automatic", ""]


def calendar_table() -> str:
    out = ["table Calendar", f"{T}dataCategory: Time", f"{T}lineageTag: {tag('table', 'Calendar')}", ""]
    out += calc_column("Calendar", "Date", "dateTime", "yyyy-mm-dd", key=True)
    out += calc_column("Calendar", "Year", "int64", "0")
    out += calc_column("Calendar", "MonthNumber", "int64", "0", hidden=True)
    out += calc_column("Calendar", "Month", "string", None, sort_by="MonthNumber")
    out += calc_column("Calendar", "CalendarQuarter", "string", None)
    src = """
ADDCOLUMNS (
    CALENDAR ( DATE ( 2014, 1, 1 ), DATE ( 2028, 12, 31 ) ),
    "Year", YEAR ( [Date] ),
    "MonthNumber", MONTH ( [Date] ),
    "Month", FORMAT ( [Date], "MMM" ),
    "CalendarQuarter", "Q" & QUARTER ( [Date] )
)
"""
    out += [f"{T}partition Calendar = calculated", f"{T*2}mode: import", f"{T*2}source =", block(src, 4), ""]
    return "\n".join(out)


def bridge_steps_table() -> str:
    out = ["/// Categories for the variance waterfall.", "table BridgeSteps", f"{T}lineageTag: {tag('table', 'BridgeSteps')}", ""]
    out += calc_column("BridgeSteps", "Step", "string", None, sort_by="Order")
    out += calc_column("BridgeSteps", "Order", "int64", "0", hidden=True)
    src = """
DATATABLE (
    "Step", STRING,
    "Order", INTEGER,
    {
        { "Forecast operating income", 1 },
        { "Revenue effect", 2 },
        { "Gross margin effect", 3 },
        { "Opex effect", 4 },
        { "Operating margin effect", 5 }
    }
)
"""
    out += [f"{T}partition BridgeSteps = calculated", f"{T*2}mode: import", f"{T*2}source =", block(src, 4), ""]
    return "\n".join(out)


def what_if_table(name: str, lo: str, hi: str, step: str, measure: str, desc: str) -> str:
    # Decimal literals so GENERATESERIES returns a decimal column, matching the declared dataType.
    col = f"{name} (pts)"
    out = [f"/// {desc}", f"table {q(name)}", f"{T}lineageTag: {tag('table', name)}", "",
           f"{T}measure {q(measure)} = DIVIDE ( SELECTEDVALUE ( {q(name)}[{col}], 0 ), 100 )",
           f"{T*2}formatString: 0.0%", f"{T*2}lineageTag: {tag('measure', measure)}", "",
           f"{T}column {q(col)}", f"{T*2}dataType: double", f"{T*2}formatString: 0.0",
           f"{T*2}lineageTag: {tag('col', name, col)}", f"{T*2}summarizeBy: none", f"{T*2}sourceColumn: [Value]", "",
           f"{T*2}extendedProperty ParameterMetadata =", f"{T*4}{{", f'{T*4}  "version": 0', f"{T*4}}}", "",
           f"{T*2}annotation SummarizationSetBy = User", "",
           f"{T}partition {q(name)} = calculated", f"{T*2}mode: import",
           f"{T*2}source = GENERATESERIES ( {lo}, {hi}, {step} )", "",
           f"{T}annotation PBI_Id = {tag('whatif', name).replace('-', '')}", ""]
    return "\n".join(out)


METRIC_ITEMS = [("Revenue", "Revenue Actual"), ("Gross profit", "Gross Profit Actual"), ("Operating income", "Operating Income Actual"),
                ("Net income", "Net Income Actual"), ("Operating margin", "Operating Margin (reported)"), ("Revenue TTM", "Revenue TTM")]
METRIC_MEASURES = [m for _, m in METRIC_ITEMS]


def field_parameter_table() -> str:
    items = METRIC_ITEMS
    rows = ",\n".join(f'    ("{label}", NAMEOF ( \'_Measures\'[{m}] ), {i})' for i, (label, m) in enumerate(items))
    out = ["/// Field parameter: pick which metric the trend chart shows.", "table Metric", f"{T}lineageTag: {tag('table', 'Metric')}", "",
           f"{T}column Metric", f"{T*2}lineageTag: {tag('col', 'Metric', 'Metric')}", f"{T*2}summarizeBy: none",
           f"{T*2}sourceColumn: [Value1]", f"{T*2}sortByColumn: 'Metric Order'", "",
           f"{T*2}relatedColumnDetails", f"{T*3}groupByColumn: 'Metric Fields'", "",
           f"{T*2}annotation SummarizationSetBy = Automatic", "",
           f"{T}column 'Metric Fields'", f"{T*2}isHidden", f"{T*2}lineageTag: {tag('col', 'Metric', 'Fields')}",
           f"{T*2}summarizeBy: none", f"{T*2}sourceColumn: [Value2]", f"{T*2}sortByColumn: 'Metric Order'", "",
           f"{T*2}extendedProperty ParameterMetadata =", f"{T*4}{{", f'{T*4}  "version": 3,', f'{T*4}  "kind": 2', f"{T*4}}}", "",
           f"{T*2}annotation SummarizationSetBy = Automatic", "",
           f"{T}column 'Metric Order'", f"{T*2}isHidden", f"{T*2}formatString: 0", f"{T*2}lineageTag: {tag('col', 'Metric', 'Order')}",
           f"{T*2}summarizeBy: sum", f"{T*2}sourceColumn: [Value3]", "", f"{T*2}annotation SummarizationSetBy = Automatic", "",
           f"{T}partition Metric = calculated", f"{T*2}mode: import", f"{T*2}source =", block("{\n" + rows + "\n}", 4), "",
           f"{T}annotation PBI_Id = {tag('fieldparam', 'Metric').replace('-', '')}", ""]
    return "\n".join(out)


def calc_group_table() -> str:
    py = """
VAR yrs = SELECTCOLUMNS ( VALUES ( DimPeriod[FiscalYear] ), "y", DimPeriod[FiscalYear] - 1 )
VAR qs = VALUES ( DimPeriod[FiscalQuarter] )
RETURN
    CALCULATE ( SELECTEDMEASURE (), REMOVEFILTERS ( DimPeriod ), TREATAS ( yrs, DimPeriod[FiscalYear] ), qs )
"""
    yoy = """
VAR yrs = SELECTCOLUMNS ( VALUES ( DimPeriod[FiscalYear] ), "y", DimPeriod[FiscalYear] - 1 )
VAR qs = VALUES ( DimPeriod[FiscalQuarter] )
VAR prior =
    CALCULATE ( SELECTEDMEASURE (), REMOVEFILTERS ( DimPeriod ), TREATAS ( yrs, DimPeriod[FiscalYear] ), qs )
RETURN
    DIVIDE ( SELECTEDMEASURE () - prior, prior )
"""
    out = ["/// Calculation group: show any actual measure as current, prior fiscal year, or year-over-year change.",
           "table 'Time View'", f"{T}lineageTag: {tag('table', 'Time View')}", "",
           f"{T}calculationGroup", f"{T*2}precedence: 1", "",
           f"{T*2}calculationItem Current = SELECTEDMEASURE ()", "",
           f"{T*2}calculationItem 'Prior year' =", block(py, 4), "",
           f"{T*2}calculationItem 'YoY %' =", block(yoy, 4), "",
           f'{T*3}formatStringDefinition = "0.0%"', "",
           f"{T}column 'Show as'", f"{T*2}dataType: string", f"{T*2}lineageTag: {tag('col', 'Time View', 'Show as')}",
           f"{T*2}summarizeBy: none", f"{T*2}sourceColumn: Name", f"{T*2}sortByColumn: Ordinal", "",
           f"{T*2}annotation SummarizationSetBy = Automatic", "",
           f"{T}column Ordinal", f"{T*2}dataType: int64", f"{T*2}isHidden", f"{T*2}formatString: 0",
           f"{T*2}lineageTag: {tag('col', 'Time View', 'Ordinal')}", f"{T*2}summarizeBy: sum", f"{T*2}sourceColumn: Ordinal", "",
           f"{T*2}annotation SummarizationSetBy = Automatic", ""]
    return "\n".join(out)


def write_model() -> list[str]:
    if MODEL.exists():
        shutil.rmtree(MODEL)
    d = MODEL / "definition"
    (d / "tables").mkdir(parents=True)
    (d / "roles").mkdir()
    (MODEL / "definition.pbism").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.1", "settings": {}}, indent=2) + "\n")
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1601\n")

    tables = {name: csv_table(name) for name in CSV_TABLES}
    tables["_Measures"] = measures_table()
    tables["Calendar"] = calendar_table()
    tables["BridgeSteps"] = bridge_steps_table()
    tables["Growth Adjustment"] = what_if_table("Growth Adjustment", "-20.0", "20.0", "1.0", "Growth Adjustment Value",
                                                "What-if parameter: percentage points added to the forecast revenue growth rate.")
    tables["Margin Adjustment"] = what_if_table("Margin Adjustment", "-10.0", "10.0", "0.5", "Margin Adjustment Value",
                                                "What-if parameter: percentage points added to the forecast operating margin.")
    tables["Metric"] = field_parameter_table()
    tables["Time View"] = calc_group_table()
    for name, text in tables.items():
        (d / "tables" / f"{name}.tmdl").write_text(text)

    order = ["DimCompany", "DimPeriod", "FactActuals", "FactForecast", "FactDrivers", "CheckValues"]
    (d / "model.tmdl").write_text("\n".join([
        "model Model",
        f"{T}culture: en-US",
        f"{T}defaultPowerBIDataSourceVersion: powerBI_V3",
        f"{T}discourageImplicitMeasures",
        f"{T}sourceQueryCulture: en-US",
        f"{T}dataAccessOptions",
        f"{T*2}legacyRedirects",
        f"{T*2}returnErrorValuesAsNull",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        f"annotation PBI_QueryOrder = {json.dumps(['DataFolder'] + order)}",
        "",
        *[f"ref table {q(n)}" for n in tables],
        "",
        "ref role 'Retail coverage'",
        "",
    ]))
    (d / "expressions.tmdl").write_text("\n".join([
        "/// Folder holding the pipeline CSVs. Change it under Transform data > Manage parameters.",
        "expression DataFolder =",
        f'{T*2}"{DEFAULT_FOLDER}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]',
        f"{T}lineageTag: {tag('expr', 'DataFolder')}",
        "",
        f"{T}annotation PBI_ResultType = Text",
        "",
    ]))
    rel = []
    for ft, fc, tt, tc in RELATIONSHIPS:
        rel += [f"relationship {tag('rel', ft, fc, tt)}", f"{T}fromColumn: {q(ft)}.{q(fc)}", f"{T}toColumn: {q(tt)}.{q(tc)}", ""]
    (d / "relationships.tmdl").write_text("\n".join(rel))
    (d / "roles" / "Retail coverage.tmdl").write_text("\n".join([
        "/// Static row-level security demo: members only see the Retail peer group.",
        "role 'Retail coverage'",
        f"{T}modelPermission: read",
        "",
        f"{T}tablePermission DimCompany = 'DimCompany'[PeerGroup] == \"Retail\"",
        "",
    ]))
    return list(tables)


# ---------------------------------------------------------------- report

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def col(entity, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def meas(prop, entity="_Measures"):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def proj(field, display=None):
    kind = "Measure" if "Measure" in field else "Column"
    f = field[kind]
    p = {"field": field, "queryRef": f"{f['Expression']['SourceRef']['Entity']}.{f['Property']}"}
    if kind == "Column":
        p["active"] = True
    if display:
        p["displayName"] = display
    return p


# Money measures are already formatted in billions ("$1,432.18B"). Power BI's automatic display units would
# divide by a billion again and show "$0bnB", so axes, data labels and cards use display units = None (1).
UNITS_OFF = {"labelDisplayUnits": {"expr": {"Literal": {"Value": "1D"}}}}
CHART_TYPES = {"lineChart", "clusteredColumnChart", "clusteredBarChart", "waterfallChart"}


def with_display_units_off(vtype: str, objects: dict) -> dict:
    names = ["valueAxis", "labels"] if vtype in CHART_TYPES else ["labels"] if vtype == "card" else []
    out = dict(objects)
    for name in names:
        existing = out.get(name, [{"properties": {}}])
        out[name] = [{**e, "properties": {**e.get("properties", {}), **UNITS_OFF}} for e in existing]
    return out


class Page:
    def __init__(self, name: str, display: str):
        self.name, self.display, self.visuals, self.z = name, display, [], 0
        self.no_filter: list[tuple[str, str]] = []  # (source visual, target visual) pairs that shouldn't filter

    def add(self, vid, vtype, x, y, w, h, roles=None, sort=None, objects=None, title=None, container=None, field_params=None):
        """field_params: {role: parameter column}. The role's projections are the parameter's measures."""
        self.z += 1000
        visual = {"visualType": vtype}
        if roles:
            visual["query"] = {"queryState": {r: {"projections": [proj(*f) if isinstance(f, tuple) else proj(f) for f in fs]} for r, fs in roles.items()}}
            for r, param in (field_params or {}).items():
                visual["query"]["queryState"][r]["fieldParameters"] = [{"parameterExpr": param, "index": 0, "length": len(roles[r])}]
            if sort:
                field, direction = sort
                visual["query"]["sortDefinition"] = {"sort": [{"field": field, "direction": direction}], "isDefaultSort": False}
        objects = with_display_units_off(vtype, objects or {})
        if objects:
            visual["objects"] = objects
        vco = dict(container or {})
        if title:
            vco["title"] = [{"properties": {"show": lit("true"), "text": lit(f"'{title}'")}}]
        if vco:
            visual["visualContainerObjects"] = vco
        visual["drillFilterOtherVisuals"] = True
        self.visuals.append({
            "$schema": f"{SCHEMA}/visualContainer/2.0.0/schema.json",
            "name": vid,
            "position": {"x": x, "y": y, "z": self.z, "height": h, "width": w, "tabOrder": self.z},
            "visual": visual,
        })

    def text(self, vid, x, y, w, h, runs):
        """runs: list of paragraphs, each a list of (text, style dict)."""
        paragraphs = [{"textRuns": [{"value": t, "textStyle": s} for t, s in para]} for para in runs]
        self.z += 1000
        self.visuals.append({
            "$schema": f"{SCHEMA}/visualContainer/2.0.0/schema.json",
            "name": vid,
            "position": {"x": x, "y": y, "z": self.z, "height": h, "width": w, "tabOrder": self.z},
            "visual": {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]},
                       "visualContainerObjects": {"background": [{"properties": {"show": lit("false")}}]},
                       "drillFilterOtherVisuals": True},
        })


H1 = {"fontSize": "20pt", "fontWeight": "bold"}
SUB = {"fontSize": "11pt", "color": "#605E5C"}
BODY = {"fontSize": "10pt"}
DROPDOWN = {"data": [{"properties": {"mode": lit("'Dropdown'")}}]}
SINGLE_VALUE = {"data": [{"properties": {"mode": lit("'Single'")}}]}


def single_value_at(entity: str, prop: str, value: str) -> dict:
    """Single-value numeric slider that opens on `value` (a "0D" style literal), saved the way Desktop does."""
    return {
        "data": [{"properties": {"mode": lit("'Single'"), "numericStart": lit(value)}}],
        "general": [{"properties": {"filter": {"filter": {
            "Version": 2,
            "From": [{"Name": "m", "Entity": entity, "Type": 0}],
            "Where": [{"Condition": {"Comparison": {
                "ComparisonKind": 0,
                "Left": {"Column": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": prop}},
                "Right": {"Literal": {"Value": value}},
            }}}],
        }}}}],
    }


def single_select():
    return {**DROPDOWN, "selection": [{"properties": {"singleSelect": lit("true")}}]}


def preselect(entity: str, prop: str, literal: str) -> dict:
    """Slicer objects that save a selected value, the way Desktop persists slicer state.
    literal is a DAX-style literal: "'Walmart'" for text, "2026L" for whole numbers."""
    return {"general": [{"properties": {"filter": {"filter": {
        "Version": 2,
        "From": [{"Name": "s", "Entity": entity, "Type": 0}],
        "Where": [{"Condition": {"In": {
            "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": prop}}],
            "Values": [[{"Literal": {"Value": literal}}]],
        }}}],
    }}}}]}


def slicer(p: "Page", vid: str, x, y, w, field, label: str, single=True, select=None, h=80):
    """Dropdown slicer. The header shows `label` (the projection's display name), so no separate title."""
    objects = single_select() if single else dict(DROPDOWN)
    if select:
        objects.update(preselect(*select))
    p.add(vid, "slicer", x, y, w, h, {"Values": [(field, label)]}, objects=objects)


# Hide the measure name under a card value; the visual title already says what it is.
NO_CARD_LABEL = {"categoryLabels": [{"properties": {"show": lit("false")}}]}
NO_TOTALS = {"subTotals": [{"properties": {"rowSubtotals": lit("false"), "columnSubtotals": lit("false")}}]}


def gradient(measure: str, lo: str = "-0.3D", hi: str = "0.3D") -> dict:
    """Matrix background color: red below 0, white at 0, green above, capped at lo/hi."""
    def stop(color, value):
        return {"color": {"Literal": {"Value": f"'{color}'"}}, "value": {"Literal": {"Value": value}}}
    return {"values": [{
        "properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {
            "Input": meas(measure),
            "FillRule": {"linearGradient3": {
                "min": stop("#E8746A", lo), "mid": stop("#FFFFFF", "0D"), "max": stop("#63B57A", hi),
                "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'noColor'"}}},
            }},
        }}}}}},
        "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f"_Measures.{measure}"},
    }]}


def header(p: Page, title: str, subtitle: str):
    p.text(f"{p.name}_title", 24, 12, 900, 70, [[(title, H1)], [(subtitle, SUB)]])


def cards(p: Page, prefix: str, items, x0, y, w, h, gap=16, vertical=False):
    for i, (m, t) in enumerate(items):
        x, yy = (x0, y + i * (h + gap)) if vertical else (x0 + i * (w + gap), y)
        p.add(f"{prefix}{i}", "card", x, yy, w, h, {"Values": [meas(m)]}, objects=NO_CARD_LABEL, title=t)


def build_pages() -> list[Page]:
    pages = []
    company = col("DimCompany", "Company")
    peer = col("DimCompany", "PeerGroup")
    fy = col("DimPeriod", "FiscalYear")
    label = col("DimPeriod", "FiscalLabel")
    walmart = ("DimCompany", "Company", "'Walmart'")

    p = Page("summary", "Summary")
    header(p, "Forecast vs Actual: how good were the forecasts?",
           "Each fiscal year, a driver-based forecast made with only the data available at the time, graded against reported results.")
    slicer(p, "summary_peer", 1006, 16, 250, peer, "Peer group", single=False)
    cards(p, "summary_card", [("Revenue MAPE (company-years)", "Average full-year revenue miss"),
                              ("Share Within 5%", "Company-years within 5%"),
                              ("Revenue Bias (company-years)", "Average bias (+ = beat forecast)"),
                              ("Beats Naive Share", "Beat a same-as-last-year forecast")], 24, 100, 296, 110)
    p.add("summary_bar", "clusteredBarChart", 24, 230, 600, 470,
          {"Category": [(company, "Company")], "Y": [(meas("Revenue MAPE (company-years)"), "Model"), (meas("Revenue MAPE (naive)"), "Same as last year")]},
          sort=(meas("Revenue MAPE (company-years)"), "Ascending"), title="Average revenue miss by company: model vs naive (lower is better)")
    p.add("summary_matrix", "pivotTable", 644, 230, 612, 250,
          {"Rows": [(peer, "Peer group")], "Values": [(meas("Revenue MAPE (company-years)"), "Avg miss"), (meas("Revenue MAPE (naive)"), "Naive avg miss"),
                                                     (meas("Share Within 5%"), "Within 5%"), (meas("Company-Years Scored"), "Company-years")]},
          title="By peer group")
    p.text("summary_note", 644, 500, 612, 200, [
        [("How to read this", {"fontSize": "11pt", "fontWeight": "bold"})],
        [("The driver model beats a naive same-as-last-year forecast in about 70% of company-years (13.5% vs 20.8% average miss) "
          "and runs slightly conservative: on average, revenue beat the forecast. Steady businesses (Walmart, Costco, Target, "
          "Microsoft) land within a few percent. The largest misses come from events a trend can't see: NVIDIA's AI boom, NRG "
          "buying Direct Energy, Schwab absorbing TD Ameritrade, and AMD's PC slump.", BODY)]])
    pages.append(p)

    p = Page("forecast_vs_actual", "Forecast vs actual")
    header(p, "Forecast vs actual by quarter", "Variances only count quarters that have both a forecast and a reported result.")
    slicer(p, "fva_company", 1006, 16, 250, company, "Company", select=walmart)
    p.add("fva_line", "lineChart", 24, 100, 1232, 300,
          {"Category": [(label, "Fiscal quarter")], "Y": [(meas("Revenue Actual"), "Actual"), (meas("Revenue Forecast"), "Forecast")]},
          sort=(label, "Ascending"), title="Revenue: actual vs forecast")
    p.add("fva_matrix", "pivotTable", 24, 420, 1232, 280, {"Rows": [(fy, "Fiscal year")], "Values": [
        (meas("Revenue Act (c)"), "Revenue actual"), (meas("Revenue Fcst (c)"), "Revenue forecast"), (meas("Revenue Variance"), "Variance"),
        (meas("Revenue Variance %"), "Variance %"), (meas("Revenue Variance Flag"), "Revenue"),
        (meas("Operating Income Variance"), "Op. income variance"), (meas("Operating Income Variance %"), "Op. income variance %")]},
        objects=gradient("Revenue Variance %", "-0.15D", "0.15D"), title="Variance by fiscal year")
    pages.append(p)

    p = Page("variance_bridge", "Variance bridge")
    header(p, "Why did operating income miss?", "Forecast operating income, plus the revenue, gross margin and opex effects, equals actual operating income.")
    slicer(p, "bridge_company", 740, 16, 250, company, "Company", select=walmart)
    slicer(p, "bridge_year", 1006, 16, 250, fy, "Fiscal year", select=("DimPeriod", "FiscalYear", "2026L"))
    p.add("bridge_waterfall", "waterfallChart", 24, 100, 820, 600,
          {"Category": [(col("BridgeSteps", "Step"), "Step")], "Y": [(meas("Bridge Value"), "Operating income")]},
          sort=(col("BridgeSteps", "Step"), "Ascending"),
          objects={"labels": [{"properties": {"show": lit("true")}}]}, title="Operating income: forecast to actual")
    cards(p, "bridge_card", [("Assumed Revenue Growth", "Growth the forecast assumed"), ("Revenue YoY %", "Growth that happened"),
                             ("Revenue Variance %", "Revenue vs forecast"), ("Operating Income Variance", "Operating income vs forecast")],
          864, 100, 392, 135, gap=20, vertical=True)
    pages.append(p)

    p = Page("accuracy_over_time", "Accuracy over time")
    header(p, "When do simple forecasts break?", "Full-year revenue variance by company and fiscal year. Positive means revenue beat the forecast.")
    p.add("acc_matrix", "pivotTable", 24, 100, 880, 400,
          {"Rows": [(company, "Company")], "Columns": [(fy, "Fiscal year")], "Values": [(meas("Revenue Variance % (full years)"), "Variance %")]},
          objects={**gradient("Revenue Variance % (full years)"), **NO_TOTALS}, title="Revenue variance % (complete fiscal years)")
    p.add("acc_by_year", "clusteredColumnChart", 24, 515, 880, 185,
          {"Category": [(fy, "Fiscal year")], "Y": [(meas("Revenue MAPE (company-years)"), "Model"), (meas("Revenue MAPE (naive)"), "Same as last year")]},
          sort=(fy, "Ascending"), title="Average miss by fiscal year: 2021 (post-COVID rebound and M&A) was the hardest")
    p.text("acc_notes", 924, 100, 332, 600, [
        [("The big misses", {"fontSize": "12pt", "fontWeight": "bold"})],
        [("NVIDIA FY2024: ", {"fontSize": "10pt", "fontWeight": "bold"}), ("the AI data center boom. Revenue came in about 92% above a forecast built on the prior trend.", BODY)],
        [("NRG 2021: ", {"fontSize": "10pt", "fontWeight": "bold"}), ("the Direct Energy acquisition closed in January 2021.", BODY)],
        [("Robinhood 2023: ", {"fontSize": "10pt", "fontWeight": "bold"}), ("the forecast extrapolated the 2022 slump, then higher rates lifted interest income.", BODY)],
        [("Schwab 2021: ", {"fontSize": "10pt", "fontWeight": "bold"}), ("the first full year after buying TD Ameritrade.", BODY)],
        [("AMD 2023: ", {"fontSize": "10pt", "fontWeight": "bold"}), ("the PC downturn.", BODY)],
        [("The lesson: a trend-based driver model is a strong baseline for steady businesses, and needs judgment overlays for M&A, "
          "rate regimes and product cycles.", BODY)]])
    pages.append(p)

    p = Page("peer_benchmarking", "Peer benchmarking")
    header(p, "Peer benchmarking", "Growth vs profitability for the selected fiscal year, and any metric over time.")
    slicer(p, "peer_group", 740, 16, 250, peer, "Peer group", single=False)
    slicer(p, "peer_year", 1006, 16, 250, fy, "Fiscal year", select=("DimPeriod", "FiscalYear", "2025L"))
    p.add("peer_scatter", "scatterChart", 24, 100, 600, 600,
          {"Category": [(company, "Company")], "X": [(meas("Revenue YoY %"), "Revenue growth")], "Y": [(meas("Operating Margin (reported)"), "Operating margin")]},
          objects={"categoryLabels": [{"properties": {"show": lit("true")}}]}, title="Revenue growth (x) vs operating margin (y)")
    slicer(p, "peer_metric", 644, 100, 612, col("Metric", "Metric"), "Metric", select=("Metric", "Metric", "'Revenue TTM'"))
    # The Metric field parameter goes in Y as the selected measure plus a fieldParameters pointer,
    # which is how Desktop saves it; a bare column reference to Metric breaks the visual.
    # The fiscal year slicer is for the scatter; the trend chart should keep showing every year.
    p.no_filter.append(("peer_year", "peer_line"))
    p.add("peer_line", "lineChart", 644, 190, 612, 510,
          {"Category": [(fy, "Fiscal year")], "Y": [meas("Revenue TTM")], "Series": [(company, "Company")]},
          sort=(fy, "Ascending"), title="Metric by fiscal year (Revenue TTM keeps the current, partial year comparable)",
          field_params={"Y": col("Metric", "Metric")})
    pages.append(p)

    p = Page("scenario_planner", "Scenario planner")
    header(p, "Scenario planner: current fiscal year", "Flex the forecast's growth and margin assumptions. Reported quarters stay at actual in the outlook.")
    slicer(p, "sc_company", 1006, 16, 250, company, "Company", select=walmart)
    p.add("sc_growth", "slicer", 24, 100, 400, 110, {"Values": [(col("Growth Adjustment", "Growth Adjustment (pts)"), "Growth adjustment (percentage points)")]},
          objects=single_value_at("Growth Adjustment", "Growth Adjustment (pts)", "0D"))
    p.add("sc_margin", "slicer", 444, 100, 400, 110, {"Values": [(col("Margin Adjustment", "Margin Adjustment (pts)"), "Operating margin adjustment (percentage points)")]},
          objects=single_value_at("Margin Adjustment", "Margin Adjustment (pts)", "0D"))
    cards(p, "sc_card", [("Revenue Base (latest)", "Base forecast revenue"), ("Revenue Scenario", "Scenario revenue"),
                         ("Revenue Outlook", "Outlook (actuals + scenario)"), ("Operating Income Scenario", "Scenario operating income")],
          24, 225, 296, 110)
    p.add("sc_columns", "clusteredColumnChart", 24, 355, 1232, 345,
          {"Category": [(label, "Fiscal quarter")],
           "Y": [(meas("Revenue Base (latest)"), "Base forecast"), (meas("Revenue Scenario"), "Scenario"), (meas("Revenue Actual (current year)"), "Actual")]},
          sort=(label, "Ascending"), title="Current fiscal year by quarter: base forecast, scenario and actual")
    pages.append(p)
    return pages


def write_report() -> None:
    if REPORT.exists():
        shutil.rmtree(REPORT)
    d = REPORT / "definition"
    (d / "pages").mkdir(parents=True)
    themes = REPORT / "StaticResources" / "SharedResources" / "BaseThemes"
    themes.mkdir(parents=True)
    shutil.copy(HERE / "base_theme_CY23SU04.json", themes / "CY23SU04.json")

    def dump(path: Path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2) + "\n")

    dump(REPORT / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    dump(d / "version.json", {"$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    dump(d / "report.json", {
        "$schema": f"{SCHEMA}/report/1.3.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "CY23SU04", "reportVersionAtImport": "5.46", "type": "SharedResources"}},
        "layoutOptimization": "None",
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources",
                              "items": [{"name": "CY23SU04", "path": "BaseThemes/CY23SU04.json", "type": "BaseTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True, "useEnhancedTooltips": True},
    })
    pages = build_pages()
    dump(d / "pages" / "pages.json", {"$schema": f"{SCHEMA}/pagesMetadata/1.0.0/schema.json",
                                      "pageOrder": [p.name for p in pages], "activePageName": pages[0].name})
    for p in pages:
        page = {"$schema": f"{SCHEMA}/page/1.4.0/schema.json", "name": p.name,
                "displayName": p.display, "displayOption": "FitToPage", "height": 720, "width": 1280}
        if p.no_filter:
            page["visualInteractions"] = [{"source": src, "target": tgt, "type": "NoFilter"} for src, tgt in p.no_filter]
        dump(d / "pages" / p.name / "page.json", page)
        for v in p.visuals:
            dump(d / "pages" / p.name / "visuals" / v["name"] / "visual.json", v)


def main() -> None:
    tables = write_model()
    write_report()
    (HERE / f"{NAME}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}], "settings": {"enableAutoRecovery": True}}, indent=2) + "\n")
    n_visuals = sum(len(p.visuals) for p in build_pages())
    print(f"Wrote {NAME}.pbip: {len(tables)} tables, {len(MEASURES)} measures, {len(RELATIONSHIPS)} relationships, 6 pages, {n_visuals} visuals")


if __name__ == "__main__":
    main()
