# Security

## Reporting a vulnerability

Open a [private security advisory](../../security/advisories/new) on GitHub.
Please do not open a public issue for anything that would let someone read data
they should not.

This is a single-maintainer project. A realistic expectation is a first reply
within a week, not within a day. If that is too slow for your situation, say so
in the report and the response will be prioritised accordingly.

## What is in scope

This is a **reference architecture** deployed against **synthetic data**. There
is no hosted service and no production instance, so "in scope" means a defect in
the architecture that would matter to someone who adopted it:

- A path by which one persona reads another persona's data
- A way for an agent to influence which role or schema its query runs under
- SQL injection through a metric contract, a filter value, or a tool argument
- A way to make the evaluation report a passing result it should not
- Anything that lets a caller reach `GAA.MARTS` or `GAA.IDENTITY` directly

That fourth one is unusual and deliberate. A harness that can be made to report
green is a security defect here, because the entire claim of this project is
that the measurement is honest. Two scorer bugs in this repository's history
already flattered its own thesis.

## Known and documented, not vulnerabilities

Read [`docs/threat-model.md`](docs/threat-model.md) before reporting. It lists
what is accepted and why, and states residual risk on the items marked closed.
Reports restating a documented accepted risk are still welcome as an argument
that the acceptance is wrong — say so explicitly and make the case, rather than
filing it as a discovery.

Two things worth knowing up front, both in that document:

- All three persona service users register the **same public key**, so a
  compromised key acts as every persona.
- The MCP server's network auth is one shared bearer token. A gate, not an
  identity system.

## If you are deploying this

The boundary rests on grants being correct, because Snowflake Standard Edition
has no row access policies. Test it adversarially on your own account before
trusting it: `tests/test_governance_boundary.py` shows how, and `make
check-drift` tells you when somebody has changed the grants since.

Do not reuse the reference deployment's identity map. `GAA.IDENTITY.MAP_USER_TO_REP`
decides who a session is, and it ships seeded with one demo mapping.
