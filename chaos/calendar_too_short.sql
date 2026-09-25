-- DEFECT: the calendar stops before the longest recognition schedule ends.
-- A 36-month subscription signed late in the booking window recognises into
-- 2029; an inner join to this table silently discards everything past its last
-- row, and dbt reports success. Committed for real in e517ed4.
WITH days AS (
    SELECT DATEADD(day, SEQ4(), DATE '2025-01-01') AS CALENDAR_DATE
    FROM TABLE(GENERATOR(ROWCOUNT => 1096))
),
labelled AS (
    SELECT CALENDAR_DATE, YEAR(CALENDAR_DATE) AS FISCAL_YEAR,
           QUARTER(CALENDAR_DATE) AS FISCAL_QUARTER_NUM
    FROM days
)
SELECT
    CALENDAR_DATE, FISCAL_YEAR, FISCAL_QUARTER_NUM,
    FISCAL_YEAR::VARCHAR || '-Q' || FISCAL_QUARTER_NUM::VARCHAR AS FISCAL_QUARTER,
    MIN(CALENDAR_DATE) OVER (PARTITION BY FISCAL_YEAR, FISCAL_QUARTER_NUM) AS QUARTER_START_DATE,
    MAX(CALENDAR_DATE) OVER (PARTITION BY FISCAL_YEAR, FISCAL_QUARTER_NUM) AS QUARTER_END_DATE
FROM labelled
