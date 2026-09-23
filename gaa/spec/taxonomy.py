from enum import Enum


class FailureCategory(str, Enum):
    """The nine ways an analytics answer can be wrong.

    Reported per-category rather than as a single accuracy number, because the
    categories have different causes and different fixes.

    ORPHANS_DROPPED deserves its own category rather than folding into a join
    error. Asked to reconcile bookings against revenue, an agent naturally writes
    an INNER JOIN, silently discards the unmatched rows, and reports that
    everything reconciles. The answer is wrong in the direction that hides the
    problem, which is the most dangerous shape an analytics error takes.
    """

    WRONG_JOIN_GRAIN = "wrong_join_grain"
    FANOUT_DOUBLE_COUNT = "fanout_double_count"
    WRONG_DATE_BOUNDARY = "wrong_date_boundary"
    WRONG_COLUMN = "wrong_column"
    NULL_SEGMENT_DROPPED = "null_segment_dropped"
    ORPHANS_DROPPED = "orphans_dropped"
    GOVERNANCE_LEAK = "governance_leak"
    GOVERNANCE_OVER_BLOCK = "governance_over_block"
    UNRESOLVABLE = "unresolvable"
