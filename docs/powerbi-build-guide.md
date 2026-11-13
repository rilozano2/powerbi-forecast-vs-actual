# Power BI build guide

There are two ways to use this guide.

- **Open the generated project (fastest).** `powerbi/ForecastVsActual.pbip` already contains everything below: the data model, all 50 measures, the calculation group, the field parameter, the what-if sliders, the security role and the six pages. See "Open the generated project" just below.
- **Rebuild it yourself (best PL-300 practice).** Follow the six sessions in order. Each step is tagged with the PL-300 skill it practices. Rebuilding at least the variance bridge page is worth it, so you can say in an interview that you built it and know how it works.

## Open the generated project

1. **Update Power BI Desktop.** The project uses the current report format (PBIR), so use a release from September 2026 or later. Microsoft Store versions update on their own.
2. **Open the file.** In the Windows VM, open `\\Mac\Home\forecast-vs-actual\powerbi\ForecastVsActual.pbip` (*File → Open*).
3. **Load the data.** Click **Refresh**. If Power BI can't find the files, go to *Transform data → Manage parameters → DataFolder* and point it at the `data\processed\` folder, ending with a backslash.
   - If you're asked about privacy levels, choose *Ignore privacy levels* or set both to *Organizational*. The data is all public.
4. **Check it loaded correctly:**
   - The Summary page should show an average miss of about 13.5%, 39.8% within 5%, an average bias of about +2.8%, and the model beating the naive forecast about 70% of the time.
   - On the Variance bridge page, pick Walmart and FY2026. The waterfall should go from $30.96B forecast, then −$0.23B revenue, +$0.54B gross margin and −$1.45B opex, to $29.82B actual.
5. **Finish the formatting.** These are faster to click than to code:
   - **Accuracy over time matrix:** *Format → Cell elements → Background color → fx*, gradient from red (negative) through white (0) to green (positive).
   - **Variance matrix:** color `Revenue Variance` by rules (green when ≥ 0, red when < 0).
   - **Waterfall:** under *Sentiment colors*, set increase to green and decrease to red.
   - Tidy anything that looks cramped, then *File → Save*. Desktop keeps the project format.
6. **Save a .pbix copy to share:** *File → Save as → Power BI file (.pbix)*, and put it in `report/`.

If Desktop reports an error when opening, it names the file and line. Send me the message, then run `python3 powerbi/generate_pbip.py` again after the fix.

---

## Session 1: Get and shape the data (PL-300: prepare the data)

