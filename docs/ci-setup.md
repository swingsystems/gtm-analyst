# Wiring CI to a warehouse

Without this, CI checks lint, the spec, the unit tests, and the no-account demo.
That is real but it is not the thing this project claims. The governance
boundary, the invariants, and the planted defects all need a warehouse, and
until these secrets exist those jobs are **skipped, not passed** — the workflow
says so in an annotation rather than going quietly green.

Three files in this repository once claimed CI enforced the chaos suite while CI
held no credentials and 7 of 8 chaos tests skipped. That is the failure this
page exists to prevent, and it is worth knowing it already happened once.

## Secrets

| Secret | What it is |
|---|---|
| `SNOWFLAKE_ACCOUNT` | account identifier, `ORG-ACCOUNT` |
| `SNOWFLAKE_USER` | the CI operator user |
| `SNOWFLAKE_PRIVATE_KEY` | PEM private key, whole file including header and footer |
| `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | omit if the key is unencrypted |
| `SNOWFLAKE_WAREHOUSE` | warehouse name |

The workflow writes the key to `/tmp/key.p8`, `chmod 600`s it, and removes it in
an `if: always()` step so a failing test does not leave it on the runner.

## Read this before you add the key

**The key CI holds can act as every persona.** All three service users register
the same public key, so whatever private key CI gets can open a session as
finance, as EMEA, and as the rep. That is convenient and it is the weakest part
of this setup: a compromised runner is every persona at once.

A real deployment gives each service user its own key pair and CI only the ones
it needs. This repository does not, because a single-operator reference
deployment sharing one key was a reasonable trade and pretending otherwise here
would be worse than saying so.

**Use a dedicated account.** CI runs the chaos suite, which deliberately breaks
models and rebuilds them. Point it at a warehouse nobody is reading from.

**Forks do not get your secrets.** GitHub withholds secrets from
`pull_request` runs on forks by design. A contributor's PR therefore gets the
credential-free job only, which is correct — and means a change that breaks the
boundary passes their CI and fails yours. Review accordingly.

## Provisioning a CI user

```sql
USE ROLE ACCOUNTADMIN;

CREATE USER IF NOT EXISTS GAA_CI
    DEFAULT_ROLE = GAA_LOADER
    DEFAULT_WAREHOUSE = <your warehouse>
    TYPE = SERVICE
    COMMENT = 'CI. Rebuilds models for the chaos suite.';

ALTER USER GAA_CI SET RSA_PUBLIC_KEY='<the CI public key body>';

-- The loader role only. CI must NOT hold the persona roles: it connects as the
-- persona SERVICE users, and granting the roles to CI directly re-creates the
-- escalation path finding 1 in the threat model is about.
GRANT ROLE GAA_LOADER TO USER GAA_CI;
```

Then run `make check-drift` — the new user shows as drift against the committed
baseline, which is the system working. Review it, then `make baseline`.

## Branch protection

The workflows are worth little without it. A contributor who can push to the
default branch can also weaken a chaos variant or a reference query and leave CI
green — not because it was fooled, but because the change went in without
running.

On the default branch, require: pull requests before merging, the `check` and
`warehouse` jobs to pass, branches up to date before merging, and no force
pushes. `evals/spec/` deserves a CODEOWNERS entry: the frozen spec is the
evidence that the questions predate the models, and a rewrite there cannot be
repaired by rewriting history, because rewriting is the thing the history exists
to disprove.
