-- One service user per persona, each holding EXACTLY ONE role.
--
-- Without this the boundary is not real. A session opened as GAA_REP_INDIVIDUAL
-- can run USE ROLE GAA_FINANCE_GLOBAL and read everything, because the USER
-- holds all four roles -- Snowflake scopes privilege to the session role, but
-- lets a session switch to any role its user has been granted. The schema grants
-- were never the weak point; the user's role portfolio was.
--
-- Each service user registers the SAME public key as the operator, so no extra
-- key management is required, and each has DEFAULT_ROLE set with no other role
-- granted. USE ROLE to anything else then fails because the user does not hold
-- it, which is the guarantee the bypass suite asserts.
USE ROLE ACCOUNTADMIN;

CREATE USER IF NOT EXISTS GAA_SVC_FINANCE_GLOBAL
    DEFAULT_ROLE = GAA_FINANCE_GLOBAL
    DEFAULT_WAREHOUSE = COMPUTE_WH
    TYPE = SERVICE
    COMMENT = 'Persona service user. Holds exactly one role by design.';
CREATE USER IF NOT EXISTS GAA_SVC_SALES_DIR_EMEA
    DEFAULT_ROLE = GAA_SALES_DIR_EMEA
    DEFAULT_WAREHOUSE = COMPUTE_WH
    TYPE = SERVICE
    COMMENT = 'Persona service user. Holds exactly one role by design.';
CREATE USER IF NOT EXISTS GAA_SVC_REP_INDIVIDUAL
    DEFAULT_ROLE = GAA_REP_INDIVIDUAL
    DEFAULT_WAREHOUSE = COMPUTE_WH
    TYPE = SERVICE
    COMMENT = 'Persona service user. Holds exactly one role by design.';

ALTER USER GAA_SVC_FINANCE_GLOBAL SET RSA_PUBLIC_KEY='<REDACTED_PUBLIC_KEY>';
ALTER USER GAA_SVC_SALES_DIR_EMEA SET RSA_PUBLIC_KEY='<REDACTED_PUBLIC_KEY>';
ALTER USER GAA_SVC_REP_INDIVIDUAL SET RSA_PUBLIC_KEY='<REDACTED_PUBLIC_KEY>';

GRANT ROLE GAA_FINANCE_GLOBAL TO USER GAA_SVC_FINANCE_GLOBAL;
GRANT ROLE GAA_SALES_DIR_EMEA TO USER GAA_SVC_SALES_DIR_EMEA;
GRANT ROLE GAA_REP_INDIVIDUAL TO USER GAA_SVC_REP_INDIVIDUAL;

-- The operator keeps only the loader role. Holding the persona roles is what
-- made escalation possible in the first place.
REVOKE ROLE GAA_FINANCE_GLOBAL FROM USER GAA_OPERATOR;
REVOKE ROLE GAA_SALES_DIR_EMEA FROM USER GAA_OPERATOR;
REVOKE ROLE GAA_REP_INDIVIDUAL FROM USER GAA_OPERATOR;
