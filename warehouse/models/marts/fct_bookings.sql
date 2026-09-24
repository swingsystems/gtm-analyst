-- Grain: one row per booking.
-- REGION and OWNER_REP_ID are denormalised from the account so the persona
-- views can filter without a join inside the security boundary.
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
  ON cal.CALENDAR_DATE = b.BOOKING_DATE
