-- Identical view NAMES in three schemas, different definitions. This IS the
-- boundary: an unqualified query resolves against the session's default schema,
-- so one SQL string returns three different correct answers.
-- CREATE OR REPLACE because dbt drops dependents whenever it rebuilds a mart.
USE ROLE SYSADMIN;

-- ---------------------------------------------------------------- FINANCE
-- Everything, account names in the clear.
CREATE OR REPLACE SECURE VIEW GAA.FINANCE.V_BOOKINGS  AS SELECT * FROM GAA.MARTS.FCT_BOOKINGS;
CREATE OR REPLACE SECURE VIEW GAA.FINANCE.V_BILLINGS  AS SELECT * FROM GAA.MARTS.FCT_BILLINGS;
CREATE OR REPLACE SECURE VIEW GAA.FINANCE.V_REVENUE   AS SELECT * FROM GAA.MARTS.FCT_REVENUE;
CREATE OR REPLACE SECURE VIEW GAA.FINANCE.V_ACCOUNT   AS SELECT * FROM GAA.MARTS.DIM_ACCOUNT;
CREATE OR REPLACE SECURE VIEW GAA.FINANCE.V_TERRITORY AS SELECT * FROM GAA.MARTS.DIM_TERRITORY_SCD;

-- ---------------------------------------------------------------- EMEA
-- Region-filtered, account names masked. Masking changes distinct values but
-- never row counts, which is what the masking_preserves_row_count invariant
-- asserts.
CREATE OR REPLACE SECURE VIEW GAA.EMEA.V_BOOKINGS AS
    SELECT * EXCLUDE (ACCOUNT_NAME),
           'ACCOUNT-' || RIGHT(SHA2(ACCOUNT_NAME), 8) AS ACCOUNT_NAME
    FROM GAA.MARTS.FCT_BOOKINGS WHERE REGION = 'EMEA';
CREATE OR REPLACE SECURE VIEW GAA.EMEA.V_BILLINGS AS
    SELECT * FROM GAA.MARTS.FCT_BILLINGS WHERE REGION = 'EMEA';
CREATE OR REPLACE SECURE VIEW GAA.EMEA.V_REVENUE AS
    SELECT * EXCLUDE (ACCOUNT_NAME),
           'ACCOUNT-' || RIGHT(SHA2(ACCOUNT_NAME), 8) AS ACCOUNT_NAME
    FROM GAA.MARTS.FCT_REVENUE WHERE REGION = 'EMEA';
CREATE OR REPLACE SECURE VIEW GAA.EMEA.V_ACCOUNT AS
    SELECT ACCOUNT_ID,
           'ACCOUNT-' || RIGHT(SHA2(ACCOUNT_NAME), 8) AS ACCOUNT_NAME,
           REGION, SEGMENT, OWNER_REP_ID
    FROM GAA.MARTS.DIM_ACCOUNT WHERE REGION = 'EMEA';
CREATE OR REPLACE SECURE VIEW GAA.EMEA.V_TERRITORY AS
    SELECT * FROM GAA.MARTS.DIM_TERRITORY_SCD WHERE REGION = 'EMEA';

-- ---------------------------------------------------------------- REP
-- Own accounts only, names masked.
-- The rep is resolved from CURRENT_USER() through GAA.IDENTITY.MAP_USER_TO_REP.
-- This previously hardcoded REP001, which meant every rep in a real deployment
-- would have seen one rep's book.
--
-- It FAILS CLOSED by construction. An unmapped session makes the scalar
-- subquery return NULL, `OWNER_REP_ID = NULL` is UNKNOWN, and UNKNOWN does not
-- pass a WHERE clause -- so an unrecognised user sees zero rows rather than
-- everything. That is the opposite of how a mapping miss usually fails, and it
-- is the reason the filter is written as a subquery rather than resolved into
-- the view at deploy time.
--
-- The map lives in GAA.IDENTITY, which no persona role has any grant on. The
-- view can read it because a secure view executes with its owner's rights; the
-- caller cannot read it directly, so the rep cannot enumerate other reps.
CREATE OR REPLACE SECURE VIEW GAA.REP.V_BOOKINGS AS
    SELECT * EXCLUDE (ACCOUNT_NAME),
           'ACCOUNT-' || RIGHT(SHA2(ACCOUNT_NAME), 8) AS ACCOUNT_NAME
    FROM GAA.MARTS.FCT_BOOKINGS WHERE OWNER_REP_ID = (SELECT REP_ID FROM GAA.IDENTITY.MAP_USER_TO_REP
                            WHERE SNOWFLAKE_USER = CURRENT_USER());
