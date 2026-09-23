-- Ground truth for q011. THE FAN-OUT QUESTION.
-- DIM_TERRITORY_SCD is effective-dated and a rep is reassigned mid-quarter, so
-- joining without constraining on the validity window multiplies each booking by
-- the number of territory rows and inflates the total.
SELECT
    b.ACCOUNT_ID                    AS ACCOUNT_ID,
    t.TERRITORY_ID                  AS TERRITORY_ID,
    SUM(b.AMOUNT)                   AS VALUE
FROM V_BOOKINGS AS b
JOIN V_TERRITORY AS t
  ON t.REP_ID = b.OWNER_REP_ID
 AND b.BOOKING_DATE >= t.VALID_FROM
 AND b.BOOKING_DATE <  t.VALID_TO
WHERE b.FISCAL_QUARTER = '2026-Q3'
GROUP BY b.ACCOUNT_ID, t.TERRITORY_ID
ORDER BY ACCOUNT_ID, TERRITORY_ID
