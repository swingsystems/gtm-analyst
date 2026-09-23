-- Same completeness guarantee for bookings: every staged booking must survive
-- the joins into the fact table.
SELECT s.BOOKING_ID
FROM {{ ref('stg_bookings') }} AS s
LEFT JOIN {{ ref('fct_bookings') }} AS f
       ON f.BOOKING_ID = s.BOOKING_ID
WHERE f.BOOKING_ID IS NULL
