-- Remove everything this reference architecture created. Nothing else.
--
-- Deliberately NOT run by `make governance`: it lives in the same directory as
-- the apply DDL, and apply_governance.py globs that directory. The glob sorts
-- alphabetically, so a file named teardown.sql would run last and drop what the
-- four numbered files had just built. It is excluded by name in that script and
-- a test asserts the exclusion, because discovering this by running it once
-- against a working deployment is an expensive way to learn it.
--
-- Drops are scoped to GAA_* objects. The warehouse is NOT dropped: it is named
-- by configuration and may predate this deployment or be shared.
USE ROLE ACCOUNTADMIN;

DROP USER IF EXISTS {{ service_user_prefix }}FINANCE_GLOBAL;
DROP USER IF EXISTS {{ service_user_prefix }}SALES_DIR_EMEA;
DROP USER IF EXISTS {{ service_user_prefix }}REP_INDIVIDUAL;

-- The database goes before the roles. Dropping a role first would orphan the
-- grants on objects the role owns, and those objects then need ACCOUNTADMIN to
-- clean up by hand.
DROP DATABASE IF EXISTS {{ database }};

USE ROLE SECURITYADMIN;
DROP ROLE IF EXISTS GAA_FINANCE_GLOBAL;
DROP ROLE IF EXISTS GAA_SALES_DIR_EMEA;
DROP ROLE IF EXISTS GAA_REP_INDIVIDUAL;
DROP ROLE IF EXISTS GAA_LOADER;
