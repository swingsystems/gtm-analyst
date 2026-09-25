"""Per-call audit log.

One JSONL line per tool call, written whether the call succeeded or was
refused. A boundary that only records what it allowed cannot tell you what it
stopped, and the refusals are the interesting half.
"""
import json
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

# One rotated segment is kept alongside the live file, so the bound on disk is
# roughly twice this. 8 MiB holds a long run without a rotation, and a rotation
# is the moment the oldest entries leave -- the fewer of those, the better.
MAX_BYTES = 8 * 1024 * 1024

_OWNER_ONLY = 0o600
_OWNER_ONLY_DIR = 0o700


@dataclass
class AuditEntry:
    persona: str
    role: str
    schema: str
    tool: str
    outcome: str = "ok"
    metrics_used: list[str] = field(default_factory=list)
    query_id: str | None = None
    duration_ms: int = 0
    error: str | None = None


class AuditLog:
    """Append-only JSONL, owner-readable only, size-bounded.

    Never overwrites in place; a rewritten audit trail is not one. But it does
    rotate, because an unbounded log is a different kind of failure: it fills
    the disk and then records nothing at all.

    The contents are sensitive without containing any customer data. Persona,
    role, schema, tool, and outcome together describe the governance topology,
    and refusal text can quote what was asked for -- so the file is 0600 and its
    directory 0700.
    """

    def __init__(self, path: Path | None, max_bytes: int = MAX_BYTES):
        self.path = Path(path) if path else None
        self.max_bytes = max_bytes

    def _harden(self, path: Path) -> None:
        """Set the mode explicitly rather than relying on umask.

        os.open honours umask, so a permissive umask in the calling process
        would widen the file. Creating it correctly once is also not enough --
        a log written before this existed, or by a process with a different
        umask, is still loose on disk today.
        """
        try:
            path.chmod(_OWNER_ONLY)
        except OSError:
            # A log on a filesystem without POSIX modes is better than no log.
            pass

    def _rotate_if_needed(self) -> None:
        if not self.path.exists() or self.path.stat().st_size < self.max_bytes:
            return
        previous = self.path.with_suffix(self.path.suffix + ".1")
        # One generation. Replacing rather than chaining keeps the bound on disk
        # predictable; the alternative is an unbounded pile of .2, .3, .4.
        self.path.replace(previous)
        self._harden(previous)

    def record(self, entry: AuditEntry) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=_OWNER_ONLY_DIR)
        try:
            self.path.parent.chmod(_OWNER_ONLY_DIR)
        except OSError:
            pass
        self._rotate_if_needed()
        with self.path.open("a") as fh:
            fh.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
        self._harden(self.path)

    @contextmanager
    def around(self, entry: AuditEntry):
        """Time a call and record it on both paths out."""
        started = time.monotonic()
        try:
            yield entry
        except Exception as exc:
            entry.outcome = "refused"
            entry.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            entry.duration_ms = int((time.monotonic() - started) * 1000)
            self.record(entry)