CREATE OR REPLACE SECURE VIEW GAA.REP.V_BILLINGS AS
    SELECT * FROM GAA.MARTS.FCT_BILLINGS WHERE OWNER_REP_ID = (SELECT REP_ID FROM GAA.IDENTITY.MAP_USER_TO_REP
                            WHERE SNOWFLAKE_USER = CURRENT_USER());
CREATE OR REPLACE SECURE VIEW GAA.REP.V_REVENUE AS
    SELECT * EXCLUDE (ACCOUNT_NAME),
           'ACCOUNT-' || RIGHT(SHA2(ACCOUNT_NAME), 8) AS ACCOUNT_NAME
    FROM GAA.MARTS.FCT_REVENUE WHERE OWNER_REP_ID = (SELECT REP_ID FROM GAA.IDENTITY.MAP_USER_TO_REP
                            WHERE SNOWFLAKE_USER = CURRENT_USER());
CREATE OR REPLACE SECURE VIEW GAA.REP.V_ACCOUNT AS
    SELECT ACCOUNT_ID,
           'ACCOUNT-' || RIGHT(SHA2(ACCOUNT_NAME), 8) AS ACCOUNT_NAME,
           REGION, SEGMENT, OWNER_REP_ID
    FROM GAA.MARTS.DIM_ACCOUNT WHERE OWNER_REP_ID = (SELECT REP_ID FROM GAA.IDENTITY.MAP_USER_TO_REP
                            WHERE SNOWFLAKE_USER = CURRENT_USER());
CREATE OR REPLACE SECURE VIEW GAA.REP.V_TERRITORY AS
    SELECT * FROM GAA.MARTS.DIM_TERRITORY_SCD WHERE REP_ID = (SELECT REP_ID FROM GAA.IDENTITY.MAP_USER_TO_REP
                      WHERE SNOWFLAKE_USER = CURRENT_USER());

-- Seed the identity map for the reference deployment: the rep service user IS
-- REP001. MERGE rather than INSERT so a second deploy converges instead of
-- accumulating duplicate rows, which would make the scalar subquery in the REP
-- views raise instead of filtering.
--
-- A real deployment populates this from the HR or CRM system of record. It is
-- the one place where "who is this session" is decided, which is why it is a
-- table someone can audit rather than a string inside a view definition.
MERGE INTO GAA.IDENTITY.MAP_USER_TO_REP AS m
USING (SELECT '{{ service_user_prefix }}REP_INDIVIDUAL' AS SNOWFLAKE_USER,
              'REP001' AS REP_ID) AS s
   ON m.SNOWFLAKE_USER = s.SNOWFLAKE_USER
 WHEN MATCHED THEN UPDATE SET REP_ID = s.REP_ID
 WHEN NOT MATCHED THEN INSERT (SNOWFLAKE_USER, REP_ID) VALUES (s.SNOWFLAKE_USER, s.REP_ID);

GRANT SELECT ON ALL VIEWS IN SCHEMA GAA.FINANCE TO ROLE GAA_FINANCE_GLOBAL;
GRANT SELECT ON ALL VIEWS IN SCHEMA GAA.EMEA    TO ROLE GAA_SALES_DIR_EMEA;
GRANT SELECT ON ALL VIEWS IN SCHEMA GAA.REP     TO ROLE GAA_REP_INDIVIDUAL;
