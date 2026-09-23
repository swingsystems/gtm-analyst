-- Effective-dated. Any join to this table MUST constrain on the validity window
-- or it fans out across a rep's history, which is exactly what q011 catches.
SELECT
    TERRITORY_ID,
    REGION,
    REP_ID,
    VALID_FROM,
    VALID_TO
FROM {{ ref('stg_territory_assignments') }}
