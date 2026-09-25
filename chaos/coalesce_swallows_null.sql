-- DEFECT: the NULL segment is replaced with a literal at staging, so accounts
-- with no segment silently join the 'SMB' group. Totals still reconcile, which
-- is what makes it dangerous: nothing looks wrong.
SELECT
    ACCOUNT_ID::VARCHAR                     AS ACCOUNT_ID,
    ACCOUNT_NAME::VARCHAR                   AS ACCOUNT_NAME,
    REGION::VARCHAR                         AS REGION,
    COALESCE(NULLIF(TRIM(SEGMENT), ''), 'SMB')::VARCHAR AS SEGMENT,
    OWNER_REP_ID::VARCHAR                   AS OWNER_REP_ID
FROM {{ ref('raw_accounts') }}