1. **Create a parameter for the data folder.** *Home → Transform data → Manage parameters → New*. Name it `DataFolder`, type Text, value `\\Mac\Home\forecast-vs-actual\data\processed\`. Every query will build its path from this, so the report can be pointed at a new folder in one place.

2. **Load the six tables.** For each file, use *Get data → Text/CSV* and then, in the Advanced Editor, replace the hard-coded path with `DataFolder & "fact_actuals.csv"`, and so on.

   | Query name | File | What it is |
   |---|---|---|
   | `DimCompany` | dim_company.csv | 15 companies, peer group, whether gross margin applies |
   | `DimPeriod` | dim_period.csv | One row per company fiscal quarter, with start and end dates |
   | `FactActuals` | fact_actuals.csv | Reported quarterly results from SEC filings |
   | `FactForecast` | fact_forecast.csv | Forecasts made at the start of each fiscal year (the "vintage") |
   | `FactDrivers` | fact_drivers.csv | The assumptions behind each vintage |
   | `CheckValues` | check_values.csv | Reference answers for checking your measures (hide it later) |

3. **Set data types explicitly.** Don't trust auto-detect:
   - money columns: Decimal Number, then Currency format in the model
   - `PeriodStart` and `PeriodEnd`: Date
   - `FiscalYear` and `FiscalQuarter`: Whole Number
   - `HasGrossMargin` and `IsReported`: True/False
   - drivers: Decimal Number

4. **Profile the data.** Turn on *View → Column quality, Column distribution, Column profile* and set profiling to the entire dataset (bottom-left of the editor). `GrossProfit` is empty for Target, the power companies and the brokers. That's expected; write down why, because interviewers like hearing that you checked.

5. **Add a sort column.** In `DimPeriod`, add a custom column `PeriodSort = [FiscalYear] * 10 + [FiscalQuarter]`.

6. **Close & Apply.**

## Session 2: Model the data (PL-300: model the data)

1. **Build a date table** with DAX (*Modeling → New table*), then mark it as the date table (*Table tools → Mark as date table*):
   ```DAX
   Calendar =
   ADDCOLUMNS (
       CALENDAR ( DATE ( 2014, 1, 1 ), DATE ( 2028, 12, 31 ) ),
       "Year", YEAR ( [Date] ),
       "Month", FORMAT ( [Date], "MMM" ),
       "MonthNumber", MONTH ( [Date] ),
       "CalendarQuarter", "Q" & QUARTER ( [Date] )
   )
   ```

2. **Create the relationships.** All are single direction, one-to-many. This is a star schema with one snowflake (Calendar → DimPeriod):

   | From (one side) | To (many side) | Key |
   |---|---|---|
   | DimCompany | FactActuals | Ticker |
   | DimCompany | FactForecast | Ticker |
   | DimCompany | FactDrivers | Ticker |
   | DimPeriod | FactActuals | PeriodKey |
   | DimPeriod | FactForecast | PeriodKey |
   | Calendar | DimPeriod | Date → PeriodEnd |

   Don't relate DimCompany to DimPeriod. Both already reach the facts, and a second path would create ambiguity. Be ready to explain this choice.

3. **Set sort orders and hide what users shouldn't touch.**
   - Sort `DimPeriod[FiscalLabel]` by `PeriodSort`.
   - Hide every key column on the many side.
   - Hide `CheckValues`.

4. **Create a `_Measures` table** (*Enter data*, one empty column you then delete) to hold every measure below. Put them in display folders: Actuals, Forecast, Variance, Bridge, Accuracy, Scenario.

## Session 3: Core measures (PL-300: DAX calculations)

**Actuals and forecast**
```DAX
Revenue Actual = SUM ( FactActuals[Revenue] )
Revenue Forecast = SUM ( FactForecast[Revenue] )
Gross Profit Actual = SUM ( FactActuals[GrossProfit] )
Gross Profit Forecast = SUM ( FactForecast[GrossProfit] )
Opex Actual = SUM ( FactActuals[OperatingExpenses] )
Opex Forecast = SUM ( FactForecast[OperatingExpenses] )
Operating Income Actual = SUM ( FactActuals[OperatingIncome] )
Operating Income Forecast = SUM ( FactForecast[OperatingIncome] )
```

**Compare only quarters that have both.** This is the key FP&A idea in the model. A variance is only fair over periods with both a forecast and an actual; otherwise unreported quarters would look like a 100% miss.
```DAX
Comparable Quarters =
COUNTROWS (
    FILTER ( DimPeriod,
        NOT ISBLANK ( [Revenue Forecast] ) && NOT ISBLANK ( [Revenue Actual] ) )
)

Revenue Act (c) =
SUMX ( FILTER ( DimPeriod, NOT ISBLANK ( [Revenue Forecast] ) ), [Revenue Actual] )

Revenue Fcst (c) =
SUMX ( FILTER ( DimPeriod, NOT ISBLANK ( [Revenue Actual] ) ), [Revenue Forecast] )
```
Write the same `(c)` pair for Gross Profit, Opex and Operating Income by swapping the measure names.

**Variance**
```DAX
Revenue Variance = [Revenue Act (c)] - [Revenue Fcst (c)]
Revenue Variance % = DIVIDE ( [Revenue Variance], [Revenue Fcst (c)] )
Operating Income Variance = [Operating Income Act (c)] - [Operating Income Fcst (c)]
Operating Income Variance % =
DIVIDE ( [Operating Income Variance], ABS ( [Operating Income Fcst (c)] ) )

