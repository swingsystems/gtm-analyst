# Governed analytics agents — recorded demo

Replaying 25 answer cards recorded against a live Snowflake account. No credentials were used to produce this page, and none are needed to reproduce it.

## One question, three identities, three correct answers

> What were total bookings for Q3 2026 by region, excluding intercompany?

| asked as | rows | total | withheld |
|---|---|---|---|
| `FINANCE_GLOBAL` | 3 | 10,826,071.18 | — |
| `REP_INDIVIDUAL` | 1 | 0.00 | yes |
| `SALES_DIR_EMEA` | 1 | 4,137,843.49 | yes |

Same question. Same SQL shape. Different answers, because the warehouse — not the prompt — decides what each identity may see.

## An answer, with everything needed to check it

**Q.** What were total bookings for Q3 2026 by region, excluding intercompany?
**Asked as** `FINANCE_GLOBAL` (role `GAA_FINANCE_GLOBAL`, schema `FINANCE`) · arm `free-sql`

| REGION | TOTAL_BOOKINGS |
|---|---|
| AMER | 2005507.42 |
| APAC | 4682720.27 |
| EMEA | 4137843.49 |

**Confidence.** high — — bookings_amount's default definition already excludes intercompany deals, matching the question exactly; query ran directly against V_BOOKINGS with explicit filters for FISCAL_QUARTER='2026-Q3' and IS_INTERCOMPANY=false, and results returned cleanly for all three regions visible to this persona.
**Metrics.** none (free SQL)
**Lineage.** V_BOOKINGS
**Query id.** `01c74cd7-010b-a885-000a-95d700bcf136`

```sql
SELECT REGION, SUM(AMOUNT) AS total_bookings
FROM V_BOOKINGS
WHERE FISCAL_QUARTER = '2026-Q3'
  AND IS_INTERCOMPANY = false
GROUP BY REGION
ORDER BY REGION
```

## Withholding, stated rather than hidden

> Only EMEA region is visible to this persona; bookings for other regions could not be retrieved or included in the total.

A smaller number presented as complete is the dangerous failure. This is the alternative.

## What this does not show

Synthetic data. A partial experiment: 25 of 36 cells, stopped by an API spending limit. One run per cell, and the same question asked repeatedly has produced row counts of 3, 68, 13 and 68. See `results/` for the numbers and their limits, and `README.md` for why the evaluation might still be lying to you.
