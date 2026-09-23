-- The single owner of every period boundary. No other model may derive a fiscal
-- quarter by date arithmetic; they join here. Fiscal year is the CALENDAR year,
-- so 2026-Q3 runs 1 July to 30 September 2026.
WITH days AS (
    -- Range must outrun the longest recognition schedule. A 36-month
    -- subscription signed at the end of the booking window recognises into
    -- 2029, and an inner join to this table silently discards anything past
    -- its final row. Sized to 2031 with deliberate headroom; the
    -- assert_no_rows_lost_* tests fail the build if it is ever outrun again.
    SELECT DATEADD(day, SEQ4(), DATE '2025-01-01') AS CALENDAR_DATE
    FROM TABLE(GENERATOR(ROWCOUNT => 2557))       -- 2025-01-01 .. 2031-12-31
),
labelled AS (
    SELECT
        CALENDAR_DATE,
        YEAR(CALENDAR_DATE)    AS FISCAL_YEAR,
        QUARTER(CALENDAR_DATE) AS FISCAL_QUARTER_NUM
    FROM days
)
SELECT
    CALENDAR_DATE,
    FISCAL_YEAR,
    FISCAL_QUARTER_NUM,
    FISCAL_YEAR::VARCHAR || '-Q' || FISCAL_QUARTER_NUM::VARCHAR                 AS FISCAL_QUARTER,
    MIN(CALENDAR_DATE) OVER (PARTITION BY FISCAL_YEAR, FISCAL_QUARTER_NUM)      AS QUARTER_START_DATE,
    MAX(CALENDAR_DATE) OVER (PARTITION BY FISCAL_YEAR, FISCAL_QUARTER_NUM)      AS QUARTER_END_DATE
FROM labelled
