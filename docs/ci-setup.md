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

## CI gets its own key, not yours

Snowflake allows **two** public keys per user. The operator's key stays in slot
one and is never uploaded anywhere; a dedicated CI key goes in slot two on the
three persona service users. CI access can then be revoked on its own by
clearing `RSA_PUBLIC_KEY_2`, without rotating the operator's key or touching
anyone else's access.

The CI user holds `GAA_LOADER` and nothing else. Granting it the persona roles
would re-create the escalation path finding 1 in the threat model is about; it
reaches personas only by connecting **as** the persona service users, which is
the same path everything else uses.

**What this does not fix.** One CI key still opens a session as all three
personas, because the boundary tests have to connect as each of them to test
anything. A compromised runner is every persona at once. The improvement is
containment and revocability, not elimination — and the honest mitigation is
pointing CI at an account you can afford to lose, which you should do anyway
because the chaos suite deliberately breaks and rebuilds models.

**Use a dedicated account.** CI runs the chaos suite, which deliberately breaks
models and rebuilds them. Point it at a warehouse nobody is reading from.

**Forks do not get your secrets.** GitHub withholds secrets from
`pull_request` runs on forks by design. A contributor's PR therefore gets the
credential-free job only, which is correct — and means a change that breaks the
boundary passes their CI and fails yours. Review accordingly.

## Provisioning a CI user

```bash
mkdir -p ~/.gtm-analyst-ci && chmod 700 ~/.gtm-analyst-ci
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out ~/.gtm-analyst-ci/ci_key.p8
chmod 600 ~/.gtm-analyst-ci/ci_key.p8
openssl rsa -in ~/.gtm-analyst-ci/ci_key.p8 -pubout -out ~/.gtm-analyst-ci/ci_key.pub
```

Keep it outside the repository. `.gitignore` is one `git add -f` away from
failing, and the pre-commit hook is a backstop rather than a boundary.

```sql
USE ROLE ACCOUNTADMIN;

CREATE USER IF NOT EXISTS GTM_CI
    DEFAULT_ROLE = GAA_LOADER
    DEFAULT_WAREHOUSE = <your warehouse>
    TYPE = SERVICE
    COMMENT = 'GitHub Actions. Rebuilds models for the chaos suite.';

ALTER USER GTM_CI SET RSA_PUBLIC_KEY='<ci public key body>';
GRANT ROLE GAA_LOADER TO USER GTM_CI;   -- the loader role, and nothing else

-- Slot two, so the operator's key is never uploaded and CI can be revoked alone.
ALTER USER GAA_SVC_FINANCE_GLOBAL SET RSA_PUBLIC_KEY_2='<ci public key body>';
ALTER USER GAA_SVC_SALES_DIR_EMEA SET RSA_PUBLIC_KEY_2='<ci public key body>';
ALTER USER GAA_SVC_REP_INDIVIDUAL SET RSA_PUBLIC_KEY_2='<ci public key body>';
```

Then run `make check-drift`. The new user shows as drift against the committed
baseline, which is the system working. Review it, then `make baseline`.

To revoke CI later, without rotating anything else:

```sql
ALTER USER GAA_SVC_FINANCE_GLOBAL UNSET RSA_PUBLIC_KEY_2;   -- and the other two
DROP USER GTM_CI;
```

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
