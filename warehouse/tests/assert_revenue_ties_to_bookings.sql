-- Every booking's recognised revenue must sum exactly to its booked amount.
-- Bookings with no revenue at all are seeded ground truth for q003 and are
-- excluded here; this asserts the schedules that DO exist are arithmetically
-- complete, so a rounding leak cannot masquerade as a real discrepancy.
SELECT
    b.BOOKING_ID,
    b.AMOUNT           AS BOOKED,
    SUM(r.AMOUNT)      AS RECOGNISED
FROM {{ ref('fct_bookings') }} AS b
JOIN {{ ref('fct_revenue') }} AS r
  ON r.BOOKING_ID = b.BOOKING_ID
GROUP BY b.BOOKING_ID, b.AMOUNT
HAVING SUM(r.AMOUNT) <> b.AMOUNT
