# What Snowflake is building, read from its job postings

Collected 2026-09-21. Method: harvested the Phenom careers feed (294 unique postings across all
categories) and the Ashby public job-board API (`api.ashbyhq.com/posting-api/job-board/snowflake`,
350 postings with full descriptions and US compensation bands). Raw data in `.firecrawl/`.

All percentages below are share of the 350 Ashby postings.

## The headline: every single req carries the same opening paragraph

350 of 350 postings (100%) open with:

> "At Snowflake, we are powering the era of the agentic enterprise. To usher in this new era, we
> seek AI-native thinkers across every function who are energized by the opportunity to reinvent
> how they work. You don't just use tools; you possess an innate curiosity, treating AI as a
> high-trust collaborator that is core to how you solve problems and accelerate your impact."

This is boilerplate, so "agentic" appearing in 100% of postings is not evidence of 100% agentic
work. What it *is* evidence of: a company-wide mandate applied uniformly, including to warehouse
roles, legal, and workplace ops. The tell is the phrase "AI as a high-trust collaborator" — they
are screening for AI-native working style in every function, not just engineering.

## Products they are staffing

| Mentions | Product | What it is, per the postings |
|---|---|---|
| 109 | Data Cloud | umbrella branding |
| 29 | Marketplace | being rebuilt "for the AI era" — packaging data + semantic views as "ready-to-use agentic experiences" discoverable through Cortex Code and CoWork |
| 23 | dbt | now first-party after the dbt Labs acquisition |
| 18 | Observe by Snowflake | AI SRE product; Slack integrations, CLI, eval pipelines, MCP integrations |
| 16 | Snowflake Intelligence | natural-language interface over governed data |
| 15 | Iceberg | open table format |
| 12 | Streamlit | consumption layer |
| 10 | Postgres | from the Crunchy Data acquisition |
| 9 | Cortex Code (CoCo) | "Snowflake's coding agent for building with data"; has a Desktop app described as "VS Code-grade" |
| 8 | Cortex Agents | agent runtime |
| 6 | CoWork | agentic workspace; "self-correcting NL-to-SQL engines" |
| 6 | Cortex Search | retrieval: vector, hybrid, semantic indexing |
| 5 | Cortex Analyst | text-to-SQL over semantic models |
| 5 | Horizon | governance |
| 4 | Polaris | open catalog |
| 2 | Openflow, Unistore | ingestion; hybrid transactional |