-- Revenue above forecast is favorable; for costs it is the reverse.
Revenue Variance Flag = IF ( [Revenue Variance] >= 0, "Favorable", "Unfavorable" )
Opex Variance Flag =
IF ( [Opex Act (c)] <= [Opex Fcst (c)], "Favorable", "Unfavorable" )
```

**Margins**
```DAX
Operating Margin Actual = DIVIDE ( [Operating Income Act (c)], [Revenue Act (c)] )
Operating Margin Forecast = DIVIDE ( [Operating Income Fcst (c)], [Revenue Fcst (c)] )
Gross Margin Actual = DIVIDE ( [Gross Profit Act (c)], [Revenue Act (c)] )
Gross Margin Forecast = DIVIDE ( [Gross Profit Fcst (c)], [Revenue Fcst (c)] )
```

**Check your work.** Build a table with `DimCompany[Ticker]`, `DimPeriod[FiscalYear]`, `Revenue Variance` and `Operating Income Variance`. For WMT FY2026, NVDA FY2024 and SCHW FY2021, the values must match the same columns in `CheckValues`. If they don't, fix it before moving on.

## Session 4: Variance bridge and accuracy (PL-300: DAX, visuals)

**The bridge.** Operating income is revenue × operating margin, so the gap from forecast splits exactly into a revenue (volume) effect and a margin effect. When gross margin exists, the margin effect splits further into gross margin and opex. The pieces always add up to the total variance.
```DAX
Bridge Revenue Effect = [Revenue Variance] * [Operating Margin Forecast]
Bridge Margin Effect = [Revenue Act (c)] * ( [Operating Margin Actual] - [Operating Margin Forecast] )
Bridge Gross Margin Effect = [Revenue Act (c)] * ( [Gross Margin Actual] - [Gross Margin Forecast] )
Bridge Opex Effect =
-1 * [Revenue Act (c)]
    * ( DIVIDE ( [Opex Act (c)], [Revenue Act (c)] ) - DIVIDE ( [Opex Fcst (c)], [Revenue Fcst (c)] ) )

Has Gross Margin (all selected) = ISEMPTY ( FILTER ( DimCompany, NOT DimCompany[HasGrossMargin] ) )
```

**Waterfall chart.**
1. Create a table with *Enter data* named `BridgeSteps`, with columns `Step` and `Order`:
   - Forecast operating income, 1
   - Revenue effect, 2
   - Gross margin effect, 3
   - Opex effect, 4
   - Operating margin effect, 5
2. Sort `Step` by `Order`.
3. Add this measure:
   ```DAX
   Bridge Value =
   VAR gm = [Has Gross Margin (all selected)]
   RETURN
       SWITCH ( SELECTEDVALUE ( BridgeSteps[Step] ),
           "Forecast operating income", [Operating Income Fcst (c)],
           "Revenue effect", [Bridge Revenue Effect],
           "Gross margin effect", IF ( gm, [Bridge Gross Margin Effect] ),
           "Opex effect", IF ( gm, [Bridge Opex Effect] ),
           "Operating margin effect", IF ( NOT gm, [Bridge Margin Effect] )
       )
   ```
4. Use a waterfall visual with Category = `BridgeSteps[Step]` and Y = `Bridge Value`, with the total turned on and renamed "Actual operating income". The total bar should equal `Operating Income Act (c)`, which is your proof the bridge ties out.

**Forecast accuracy.** Each company-year with all 4 quarters counts once.
```DAX
Revenue Abs % Error = ABS ( [Revenue Variance %] )

Revenue MAPE (company-years) =
AVERAGEX (
    FILTER (
        CROSSJOIN ( VALUES ( DimCompany[Ticker] ), VALUES ( DimPeriod[FiscalYear] ) ),
        [Comparable Quarters] = 4
    ),
    [Revenue Abs % Error]
)

Share Within 5% =
VAR years =
    FILTER ( CROSSJOIN ( VALUES ( DimCompany[Ticker] ), VALUES ( DimPeriod[FiscalYear] ) ),
        [Comparable Quarters] = 4 )
