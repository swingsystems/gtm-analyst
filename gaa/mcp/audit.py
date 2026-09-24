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
    """Append-only JSONL. Never overwrites; a rewritten audit trail is not one."""

    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None

    def record(self, entry: AuditEntry) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(asdict(entry), sort_keys=True) + "\n")

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
