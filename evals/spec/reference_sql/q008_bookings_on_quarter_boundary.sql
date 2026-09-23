-- Ground truth for q008. Bookings on the FINAL DAY of Q2, 30 June 2026.
-- An off-by-one on the quarter edge -- using < instead of <=, or taking the
-- quarter start as the boundary -- silently omits this row.
SELECT
    BOOKING_ID                      AS BOOKING_ID,
    AMOUNT                          AS VALUE
FROM V_BOOKINGS
WHERE BOOKING_DATE = DATE '2026-06-30'
ORDER BY BOOKING_ID
