-- Ground truth for q006. Revenue recognised IN Q3 from bookings signed BEFORE
-- Q3 -- the ratable tail. Requires distinguishing recognition date from booking
-- date; conflating them returns zero.
SELECT
    SUM(r.AMOUNT)                   AS VALUE
FROM V_REVENUE AS r
JOIN V_BOOKINGS AS b
  ON b.BOOKING_ID = r.BOOKING_ID
WHERE r.FISCAL_QUARTER = '2026-Q3'
  AND b.BOOKING_DATE < DATE '2026-07-01'
