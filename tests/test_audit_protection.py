"""The audit log records who asked what and what was refused.

Anyone who can read it learns the persona topology, the schema shape, and which
questions were declined -- and refusal text can quote what was asked for. It was
world-readable, unrotated, and unbounded.
"""
import json
import os
import stat

import pytest

from gaa.mcp.audit import MAX_BYTES, AuditEntry, AuditLog


def _entry(tool: str = "query_metric") -> AuditEntry:
    return AuditEntry(persona="REP_INDIVIDUAL", role="GAA_REP_INDIVIDUAL",
                      schema="REP", tool=tool)


def test_the_log_file_is_readable_only_by_its_owner(tmp_path) -> None:
    log = AuditLog(tmp_path / "nested" / "audit.jsonl")
    log.record(_entry())
    mode = stat.S_IMODE(os.stat(log.path).st_mode)
    assert mode == 0o600, f"audit log is {oct(mode)}, expected 0o600"


def test_the_containing_directory_is_not_world_traversable(tmp_path) -> None:
    """0600 on the file is undone by a directory anyone can list and rename in."""
    log = AuditLog(tmp_path / "nested" / "audit.jsonl")
    log.record(_entry())
    mode = stat.S_IMODE(os.stat(log.path.parent).st_mode)
    assert mode & 0o077 == 0, f"audit directory is {oct(mode)}"


def test_permissions_are_repaired_on_a_preexisting_loose_file(tmp_path) -> None:
    """The realistic case. A log already exists from before this change, or was
    created by a process with a different umask. Creating it correctly once is
    not the same as it being correct."""
    path = tmp_path / "audit.jsonl"
    path.write_text("")
    path.chmod(0o644)
    AuditLog(path).record(_entry())
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_the_log_rotates_instead_of_growing_without_bound(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, max_bytes=2048)
    for i in range(400):
        log.record(_entry(tool=f"t{i}"))
    assert path.stat().st_size <= 2048 * 2
    assert path.with_suffix(".jsonl.1").exists(), "no rotated segment was kept"


def test_rotation_preserves_the_older_entries_rather_than_dropping_them(tmp_path) -> None:
    """A trail that silently deletes its own beginning is not a trail."""
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, max_bytes=1024)
    for i in range(200):
        log.record(_entry(tool=f"tool{i:03d}"))
    seen = set()
    for p in (path.with_suffix(".jsonl.1"), path):
        if p.exists():
            seen |= {json.loads(line)["tool"] for line in p.read_text().splitlines() if line}
    assert "tool199" in seen, "the newest entry is missing"
    assert len(seen) > 1, "rotation kept only a single entry"


def test_rotated_segments_are_also_owner_only(tmp_path) -> None:
    """Rotation that relaxes permissions on the way out defeats the point."""
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, max_bytes=512)
    for i in range(200):
        log.record(_entry(tool=f"t{i}"))
    rotated = path.with_suffix(".jsonl.1")
    assert stat.S_IMODE(os.stat(rotated).st_mode) == 0o600


def test_a_default_size_bound_exists(tmp_path) -> None:
    """An unbounded default makes every other test here theatre."""
    assert MAX_BYTES > 0
    assert AuditLog(tmp_path / "a.jsonl").max_bytes == MAX_BYTES


def test_disabled_logging_still_works(tmp_path) -> None:
    AuditLog(None).record(_entry())


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_the_umask_cannot_loosen_the_file(tmp_path) -> None:
    """os.open honours umask, so a permissive umask would widen the mode unless
    it is set explicitly after creation."""
    old = os.umask(0o000)
    try:
        log = AuditLog(tmp_path / "audit.jsonl")
        log.record(_entry())
        assert stat.S_IMODE(os.stat(log.path).st_mode) == 0o600
    finally:
        os.umask(old)
