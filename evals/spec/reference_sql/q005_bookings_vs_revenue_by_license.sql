-- Ground truth for q005. The perpetual/ratable timing gap, side by side.
-- Two independent aggregates unioned rather than joined: joining bookings to
-- revenue on license type would fan out across the many revenue rows a single
-- subscription booking produces.
SELECT LICENSE_TYPE AS LICENSE_TYPE, 'BOOKED' AS MEASURE, SUM(AMOUNT) AS VALUE
FROM V_BOOKINGS
WHERE FISCAL_QUARTER = '2026-Q3' AND IS_INTERCOMPANY = FALSE
GROUP BY LICENSE_TYPE
UNION ALL
SELECT LICENSE_TYPE AS LICENSE_TYPE, 'RECOGNISED' AS MEASURE, SUM(AMOUNT) AS VALUE
FROM V_REVENUE
WHERE FISCAL_QUARTER = '2026-Q3'
GROUP BY LICENSE_TYPE
ORDER BY LICENSE_TYPE, MEASURE
