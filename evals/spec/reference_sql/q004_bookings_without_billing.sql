-- Ground truth for q004. The orphan question on the billing surface.
SELECT
    b.BOOKING_ID                    AS BOOKING_ID,
    b.AMOUNT                        AS VALUE
FROM V_BOOKINGS AS b
LEFT JOIN V_BILLINGS AS bi
       ON bi.BOOKING_ID = b.BOOKING_ID
WHERE b.FISCAL_QUARTER = '2026-Q3'
  AND bi.BOOKING_ID IS NULL
ORDER BY b.BOOKING_ID
