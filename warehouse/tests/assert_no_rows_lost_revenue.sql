-- fct_revenue joins to dim_fiscal_calendar. An inner join to a dimension that
-- does not span the data silently drops rows and dbt still reports success.
-- That happened during the build: a calendar ending in 2027 discarded 1,159
-- revenue rows from 36-month subscriptions recognising into 2029.
-- Returns rows -- and so fails -- if any staged revenue row is missing.
SELECT s.REVENUE_ID
FROM {{ ref('stg_revenue') }} AS s
LEFT JOIN {{ ref('fct_revenue') }} AS f
       ON f.REVENUE_ID = s.REVENUE_ID
WHERE f.REVENUE_ID IS NULL
