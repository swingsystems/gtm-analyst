-- Ground truth for q001. Grain: one row per region.
-- V_BOOKINGS is UNQUALIFIED on purpose: the session default schema differs per
-- persona, so this one statement yields three different correct answers.
SELECT
    REGION                          AS REGION,
    SUM(AMOUNT)                     AS VALUE
FROM V_BOOKINGS
WHERE FISCAL_QUARTER = '2026-Q3'
  AND IS_INTERCOMPANY = FALSE
GROUP BY REGION
ORDER BY REGION
