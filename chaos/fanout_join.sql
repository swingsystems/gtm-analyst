-- DEFECT: the calendar join loses its date equality and matches on year alone.
-- Every booking multiplies by the number of days in its year, so BOOKING_ID
-- stops being unique and every bookings total inflates by roughly 365x.
--
-- This is the crude version of the failure the whole strict-contract arm exists
-- to make impossible: a join written inside the warehouse without the predicate
-- that makes it a join rather than a near-cross-product.
SELECT
    b.BOOKING_ID,
    b.ACCOUNT_ID,
    b.BOOKING_DATE,
    cal.FISCAL_QUARTER,
    a.REGION,
    a.OWNER_REP_ID,
    a.SEGMENT,
    a.ACCOUNT_NAME,
    b.AMOUNT,
    b.LICENSE_TYPE,
    b.TERM_MONTHS,
    b.IS_INTERCOMPANY
FROM {{ ref('stg_bookings') }} AS b
JOIN {{ ref('dim_account') }} AS a
  ON a.ACCOUNT_ID = b.ACCOUNT_ID
JOIN {{ ref('dim_fiscal_calendar') }} AS cal
  ON cal.FISCAL_YEAR = YEAR(b.BOOKING_DATE)
