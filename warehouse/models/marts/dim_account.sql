SELECT
    ACCOUNT_ID,
    ACCOUNT_NAME,
    REGION,
    SEGMENT,
    OWNER_REP_ID
FROM {{ ref('stg_accounts') }}
