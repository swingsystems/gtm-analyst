"""Prompt symmetry is an experimental control, not a style preference.

If one arm's prompt is better written than another's, the experiment measures
prose quality and reports it as a finding about semantic grounding.
"""
from gaa.agent.prompts import (
    FREE_SQL_TOOLS,
    SAFE_JOIN_TOOLS,
    SHARED_PREAMBLE,
    STRICT_CONTRACT_TOOLS,
    system_prompt,
)

ARMS = ["strict-contract", "free-sql", "safe-join-contract"]


def test_every_arm_gets_the_identical_preamble():
    for arm in ARMS:
        assert SHARED_PREAMBLE in system_prompt(arm)


def test_the_arms_differ_only_in_their_tool_paragraph():
    bodies = {arm: system_prompt(arm).replace(SHARED_PREAMBLE, "") for arm in ARMS}
    assert bodies["strict-contract"].strip() == STRICT_CONTRACT_TOOLS.strip()
    assert bodies["free-sql"].strip() == FREE_SQL_TOOLS.strip()
    assert bodies["safe-join-contract"].strip() == SAFE_JOIN_TOOLS.strip()


def test_no_arm_gets_materially_more_instruction_than_another():
    """A big length gap is the cheapest proxy for one arm being coached harder."""
    lengths = [len(system_prompt(arm)) for arm in ARMS]
    assert max(lengths) - min(lengths) < 250, f"prompt lengths differ too much: {lengths}"


def test_the_shared_rules_cover_the_behaviours_being_scored():
    """Ambiguity, partial visibility and guessing are scored categories. An arm
    never told about them would fail for reasons the experiment does not mean
    to measure."""
    for cue in ["ambiguous", "withheld", "Never guess", "CONFIDENCE:", "WHY_NOT:"]:
        assert cue in SHARED_PREAMBLE


def test_no_arm_is_told_which_answer_is_expected():
    """Leaking the ground truth into a prompt would invalidate everything."""
    for arm in ARMS:
        prompt = system_prompt(arm).lower()
        for leak in ["2026-q3 bookings are", "the correct answer", "expected result"]:
            assert leak not in prompt