Cortex Code is the strategic center of gravity. It is simultaneously a product they sell, the
internal tool they mandate ("use AI as a first-class collaborator in development, code review,
debugging, and on-call triage via Cortex Code CLI"), and the harness through which Marketplace
assets are meant to become executable.

## The engineering practice they are hiring for

- **evals — 9 postings use the literal term.** Not "evaluation" in the generic sense: eval
  pipelines, eval frameworks for LLM/agent systems, "hill-climbing infrastructure," regression
  tests generated from broken customer runs, frontier-model bake-offs. There is a whole team
  (Cortex Quality) whose job is closing the loop from production traces back into evals.
- **MCP — 9 postings.** Spread across AI products, core compute ("how Snowflake's core compute
  fabric evolves to support the burgeoning Model Context Protocol"), Observe, GTM engineering,
  partner development, and — notably — **two identity/security roles**: "controlled, audited agent
  workflows, MCP…" and "agentic AI identity, non-human identity governance, or authorization for
  autonomous workloads."
- **guardrails — 19 postings (5.4%). observability — 56 (16%).**
- **Semantic layer / semantic model / semantic view — 21 postings combined.** The semantic layer is
  treated as the substrate agents read, not as a BI convenience.

48 of 350 titles (14%) name AI, Agent, Cortex, ML, or Intelligence directly — including a
Post-Doctoral AI Researcher, "AI Research Scientist, New Grad – Agents & Reinforcement Learning,"
"Staff Research Scientist - Physical AI / Multimodality," and "Senior Engineering Manager -
Agentic Analytics."

## Where the headcount sits

Engineering 94, Solution Engineering 56, Sales 44, Marketing 36, Professional Services 23,
Product Management 20, Sales Development 17, Finance 11, Alliances 11, Global Support 11,
**Data Analytics and AI 7**, Enterprise Technology 5.

Solution Engineering at 56 and Professional Services at 23 is a large field-facing build-out —
consistent with selling agentic products that customers cannot self-serve yet.

## The Data, Analytics and AI org (DAA) — all 7 open roles

Reports into a Chief Data & Analytics Officer. Every US role is Menlo Park, 3 days/week in office.

1. **Senior Director, Analytics Engineering** — REQ20959, posted 2026-09-19, grade 10,
   **$292,000–$383,250 + equity + bonus**. Leads 20+ analytics engineers. Reports directly to the
   CDAO.
2. **Manager/Senior Manager, Finance Analytics & AI** — grade 8, $200K–$262.5K.
3. **GTM Staff Data Scientist** — grade 7, $184K–$264.5K.
4. **Staff Analyst, GTM Analytics** — grade 7, $163K–$214.2K.
5. **Senior Analyst, GTM Analytics** — grade 6, $138K–$180.6K.
6. **Senior Product Manager - Enterprise AI** — grade 6, $200K–$287.5K.
7. **Analytics Engineer - Finance** — Pune, grade 5, no published band.

### The Senior Director req, in its own words

Duties, verbatim:

- "Own Snowflake's internal analytics agents: Build, improve, and maintain general purpose
  analytics agents — and underlying context and semantic layers — that can be used across the
  organization **including evals, orchestration instructions, and ground truth data sets**"
- "Drive Snowflake's internal data transformation: … an AI ready data foundation, with an emphasis
  on **documentation, contracts, context, and governance**"
- "Champion AI-assisted engineering: Drive adoption of **Cortex Code-based agentic workflows and
  reusable skills** across your teams … including model development, PR review, and root-cause
  analysis"
- "Act as Snowflake's **customer zero**: Be the first trusted tester of Snowflake's own features"
- "Represent Snowflake: … customer conversations, speaking engagements, and publishing thought
  leadership"

Requirements worth noting: second-line leadership (managing managers); Snowflake RBAC, row access
policies, masking policies, Dynamic Tables, Streams, Tasks, Horizon, Cortex; expert dbt including
macro development and CI/CD; Airflow; **"a track record owning finance- or revenue-critical,
deadline-driven data pipelines where accuracy and auditability are non-negotiable"**; GTM/sales
analytics domain (master data management, consumption & attainment pipelines, quota/territory
data); **"Advanced adoption of AI-assisted engineering tools — Cortex Code, Claude Code, or similar
agent frameworks — including agentic skill development and prompt engineering for data
workflows"**; Streamlit/Sigma/Tableau; Jira/Confluence.

### The GTM Staff Data Scientist req is the sibling problem

"Technical leadership for Snowflake's next generation of AI & Machine Learning powered GTM
decision systems." Duties include next-best-action systems, propensity models across the GTM
funnel, causal inference and uplift modeling, and — the line that matters —

> "Define common standards for point-in-time training, backtesting, calibration, ranking quality,
> treatment-effect evaluation, uncertainty, and realized business impact."
> "Separate genuine customer and market movement from CRM changes, selection effects, territory
> shifts…"

That is a job description for non-circular evaluation of GTM decision systems.

## Status of the Senior Director posting

The careers.snowflake.com page renders "OH SNAP! THIS JOB HAS BEEN CLOSED." The posting is
nonetheless present and listed in both the Phenom search feed and the Ashby board as of
2026-09-21, published 2026-09-19. Treat the "closed" page as a rendering artifact of that
deep-link, not as proof the req is filled — but verify before investing in an application.
