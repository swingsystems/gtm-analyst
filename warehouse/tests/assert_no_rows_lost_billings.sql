-- Same completeness guarantee for billings.
SELECT s.BILLING_ID
FROM {{ ref('stg_billings') }} AS s
LEFT JOIN {{ ref('fct_billings') }} AS f
       ON f.BILLING_ID = s.BILLING_ID
WHERE f.BILLING_ID IS NULL
