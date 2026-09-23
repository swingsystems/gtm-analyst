-- Grain: one row per billing. Carries REGION and OWNER_REP_ID for persona
-- filtering, and FISCAL_QUARTER of the INVOICE date, which is not necessarily
-- the quarter the booking was signed in.
SELECT
    bi.BILLING_ID,
    bi.BOOKING_ID,
    b.ACCOUNT_ID,
    bi.INVOICE_DATE,
    cal.FISCAL_QUARTER,
    b.REGION,
    b.OWNER_REP_ID,
    bi.AMOUNT
FROM {{ ref('stg_billings') }} AS bi
JOIN {{ ref('fct_bookings') }} AS b
  ON b.BOOKING_ID = bi.BOOKING_ID
JOIN {{ ref('dim_fiscal_calendar') }} AS cal
  ON cal.CALENDAR_DATE = bi.INVOICE_DATE
