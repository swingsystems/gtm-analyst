-- Each persona role is granted USAGE on exactly ONE schema. MARTS is loader-only.
-- These grants ARE the boundary, so a mis-grant is a breach rather than a bug,
-- and the bypass suite tests them adversarially.
--
-- The loader's grants are enumerated rather than GRANT ALL. GRANT ALL ON SCHEMA
-- confers roughly seventy privileges including CREATE AGENT, CREATE SECRET and
-- CREATE MCP SERVER -- none of which a role that builds tables has any business
-- holding. Found while bootstrapping this warehouse; recorded in the threat
-- model as a least-privilege finding.
USE ROLE SYSADMIN;

GRANT USAGE ON DATABASE GAA TO ROLE GAA_LOADER;
GRANT USAGE ON DATABASE GAA TO ROLE GAA_FINANCE_GLOBAL;
GRANT USAGE ON DATABASE GAA TO ROLE GAA_SALES_DIR_EMEA;
GRANT USAGE ON DATABASE GAA TO ROLE GAA_REP_INDIVIDUAL;

-- Loader: exactly what dbt needs to build and nothing else.
--
-- REVOKE first. Grants are ADDITIVE: adding narrow grants does not remove broad
-- ones already held, so re-running this against an account that once had
-- GRANT ALL would leave the loader holding CREATE AGENT and CREATE SECRET
-- forever while the file appeared to say otherwise. Revoke-then-grant makes the
-- privilege set converge on what is written here regardless of history, which is
-- the only way `make deploy` means the same thing on the first run and the tenth.
REVOKE ALL PRIVILEGES ON SCHEMA GAA.MARTS FROM ROLE GAA_LOADER;
GRANT USAGE, MODIFY, CREATE TABLE, CREATE VIEW ON SCHEMA GAA.MARTS TO ROLE GAA_LOADER;
GRANT USAGE ON SCHEMA GAA.FINANCE TO ROLE GAA_LOADER;
GRANT USAGE ON SCHEMA GAA.EMEA    TO ROLE GAA_LOADER;
GRANT USAGE ON SCHEMA GAA.REP     TO ROLE GAA_LOADER;

-- Personas: one schema each. No grant on MARTS, ever.
GRANT USAGE ON SCHEMA GAA.FINANCE TO ROLE GAA_FINANCE_GLOBAL;
GRANT USAGE ON SCHEMA GAA.EMEA    TO ROLE GAA_SALES_DIR_EMEA;
GRANT USAGE ON SCHEMA GAA.REP     TO ROLE GAA_REP_INDIVIDUAL;

-- Warehouse grants need the warehouse's OWNER. On a default account {{ warehouse }}
-- belongs to ACCOUNTADMIN, not SYSADMIN, so granting on it from SYSADMIN fails
-- with "Insufficient privileges" -- which reads like a bug and is not one. An
-- adopter whose warehouse is owned elsewhere must adjust this role accordingly.
USE ROLE ACCOUNTADMIN;

GRANT USAGE, OPERATE ON WAREHOUSE {{ warehouse }} TO ROLE GAA_LOADER;
GRANT USAGE ON WAREHOUSE {{ warehouse }} TO ROLE GAA_FINANCE_GLOBAL;
GRANT USAGE ON WAREHOUSE {{ warehouse }} TO ROLE GAA_SALES_DIR_EMEA;
GRANT USAGE ON WAREHOUSE {{ warehouse }} TO ROLE GAA_REP_INDIVIDUAL;
