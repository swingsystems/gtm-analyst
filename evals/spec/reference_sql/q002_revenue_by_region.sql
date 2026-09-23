-- Ground truth for q002. Revenue RECOGNISED in the quarter, which is not the
-- same population as bookings signed in the quarter. Perpetual recognises on the
-- booking date; subscription recognises ratably, so revenue here includes tails
-- from earlier bookings and excludes the unrecognised remainder of new ones.
SELECT
    REGION                          AS REGION,
    SUM(AMOUNT)                     AS VALUE
FROM V_REVENUE
WHERE FISCAL_QUARTER = '2026-Q3'
GROUP BY REGION
ORDER BY REGION
