-- Empty-string segment becomes a real NULL here, once, so no downstream model
-- has to guess. q010 asserts the NULL segment survives aggregation.
SELECT
    ACCOUNT_ID::VARCHAR                    AS ACCOUNT_ID,
    ACCOUNT_NAME::VARCHAR                  AS ACCOUNT_NAME,
    REGION::VARCHAR                        AS REGION,
    NULLIF(TRIM(SEGMENT), '')::VARCHAR     AS SEGMENT,
    OWNER_REP_ID::VARCHAR                  AS OWNER_REP_ID
FROM {{ ref('raw_accounts') }}
