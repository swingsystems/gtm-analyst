"""Render recorded answer cards into one self-contained page.

Deliberately a static file rather than a server. The plan sketched FastAPI, but
every step it listed says "render from the recorded cards, no live calls" -- so
a server would add two dependencies and a process to display data that never
changes. A file opens with no account, no key, and no network, which is the same
constraint the demo tier holds itself to.

The argument is visual and it is one argument: the same question, asked by three
identities, returns three different correct answers, and the two restricted ones
say what they withheld.
"""
import json
from html import escape
from pathlib import Path

from gtm_analyst.agent.card import AnswerCard, strip_sidecars

# Ordered widest-to-narrowest so the page reads as progressive restriction
# rather than three unrelated columns.
PERSONA_ORDER = ("FINANCE_GLOBAL", "SALES_DIR_EMEA", "REP_INDIVIDUAL")

_SCOPE = {
    "FINANCE_GLOBAL": "sees everything",
    "SALES_DIR_EMEA": "sees EMEA only",
    "REP_INDIVIDUAL": "sees own book only",
}


def load_cards(path: Path) -> list[AnswerCard]:
    """Read recorded cards, dropping the harness's sidecar keys.

    The harness writes `_question_id` alongside each card so results can be
    joined back to the spec. AnswerCard sets extra="forbid" on purpose -- an
    unrecognised field is a schema drift worth failing on -- so the sidecar is
    stripped here by its underscore prefix rather than by relaxing the model.
    """
    records = json.loads(path.read_text())
    return [AnswerCard.model_validate(strip_sidecars(r)) for r in records]


def cards_for_question(cards: list[AnswerCard], needle: str) -> list[AnswerCard]:
    """Cards whose question contains `needle`, preferring one arm.

    Mixing arms in one column would confound the comparison the page makes: a
    difference between columns must come from the persona, not from the arm.
    """
    matched = [c for c in cards if needle.lower() in c.question.lower()]
    for arm in ("strict-contract", "safe-join-contract", "free-sql"):
        in_arm = [c for c in matched if c.arm == arm]
        if {c.persona for c in in_arm} >= set(PERSONA_ORDER):
            return in_arm
    return matched


def group_by_persona(cards: list[AnswerCard]) -> dict[str, AnswerCard]:
    """One card per persona. Later cards win, which only matters for duplicates."""
    return {c.persona: c for c in cards}


def _rows_table(card: AnswerCard) -> str:
    if not card.rows:
        return '<p class="empty">no rows</p>'
    headers = list(card.rows[0])
    head = "".join(f"<th>{escape(str(h))}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(row.get(h, '')))}</td>" for h in headers) + "</tr>"
        for row in card.rows
    )
    return f"<table class=rows><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _column(card: AnswerCard) -> str:
    scope = _SCOPE.get(card.persona, "")
    context = card.context or {}
    role = escape(str(context.get("role", "")))
    schema = escape(str(context.get("schema", "")))

    # The withholding is the argument, not a footnote, so it sits directly under
    # the numbers rather than at the bottom with the provenance.
    withheld = (
        f'<div class=withheld><span class=tag>withheld</span>{escape(card.why_not)}</div>'
        if card.why_not else '<div class="withheld none">nothing withheld</div>'
    )
    return f"""
    <section class="col {escape(card.persona.lower())}">
      <h2>{escape(card.persona)}</h2>
      <p class=scope>{escape(scope)}</p>
      {_rows_table(card)}
      {withheld}
      <dl class=prov>
        <dt>role</dt><dd>{role}</dd>
        <dt>schema</dt><dd>{schema}</dd>
        <dt>metrics</dt><dd>{escape(", ".join(card.metrics_used)) or "&mdash;"}</dd>
        <dt>lineage</dt><dd>{escape(", ".join(card.lineage)) or "&mdash;"}</dd>
        <dt>query id</dt><dd class=qid>{escape(card.query_id or "")}</dd>
      </dl>
      <details><summary>SQL</summary><pre>{escape(card.sql or "")}</pre></details>
    </section>"""


