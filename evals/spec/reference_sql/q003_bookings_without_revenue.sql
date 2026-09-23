-- Ground truth for q003. THE ORPHAN QUESTION.
-- A LEFT JOIN with a NULL test is required. An INNER JOIN returns the matched
-- rows and reports nothing missing, which is wrong in the direction that hides
-- the problem.
SELECT
    b.BOOKING_ID                    AS BOOKING_ID,
    b.AMOUNT                        AS VALUE
FROM V_BOOKINGS AS b
LEFT JOIN V_REVENUE AS r
       ON r.BOOKING_ID = b.BOOKING_ID
WHERE b.FISCAL_QUARTER = '2026-Q3'
  AND r.BOOKING_ID IS NULL
ORDER BY b.BOOKING_ID
