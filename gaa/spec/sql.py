"""Splitting SQL into statements.

A naive ``sql.split(";")`` counts semicolons inside comments as statement
separators, so a comment containing ordinary prose punctuation silently turns one
query into two. Everything that needs to count or execute statements uses this.
"""


def strip_line_comments(sql: str) -> str:
    """Drop ``--`` line comments, preserving the rest verbatim."""
    out = []
    for line in sql.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("--"):
            continue
        if "--" in line:
            line = line[: line.index("--")].rstrip()
        out.append(line)
    return "\n".join(out)


def sql_statements(sql: str) -> list[str]:
    """Return the non-empty statements in ``sql``, comments removed."""
    return [s.strip() for s in strip_line_comments(sql).split(";") if s.strip()]
