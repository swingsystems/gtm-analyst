-- Ground truth for q010. Accounts with no segment must appear as their own
-- group, not vanish. An inner join to a segment dimension, or a WHERE SEGMENT
-- IS NOT NULL, silently drops them and the total no longer ties to q002.
SELECT
    COALESCE(a.SEGMENT, '(none)')   AS SEGMENT,
    SUM(r.AMOUNT)                   AS VALUE
FROM V_REVENUE AS r
LEFT JOIN V_ACCOUNT AS a
       ON a.ACCOUNT_ID = r.ACCOUNT_ID
WHERE r.FISCAL_QUARTER = '2026-Q3'
GROUP BY COALESCE(a.SEGMENT, '(none)')
ORDER BY SEGMENT
