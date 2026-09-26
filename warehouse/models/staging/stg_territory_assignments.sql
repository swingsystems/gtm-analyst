-- Source-switched. `--vars 'source_system: salesforce'` reads the
-- Salesforce-shaped seeds instead of the native ones and produces an IDENTICAL
-- contract, which is the point: the marts, the governance boundary and the
-- frozen evaluation all sit above this line and cannot tell the difference.
{% set source_system = var('source_system', 'native') %}

{% if source_system == 'salesforce' %}
-- Salesforce models rep-to-territory as its own object with effective dates,
-- which is precisely the effective-dated join q011 exists to test.
SELECT
    t.External_Id__c::VARCHAR   AS TERRITORY_ID,
    t.Region__c::VARCHAR        AS REGION,
    u.External_Id__c::VARCHAR   AS REP_ID,
    a.EffectiveStartDate::DATE  AS VALID_FROM,
    a.EffectiveEndDate::DATE    AS VALID_TO
FROM {{ ref('sfdc_user_territory2_association') }} AS a
JOIN {{ ref('sfdc_territory2') }} AS t ON t.Id = a.Territory2Id
JOIN {{ ref('sfdc_user') }} AS u       ON u.Id = a.UserId
{% else %}
SELECT
    TERRITORY_ID::VARCHAR   AS TERRITORY_ID,
    REGION::VARCHAR         AS REGION,
    REP_ID::VARCHAR         AS REP_ID,
    VALID_FROM::DATE        AS VALID_FROM,
    VALID_TO::DATE          AS VALID_TO
FROM {{ ref('raw_territory_assignments') }}
{% endif %}
