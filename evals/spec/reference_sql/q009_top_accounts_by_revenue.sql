-- Ground truth for q009. Account names come from the persona's own view, so
-- finance sees them in the clear and the restricted personas see hashes. Row
-- counts must match across personas for the same filtered population; only the
-- values differ.
SELECT
    a.ACCOUNT_NAME                  AS ACCOUNT_NAME,
    SUM(r.AMOUNT)                   AS VALUE
FROM V_REVENUE AS r
JOIN V_ACCOUNT AS a
  ON a.ACCOUNT_ID = r.ACCOUNT_ID
WHERE r.FISCAL_QUARTER = '2026-Q3'
GROUP BY a.ACCOUNT_NAME
ORDER BY VALUE DESC, ACCOUNT_NAME
LIMIT 10
