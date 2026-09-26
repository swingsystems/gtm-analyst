-- Source-switched. `--vars 'source_system: salesforce'` reads the
-- Salesforce-shaped seeds instead of the native ones and produces an IDENTICAL
-- contract, which is the point: the marts, the governance boundary and the
-- frozen evaluation all sit above this line and cannot tell the difference.
--
-- Empty-string segment becomes a real NULL here, once, so no downstream model
-- has to guess. q010 asserts the NULL segment survives aggregation.
{% set source_system = var('source_system', 'native') %}

{% if source_system == 'salesforce' %}
-- Region is DERIVED from BillingCountry. A CRM stores where the account is,
-- not which reporting region it rolls into, and putting that mapping here makes
-- it reviewable instead of buried in a report.
SELECT
    a.External_Id__c::VARCHAR              AS ACCOUNT_ID,
    a.Name::VARCHAR                        AS ACCOUNT_NAME,
    CASE
        WHEN a.BillingCountry IN ('US', 'CA', 'BR', 'MX')             THEN 'AMER'
        WHEN a.BillingCountry IN ('GB', 'DE', 'FR', 'NL', 'ES')       THEN 'EMEA'
        WHEN a.BillingCountry IN ('JP', 'AU', 'SG', 'IN')             THEN 'APAC'
    END::VARCHAR                           AS REGION,
    NULLIF(TRIM(a.Segment__c), '')::VARCHAR AS SEGMENT,
    u.External_Id__c::VARCHAR              AS OWNER_REP_ID
FROM {{ ref('sfdc_account') }} AS a
JOIN {{ ref('sfdc_user') }} AS u
  ON u.Id = a.OwnerId
{% else %}
SELECT
    ACCOUNT_ID::VARCHAR                    AS ACCOUNT_ID,
    ACCOUNT_NAME::VARCHAR                  AS ACCOUNT_NAME,
    REGION::VARCHAR                        AS REGION,
    NULLIF(TRIM(SEGMENT), '')::VARCHAR     AS SEGMENT,
    OWNER_REP_ID::VARCHAR                  AS OWNER_REP_ID
FROM {{ ref('raw_accounts') }}
{% endif %}