_CSS = """
:root { color-scheme: light dark; --fg:#111; --bg:#fff; --mut:#666; --line:#d8d8d8;
        --warn:#8a4b00; --warnbg:#fff4e5; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e8e8e8; --bg:#141414; --mut:#9a9a9a; --line:#333;
          --warn:#ffcf8f; --warnbg:#3a2a12; } }
body { font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       color: var(--fg); background: var(--bg); margin: 0; padding: 2rem; }
h1 { font-size: 1.15rem; font-weight: 600; margin: 0 0 .25rem; }
.q { font-size: 1.05rem; margin: 0 0 .25rem; }
.sub { color: var(--mut); margin: 0 0 1.75rem; font-size: .85rem; }
.cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(270px, 1fr)); gap: 1.25rem; }
.col { border: 1px solid var(--line); border-radius: 8px; padding: 1rem; min-width: 0; }
.col h2 { font-size: .8rem; letter-spacing: .06em; margin: 0; font-family: ui-monospace, monospace; }
.scope { color: var(--mut); font-size: .8rem; margin: .15rem 0 .9rem; }
table.rows { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums;
             display: block; overflow-x: auto; }
table.rows th { text-align: left; font-size: .7rem; color: var(--mut); text-transform: uppercase;
                letter-spacing: .05em; border-bottom: 1px solid var(--line); padding: .3rem .5rem .3rem 0; }
table.rows td { padding: .3rem .5rem .3rem 0; white-space: nowrap; }
table.rows td:last-child { text-align: right; }
.empty { color: var(--mut); font-style: italic; }
.withheld { margin: .9rem 0; padding: .6rem .7rem; border-radius: 6px; font-size: .85rem;
            background: var(--warnbg); color: var(--warn); }
.withheld.none { background: transparent; color: var(--mut); padding-left: 0; font-style: italic; }
.tag { display: inline-block; font-size: .65rem; text-transform: uppercase; letter-spacing: .08em;
       font-weight: 700; margin-right: .5rem; }
dl.prov { display: grid; grid-template-columns: max-content 1fr; gap: .1rem .7rem;
          font-size: .75rem; margin: .9rem 0 .5rem; }
dl.prov dt { color: var(--mut); }
dl.prov dd { margin: 0; font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
.qid { font-size: .7rem; }
details summary { cursor: pointer; font-size: .78rem; color: var(--mut); }
pre { overflow-x: auto; font-size: .72rem; background: rgba(127,127,127,.09);
      padding: .6rem; border-radius: 5px; }
footer { margin-top: 2rem; color: var(--mut); font-size: .78rem; max-width: 62ch; }
"""


def build_page(cards: list[AnswerCard], needle: str) -> str:
    """One page for one question. Raises when nothing matches."""
    chosen = cards_for_question(cards, needle)
    if not chosen:
        raise ValueError(f"{needle!r} matched no recorded card")
    by_persona = group_by_persona(chosen)
    ordered = [by_persona[p] for p in PERSONA_ORDER if p in by_persona]
    ordered += [c for p, c in by_persona.items() if p not in PERSONA_ORDER]

    question = escape(ordered[0].question)
    arm = escape(str(ordered[0].arm))
    columns = "".join(_column(c) for c in ordered)
    return f"""<!doctype html>
<html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>One question, three identities</title>
<style>{_CSS}</style></head><body>
<h1>One question, three identities</h1>
<p class=q>{question}</p>
<p class=sub>arm <code>{arm}</code> &middot; recorded against a live Snowflake account &middot;
nothing on this page was computed at render time</p>
<div class=cols>{columns}</div>
<footer>Each column ran the <em>same</em> SQL as a different Snowflake identity. The
differences come from the warehouse &mdash; schema-scoped grants and secure views &mdash;
not from the prompt. Every query id resolves in <code>ACCOUNT_USAGE</code>.</footer>
</body></html>
"""
