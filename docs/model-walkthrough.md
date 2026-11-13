# How the report works: interview walkthrough

Use this to explain the project in your own words. Each section covers what the piece does, why it's built that way, and the interview question it answers.

## The 30-second version

> "I wanted to show FP&A forecasting on real data, but public companies don't publish budgets, so I made my own. For 15 companies, I stood at the start of every fiscal year since 2019 and forecast the next four quarters using only what was known at the time: revenue growth, gross margin and opex as a share of revenue. Then I graded those forecasts against what the companies reported to the SEC. Steady businesses like Walmart came within 1%. The big misses were real events, like NVIDIA's AI boom and Schwab buying TD Ameritrade. The report breaks every miss into revenue, margin and cost effects, so you can see why each one happened."

## Data model

The model is a star schema. Two dimension tables, **DimCompany** and **DimPeriod**, filter the fact tables **FactActuals** and **FactForecast**. The **Calendar** table filters DimPeriod by quarter-end date.

- **Why DimPeriod is per company.** Every company has its own fiscal calendar. Walmart's year ends in January, Costco's in August, Microsoft's in June. One row per company-quarter keeps each company on the calendar its own FP&A team uses, and the Calendar table still lets you slice by real dates.
- **Why there's no relationship between DimCompany and DimPeriod.** Both already reach the fact tables. A second path would make filtering ambiguous, which is a classic modeling mistake.
- **Why the fact tables aren't joined to each other.** Actuals and forecasts meet through the shared dimensions. That's the standard way to compare two fact tables at the same grain.
- **FactDrivers** holds the assumptions behind each forecast. It connects to the selected fiscal year inside the measures (with `TREATAS`) rather than through a relationship, because the vintage *is* the fiscal year.

*Likely question: "Walk me through your data model."*

## Comparable quarters

Every variance measure uses the `(c)` versions, such as `Revenue Act (c)`. These only count quarters that have **both** a forecast and a reported result.

**Why:** if Q3 is forecast but not reported yet, a plain sum would treat it as revenue of zero, which looks like a 25% miss. Comparing like with like is the first rule of variance reporting.

*Likely question: "How do you handle partial periods?"*

## Variance and the favorable/unfavorable flag

- **Variance** is actual minus forecast. Variance % divides by the forecast.
- **The flag depends on the line item.** More revenue than forecast is favorable; more opex than forecast is unfavorable. That's why there are separate flags for revenue and opex.

*Likely question: "How do you present a variance to a CFO?"*

## The operating income bridge

Operating income = revenue × operating margin. So the gap between forecast and actual splits exactly into two parts:

| Effect | Formula | Meaning |
|---|---|---|
| Revenue (volume) | (actual revenue − forecast revenue) × forecast margin | What selling more or less was worth, at the margin we planned |
| Margin | actual revenue × (actual margin − forecast margin) | What earning a different margin was worth, on what we actually sold |

When the company has a gross margin, the margin effect splits further into a **gross margin effect** (pricing and cost of goods) and an **opex effect** (spending discipline). The pieces always add up to the total variance. The Python pipeline checks this for all 98 company-years, and the waterfall total proves it in the report.

**Example, Walmart FY2026:** operating income came in $1.14B under forecast. Revenue was slightly light (−$0.23B) and gross margin was better than planned (+$0.54B), but opex ran higher than planned (−$1.45B). So the miss was a cost story, not a sales story.

**Example, NVIDIA FY2024:** operating income was $28B over forecast. Most of it came from operating leverage (opex +$13.8B) and gross margin (+$9.6B), not just volume. Revenue nearly doubled while costs didn't.

*Likely question: "Revenue was on plan but profit missed. How would you explain it?"*

## Forecast accuracy

- **Revenue MAPE** is the average absolute full-year miss, counting each company-year once. It's 13.5%.
- **The median is 7.4%.** A few huge misses (NVIDIA, NRG) pull the average up, which is why the report shows both views. Being able to explain a skewed average is a good analyst point.
- **Share within 5%** is how often the forecast landed within 5%: 40% of company-years.

- **Benchmark:** the model is compared against a naive "same as last year" forecast. It wins in 70% of company-years (13.5% vs 20.8% average miss). Without a benchmark, an accuracy number means little.
- **Bias:** on average, actual revenue beat the forecast by 2.8%, so the model leans conservative. Bias and accuracy are different questions. A forecast can be accurate on average and still be consistently low, and a CFO cares about both.

*Likely question: "How do you measure whether a forecast is good?"*

## Time intelligence on fiscal calendars

- **Prior year** shifts by fiscal year and keeps the same fiscal quarter, using `TREATAS`.
- **Why not `SAMEPERIODLASTYEAR`:** it shifts calendar dates, and with 52/53-week years and different year-ends that can land on the wrong quarter.
- **Revenue TTM** (last 12 months) uses `DATESINPERIOD` on the Calendar table, ending at the latest quarter in view.
- **The `Time View` calculation group** applies current, prior year and YoY % to *any* measure, so one set of logic replaces dozens of near-duplicate measures. That's the main reason calculation groups exist.

*Likely question: "How do you handle a fiscal year that isn't the calendar year?"*

## Field parameter and scenario sliders

- **The `Metric` field parameter** lets one chart switch between revenue, gross profit, operating income, net income, margin and TTM revenue.
- **The two sliders** (what-if parameters) add percentage points to the forecast's growth and margin assumptions for the current year.
- **`Revenue Outlook`** keeps reported quarters at actual and applies the scenario only to quarters still ahead. That's how a rolling forecast works in practice.

*Likely question: "How would you build a scenario or sensitivity analysis?"*

## Row-level security

The `Retail coverage` role limits a user to the Retail peer group. Test it with *Modeling → View as*. In a real company you'd map roles to users' coverage areas, or use dynamic security with `USERPRINCIPALNAME()`.

*Likely question (PL-300): "Static vs dynamic row-level security?"*

## What the project shows about you

- You can take messy source data (SEC XBRL tags, fiscal calendars, derived fourth quarters) and validate it to the dollar.
- You think like FP&A: no hindsight, only compare like with like, explain variances by driver.
- You can build the full Power BI stack: Power Query, star schema, DAX, calculation groups, parameters and security.
- You can tell the story behind the numbers: where trend forecasts work, and where judgment has to step in.
