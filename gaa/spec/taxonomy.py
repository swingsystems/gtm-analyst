from enum import Enum


class FailureCategory(str, Enum):
    """The eight ways an analytics answer can be wrong.

    Reported per-category rather than as a single accuracy number, because the
    categories have different causes and different fixes.
    """

    WRONG_JOIN_GRAIN = "wrong_join_grain"
    FANOUT_DOUBLE_COUNT = "fanout_double_count"
    WRONG_DATE_BOUNDARY = "wrong_date_boundary"
    WRONG_COLUMN = "wrong_column"
    NULL_SEGMENT_DROPPED = "null_segment_dropped"
    GOVERNANCE_LEAK = "governance_leak"
    GOVERNANCE_OVER_BLOCK = "governance_over_block"
    UNRESOLVABLE = "unresolvable"