RETURN DIVIDE ( COUNTROWS ( FILTER ( years, [Revenue Abs % Error] <= 0.05 ) ), COUNTROWS ( years ) )
```
Expect about 40% within 5% and an average miss of about 13.5% (the median is 7.4%; NVIDIA and NRG pull the average up). Walmart, Costco and Target should be the most accurate.

**Benchmark against a naive forecast.** A forecast is only useful if it beats a simple rule. The naive benchmark is "same quarters as last year":
```DAX
Naive Fcst (c) =
SUMX (
    FILTER ( DimPeriod, NOT ISBLANK ( [Revenue Forecast] ) && NOT ISBLANK ( [Revenue Actual] ) ),
    VAR t = DimPeriod[Ticker]
    RETURN CALCULATE ( [Revenue PY], DimCompany[Ticker] = t )
)
```
`Revenue MAPE (naive)` and `Beats Naive Share` follow the same pattern as the accuracy measures above. `Revenue Bias (company-years)` is the average *signed* miss, which shows whether the forecast leans optimistic or conservative. Build `Revenue PY` (Session 5) first.

## Session 5: Time intelligence, calculation groups and field parameters (PL-300: advanced modeling)

**Prior year and last-12-months revenue on fiscal quarters.**
```DAX
Revenue PY =
VAR yrs = SELECTCOLUMNS ( VALUES ( DimPeriod[FiscalYear] ), "y", DimPeriod[FiscalYear] - 1 )
VAR qs = VALUES ( DimPeriod[FiscalQuarter] )
RETURN
    CALCULATE ( [Revenue Actual], REMOVEFILTERS ( DimPeriod ), TREATAS ( yrs, DimPeriod[FiscalYear] ), qs )

Revenue YoY % = DIVIDE ( [Revenue Actual] - [Revenue PY], [Revenue PY] )

Revenue TTM =
VAR e = MAX ( DimPeriod[PeriodEnd] )
RETURN CALCULATE ( [Revenue Actual], REMOVEFILTERS ( DimPeriod ), DATESINPERIOD ( 'Calendar'[Date], e, -12, MONTH ) )
```
Be ready to explain why `SAMEPERIODLASTYEAR` isn't used here: fiscal quarters end on different dates for each company, so shifting by fiscal year and quarter is more reliable.

**Calculation group.** In *Model view*, create a calculation group named `Time View` with these items:
- `Current` = `SELECTEDMEASURE ()`
- `Prior year` = the `Revenue PY` pattern, with `SELECTEDMEASURE ()` in place of `[Revenue Actual]`
- `YoY %` = `DIVIDE ( SELECTEDMEASURE () - <Prior year expression>, <Prior year expression> )`, with a format string expression of `"0.0%"`

Put it on the columns of a matrix to show any actual measure as current, prior year and YoY.

**Field parameter.** *Modeling → New parameter → Fields*, named `Metric`, with Revenue Actual, Gross Profit Actual, Operating Income Actual and Net Income Actual. Use it as a slicer so one trend chart can show any metric.

## Session 6: Scenario planner, security, pages and publishing

**Scenario sliders.** Create two numeric-range parameters with *Modeling → New parameter → Numeric range*:
- `Growth Adjustment`: −20 to 20 percentage points, step 1, default 0
- `Margin Adjustment`: −10 to 10 percentage points, step 0.5, default 0

Working in points keeps the slider labels readable. The generated project's value measures divide by 100: `Growth Adjustment Value = DIVIDE ( SELECTEDVALUE ( 'Growth Adjustment'[Growth Adjustment (pts)], 0 ), 100 )`.

Then add these measures:
```DAX
-- Calculated column on FactForecast
Is Latest Vintage Row =
FactForecast[Vintage] = CALCULATE ( MAX ( FactForecast[Vintage] ), ALLEXCEPT ( FactForecast, FactForecast[Ticker] ) )

