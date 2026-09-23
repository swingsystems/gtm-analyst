SELECT
    TERRITORY_ID::VARCHAR   AS TERRITORY_ID,
    REGION::VARCHAR         AS REGION,
    REP_ID::VARCHAR         AS REP_ID,
    VALID_FROM::DATE        AS VALID_FROM,
    VALID_TO::DATE          AS VALID_TO
FROM {{ ref('raw_territory_assignments') }}
