-- DEFECT: every date is labelled with the quarter of the FOLLOWING day.
--
-- CALENDAR_DATE is untouched, so nothing looks wrong on inspection and no dbt
-- test fires. Only the labelling shifts: 30 June 2026 becomes 2026-Q3 and 30
-- September 2026 falls out of it, so a "Q3 bookings" total quietly gains one
-- day's bookings at the front and loses one at the back.
--
-- This is the dangerous shape. The numbers stay plausible, the row counts stay
-- sane, and the error is a boundary nobody re-derives by hand.
WITH days AS (
    SELECT DATEADD(day, SEQ4(), DATE '2025-01-01') AS CALENDAR_DATE
    FROM TABLE(GENERATOR(ROWCOUNT => 2557))       -- 2025-01-01 .. 2031-12-31
),
labelled AS (
    SELECT
        CALENDAR_DATE,
        YEAR(DATEADD(day, 1, CALENDAR_DATE))    AS FISCAL_YEAR,
        QUARTER(DATEADD(day, 1, CALENDAR_DATE)) AS FISCAL_QUARTER_NUM
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
