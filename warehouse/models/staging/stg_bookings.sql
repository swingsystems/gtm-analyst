-- Source-switched. `--vars 'source_system: salesforce'` reads the
-- Salesforce-shaped seeds instead of the native ones and produces an IDENTICAL
-- contract, which is the point: the marts, the governance boundary and the
-- frozen evaluation all sit above this line and cannot tell the difference.
{% set source_system = var('source_system', 'native') %}

{% if source_system == 'salesforce' %}
-- A booking is a CLOSED WON opportunity. Open pipeline is not revenue, and
-- conflating the two is the most common reporting error in go-to-market.
SELECT
    o.External_Id__c::VARCHAR        AS BOOKING_ID,
    acc.External_Id__c::VARCHAR      AS ACCOUNT_ID,
    o.CloseDate::DATE                AS BOOKING_DATE,
    o.Amount::NUMBER(38,2)           AS AMOUNT,
    o.License_Type__c::VARCHAR       AS LICENSE_TYPE,
    o.Term_Months__c::NUMBER(38,0)   AS TERM_MONTHS,
    NULLIF(TRIM(acc.Segment__c), '')::VARCHAR AS SEGMENT,
    acc.Name::VARCHAR                AS ACCOUNT_NAME,
    o.Is_Intercompany__c::BOOLEAN    AS IS_INTERCOMPANY,
    o.CurrencyIsoCode::VARCHAR       AS CURRENCY
FROM {{ ref('sfdc_opportunity') }} AS o
JOIN {{ ref('sfdc_account') }} AS acc
  ON acc.Id = o.AccountId
WHERE o.IsWon = TRUE
  AND o.IsClosed = TRUE
{% else %}
SELECT
    BOOKING_ID::VARCHAR          AS BOOKING_ID,
    ACCOUNT_ID::VARCHAR          AS ACCOUNT_ID,
    BOOKING_DATE::DATE           AS BOOKING_DATE,
    AMOUNT::NUMBER(38,2)         AS AMOUNT,
    LICENSE_TYPE::VARCHAR        AS LICENSE_TYPE,
    TERM_MONTHS::NUMBER(38,0)    AS TERM_MONTHS,
    NULLIF(TRIM(SEGMENT), '')::VARCHAR AS SEGMENT,
    ACCOUNT_NAME::VARCHAR        AS ACCOUNT_NAME,
    IS_INTERCOMPANY::BOOLEAN     AS IS_INTERCOMPANY,
    CURRENCY::VARCHAR            AS CURRENCY
FROM {{ ref('raw_bookings') }}
{% endif %}
