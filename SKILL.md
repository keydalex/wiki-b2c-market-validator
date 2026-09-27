---
name: wiki-b2c-market-validator
description: Validate B2C product market demand, assess topic growth trustworthiness, detect viral hype vs organic interest, and prioritize localization markets using Wikimedia Pageviews Analytics.
version: 1.0.0
author: AI Engineering
---

# Wiki B2C Market Validator (Agent Skill)

An autonomous skill for AI agents (specifically optimized for fast, cost-effective models like **Claude 3.5/4.5 Haiku** and **Gemini 1.5/2.0 Flash**) to assist B2C product founders, venture studios, and growth teams in validating market demand before allocating capital.

---

## 1. When to Use This Skill

Activate this skill whenever a founder or product manager asks:
- **Market Expansion / Localization**: *"Which language market should we localize our language learning app into next?"*
- **Curriculum / Feature Validation**: *"We want to launch an Astronomy course in our educational app. Is interest growing in Ukrainian Wikipedia, and can this growth be trusted?"*
- **Trend Verification / Hype vs. Reality**: *"Compare the rise of intermittent fasting in Poland vs. the Czech Republic over the last 2 years."*
- **TAM Estimation**: *"Estimate the relative market demand for topic X compared to established benchmark Y."*

---

## 2. CLI Execution Interface

To minimize token usage and prevent mathematical hallucinations, **never** attempt to download raw daily pageviews directly into your LLM context window. Instead, invoke the deterministic local CLI runner:

```bash
# Basic single or multi-language market validation
python -m wiki_market_validator.cli \
  --target "<topic_name>" \
  --langs "<comma_separated_language_codes>" \
  --years <number_of_years> \
  --output-pdf "<path_to_report.pdf>" \
  --output-png "<path_to_chart.png>" \
  --output-json "<path_to_summary.json>"
```

### Key CLI Flags:
| Flag | Description | Example |
| :--- | :--- | :--- |
| `--target` | Primary topic / concept name (in English or local language) | `--target "Intermittent fasting"` |
| `--target-titles` | Explicit per-language overrides if known | `--target-titles "pl:Głodówka,cs:Přerušovaný_půst"` |
| `--langs` | Comma-separated ISO language codes | `--langs "es,de,pl,uk,ja"` |
| `--years` | Lookback period in years (default: 2.0) | `--years 2.0` |
| `--benchmark` | Established reference topic for TAM proxy estimation | `--benchmark "Physics"` |
| `--start` / `--end` | Explicit date range (`YYYYMMDD`) | `--start 20230101 --end 20250101` |
| `--output-pdf` | Path to build strict **1-Page Executive PDF** | `--output-pdf report.pdf` |
| `--output-png` | Path to build publication-grade **300 DPI chart** | `--output-png chart.png` |
| `--no-cache` | Disable SQLite cache (default: caching is active) | `--no-cache` |

---

## 3. Step-by-Step Agent Reasoning Protocol

When processing a user query, follow this 4-step protocol:

### Step 1: Query Deconstruction
1. Identify the **core topic** (e.g. "Astronomy", "Intermittent fasting").
2. Identify the **target language markets** (e.g. `uk` for Ukraine, `pl` for Poland, `cs` for Czech Republic).
3. Determine if an established **benchmark** is relevant (e.g. comparing "Astronomy" against "Physics" to scale market size).
4. Select the time window (default 2 years for trend reliability).

### Step 2: Tool Invocation
Execute the CLI command. The CLI automatically handles:
- Following MediaWiki page redirects (`redirects=1`).
- Resolving counterpart article titles across languages via Wikidata Q-IDs.
- Querying filtered human pageviews (`agent=user`) vs web spiders (`agent=all-agents`).
- Executing Hampel filtering, STL decomposition, Theil-Sen regression, and Trust Scoring.
- Generating the dual-panel chart and 1-page PDF report.

### Step 3: Compact JSON Interpretation
The CLI returns a compact JSON payload (<1.5 KB). Read the key metrics:

1. **Theil-Sen CAGR (`cagr`)**:
   - $\ge +25\%$: High organic momentum.
   - $+8\%$ to $+25\%$: Moderate steady expansion.
   - $-8\%$ to $+8\%$: Stable plateau / mature interest.
   - $< -8\%$: Waning consumer interest.
2. **Trust & Reliability Score (`trust_score` / 100)**:
   - $\ge 75$: **High Trust**. Signal is clean, organic, and driven by real humans.
   - $55 - 74$: **Moderate Trust**. Real interest, but check for seasonal spikes or moderate bot scraping.
   - $40 - 54$: **Speculative / Low Trust**. Driven by viral news hype or high bot share. Smoke-test with an MVP first.
   - $< 40$: **Unreliable**. Do not invest.
3. **Academic Seasonality Index (`academic_seasonality_index`)**:
   - $ASI \ge 1.35$: Traffic is heavily dictated by school/university semesters (Sept-May peak, summer crash). Warn the founder that demand is cyclical.
   - $ASI \approx 1.0$: Year-round evergreen demand.
4. **Expansion Priority Score (`priority_score`)**:
   - Multi-market composite score ($0.40 V_i + 0.40 G_i + 0.20 T_i$) ranking which localization market to pursue first.

### Step 4: Structuring the Founder Response
Communicate findings clearly to the founder:
1. **Executive Verdict**: State clearly **GO**, **CAUTION**, or **NO-GO**.
2. **Market Sizing & Momentum**: Highlight TAM proxy ($) and annualized growth rate (CAGR).
3. **Reliability & Trust Audit**: Answer directly whether the trend can be trusted, explaining bot ratio, viral spike share, and seasonality.
4. **Actionable Recommendations**: Provide concrete next steps (e.g., timing course launch for September if $ASI$ is high; smoke-testing landing page if trust is moderate).
5. **Artifact Links**: Direct the user to the generated 1-Page PDF and high-res chart PNG.

---

## 4. Handling Edge Cases & Diagnostics

- **`INSUFFICIENT_DATA`**: Returned if an article has $<30$ days of history or $<10$ daily views average. Inform the founder that volume is currently too low for statistical confidence.
- **`PAGE_NOT_FOUND`**: If an exact article does not exist in a target language (e.g. Polish Wikipedia lacking a standalone "Intermittent fasting" article), the client automatically falls back to related terms (e.g. `Głodówka`). Note this nuance in your reply.
- **Repeated / Iterative Inquiries**: Thanks to the persistent SQLite cache (`.wiki_cache.sqlite`), follow-up questions from the user (such as changing the benchmark or tuning weights) execute in **<0.1 seconds** without network latency.