Revenue Scenario =
SUMX (
    FILTER ( FactForecast, FactForecast[Is Latest Vintage Row] ),
    FactForecast[BaseRevenue] * ( 1 + FactForecast[RevenueGrowth] + [Growth Adjustment Value] )
)

Operating Income Scenario =
SUMX (
    FILTER ( FactForecast, FactForecast[Is Latest Vintage Row] ),
    FactForecast[BaseRevenue] * ( 1 + FactForecast[RevenueGrowth] + [Growth Adjustment Value] )
        * ( FactForecast[OperatingMargin] + [Margin Adjustment Value] )
)

-- Reported quarters at actual, the rest of the year at the scenario.
Revenue Outlook =
SUMX (
    FILTER ( FactForecast, FactForecast[Is Latest Vintage Row] ),
    IF ( RELATED ( DimPeriod[IsReported] ),
        LOOKUPVALUE ( FactActuals[Revenue], FactActuals[PeriodKey], FactForecast[PeriodKey] ),
        FactForecast[BaseRevenue] * ( 1 + FactForecast[RevenueGrowth] + [Growth Adjustment Value] ) )
)
```
`Is Latest Vintage Row` is a calculated column, not a measure. Add it to `FactForecast` with *New column*.

**Row-level security.** *Modeling → Manage roles → New*: create a role `Retail coverage` with the filter `[PeerGroup] = "Retail"` on `DimCompany`. Test it with *View as*. Expect the exam to ask about static and dynamic RLS; this is the static version.

**Pages to build:**

| Page | Visuals | Question it answers |
|---|---|---|
| Summary | KPI cards (MAPE, share within 5%, total revenue variance), accuracy-by-company bar chart, peer group slicer | How good were the forecasts overall? |
| Forecast vs actual | Line chart of actual vs forecast by `FiscalLabel`; variance matrix with conditional formatting (green favorable, red unfavorable) | Where did each company beat or miss? |
| Variance bridge | Waterfall; slicers for company and fiscal year; drivers table from `FactDrivers` | Why did operating income miss: volume, margin or cost? |
| Accuracy over time | Matrix of company × vintage colored by `Revenue Variance %`, with text boxes on the big misses | When do simple driver models break? |
| Peer benchmarking | Scatter of revenue growth vs operating margin by company; small multiples of margin trends; the field parameter slicer | Who grows faster and more profitably than peers? |
| Scenario planner | Sliders for both parameters; cards and a column chart for the outlook vs the base forecast | What if growth or margins come in different? |

**Notes to add on the accuracy page.** These are the misses where the story is the business, not the model:
- **NVIDIA FY2024:** the AI data center boom. Revenue came in about 92% above a forecast that extrapolated the prior trend.
- **NRG 2021:** the acquisition of Direct Energy closed in January 2021.
- **Schwab 2021:** the first full year after buying TD Ameritrade.
- **AMD 2023:** the PC downturn.
- **Robinhood 2023:** the forecast extrapolated the 2022 slump, then higher rates lifted interest income and revenue came in about 72% above it.

**Share it:**
- Export to PDF (*File → Export → PDF*).
- Take a screenshot of each page into `docs/screenshots/`.
- Save the `.pbix` in `report/`.
- If your account allows it, publish to *My workspace* to practice the service side of the exam: refresh, sharing settings, apps.

---

## PL-300 coverage

| Exam area | Where you practice it |
|---|---|
| Prepare the data: get data, parameters, profiling, data types | Session 1 |
| Model the data: star schema, relationships, date table, sort by column, hiding | Session 2 |
| DAX: SUMX, FILTER, CALCULATE, DIVIDE, SWITCH, iterators, context transition | Sessions 3, 4, 6 |
| Time intelligence: DATESINPERIOD, TREATAS shifting, marking the date table | Session 5 |
| Calculation groups, field parameters, what-if parameters | Sessions 5, 6 |
| Visualize: waterfall, conditional formatting, small multiples, scatter, slicers | Sessions 4, 6 |
| Secure: row-level security, View as | Session 6 |
| Deploy: publish, export, workspace basics | Session 6 |
