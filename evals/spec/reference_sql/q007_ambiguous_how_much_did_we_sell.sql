-- Ground truth for q007 is DELIBERATELY EMPTY.
-- "How much did we sell in Q3?" does not name a metric. Bookings, billings and
-- revenue all answer it and give three different numbers. The correct agent
-- behaviour is to refuse and ask which is meant; any confident single number is
-- scored as a failure in the UNRESOLVABLE category.
-- This query exists so the file reference resolves. It returns no rows by
-- construction, which is the expected result for every persona.
SELECT
    NULL                            AS VALUE
WHERE FALSE
