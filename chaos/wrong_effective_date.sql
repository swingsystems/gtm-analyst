-- DEFECT: the validity window becomes inclusive at its upper bound.
--
-- Consumers read it half-open -- [VALID_FROM, VALID_TO) -- which is what q011's
-- reference SQL does. Pushing VALID_TO out by one day makes the handover date
-- fall inside BOTH the outgoing and incoming assignment, so every booking on a
-- reassignment date is counted twice and attributed to two territories.
--
-- Not hypothetical. This project shipped the mirror image of it: the generator
-- wrote inclusive end dates while the reference SQL read them half-open, and
-- 180,848.13 went missing at handovers until a free-SQL agent refused to answer
-- and kept probing instead.
SELECT
    TERRITORY_ID,
    REGION,
    REP_ID,
    VALID_FROM,
    DATEADD(day, 1, VALID_TO) AS VALID_TO
FROM {{ ref('stg_territory_assignments') }}
