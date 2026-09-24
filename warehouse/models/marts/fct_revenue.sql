-- Grain: one row per recognition event. FISCAL_QUARTER is the quarter revenue
-- was RECOGNISED in, which for a subscription is not the quarter the booking
-- was signed in -- that gap is what q002 and q006 measure.
-- LICENSE_TYPE is carried so q005 can compare booked against recognised by
-- license type without joining back to bookings and fanning out.
SELECT
    r.REVENUE_ID,
    r.BOOKING_ID,
    r.ACCOUNT_ID,
    r.RECOGNITION_DATE,
    cal.FISCAL_QUARTER,
    r.REGION,
    r.OWNER_REP_ID,
    r.SEGMENT,
    r.ACCOUNT_NAME,
    b.LICENSE_TYPE,
    r.AMOUNT
FROM {{ ref('stg_revenue') }} AS r
JOIN {{ ref('stg_bookings') }} AS b
  ON b.BOOKING_ID = r.BOOKING_ID
JOIN {{ ref('dim_fiscal_calendar') }} AS cal
  ON cal.CALENDAR_DATE = r.RECOGNITION_DATE
