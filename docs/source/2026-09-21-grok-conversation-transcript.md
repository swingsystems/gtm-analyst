# Grok conversation transcript — GTM Agents project origin

Captured 2026-09-21. Voice conversation held in-car; transcript pasted by Rama Kattunga.
Source material only — claims in this document are UNVERIFIED and several are suspected
inaccurate. See `docs/source/grok-claims-audit.md` for the reconciliation.

---

**Speaker 1 (Grok) 0:05**

Here's the concrete path. Snowflake's trial gives you $400 of free compute and includes their
managed MCP server out of the box, which exposes Cortex Analyst, Direct SQL, and custom tools to
Claude Code. You'd create a schema that mirrors Salesforce's core objects: account, contact,
opportunity, plus a custom object for license type, something like `license_type_c`, with values
perpetual and subscription. Then seed it with realistic relational data. There's an open source
tool called Snowfakery from Salesforce that generates linked records, accounts with nested
contacts and opportunities, all with proper foreign keys. You can also grab the Kaggle sample
sales CRM dataset, which has 10,000 accounts, 18,000 contacts, and 16,000 opportunities already
shaped like Salesforce. The key move is wrapping Snowflake behind an MCP server that exposes the
same tool names Salesforce's hosted MCP uses, things like `query_sobjects`, `update_opportunity`,
`create_task`. That way, when you swap in a real Salesforce org later, zero agent code changes.
The agent doesn't know or care where the data lives. For the perpetual to subscription angle
specifically, you generate a scenario where roughly 40% of accounts are still on perpetual
licenses, with maintenance contracts expiring on staggered dates, usage signals declining, and a
scoring model that ranks conversion likelihood. Then the agent reads that through the MCP layer,
ranks targets, drafts outreach, and logs everything behind approval gates. One thing to flag:
Snowflake's trial MCP server is read-write capable but rate-limited. So for the eval framework,
you'd want a local fallback, maybe a SQLite mirror, or even just JSON files behind a second MCP
server, so your regression tests run in seconds instead of waiting on cloud queries.

**Rama 2:07** — I'm accessing this from the car, so I can't see the text.

**Speaker 1 2:18**

Four tables. Accounts with fields for name, industry, annual revenue, and a custom field called
license type, which is either perpetual or subscription. Contacts linked to accounts by account
ID with name, email, title, and role. Opportunities linked to accounts with amount, stage, close
date, and a source field. And a custom table called License Events, which tracks every time a
customer moved from perpetual to subscription, with the date, the old and new contract value, and
who owned the deal. For the Snowfakery recipe, you'd define accounts first, say 200 of them,
split roughly 60/40 between subscription and perpetual. Then nest contacts inside each account,
two to five per account. Then nest opportunities inside accounts, one to three per account. Then
generate license events only for the accounts that flipped, maybe 30 of them, with dates spread
across the last 18 months. The trick is the foreign keys. Snowfakery handles that automatically
if you nest the objects in the recipe, so contacts always point to a real account, opportunities
always point to a real account, no orphaned records. Once that's loaded into Snowflake, you point
the MCP server at it, and Claude Code can query it like it's a live Salesforce org. You just swap
the connection string later.

**Rama 3:57**

I already have Snowflake set up. A small point of correction: we are not trying to move from
perpetual to subscription. We have both licensing formats. B2C is mostly subscription. B2B is
perpetual — all the studios and production houses in the Avid products take those licenses.

**Speaker 1 4:30**

Good catch. That makes the problem richer. Now the agent has to juggle two completely different
sales motions under one roof. B2C subscription is high volume, low touch, self-serve, churn
driven. B2B perpetual is low volume, high touch, relationship driven, maintenance contract
driven. The agent needs to recognize which track a lead belongs to and route it accordingly. That
means your schema needs a segment field on accounts, B2C or B2B, and the opportunity stages
differ too. B2C might be a simple funnel — lead, converted, churned. B2B has a longer cycle with
discovery, proposal, negotiation, closed won, plus a maintenance renewal loop. The scoring model
gets interesting because the signals are totally different. For B2C you'd watch usage frequency,
feature adoption, support ticket volume. For B2B you'd watch contract renewal dates, seat count
changes, project milestones, even public announcements about new facility builds or show
productions. The outreach differs too. B2C gets automated nurture sequences. B2B gets researched,
personalized outreach, maybe even intelligence about what they're currently producing or which
Avid products they already own. So the agent isn't just ranking conversion candidates; it's
classifying the segment first, then applying the right playbook. That's a much stronger portfolio
story because it shows the agent can make judgment calls, not just follow one script.

Reworked recipe: file `avid-dual-track.recipe.yml`. First block defines accounts — about 300, each
randomly assigned a segment, roughly 70% B2C and 30% B2B, since consumer users outnumber studios.
Industry field: B2C gets individual creator, freelancer, educator; B2B gets production house,
broadcast network, post-production studio, film school, live event company. Second block nests
contacts inside accounts — B2C accounts get one contact, the end user; B2B accounts get two to
four: a technical buyer, a creative director, maybe an IT admin, each with a different role field.
Third block nests opportunities, split by segment. B2C opportunities are simple: stage is new,
converted, or churned; amount is low, $20 to $200; close date within the last 12 months. B2B
opportunities are richer: stages go discovery, technical evaluation, proposal, negotiation, closed
won, closed lost; amounts range $5,000 to $250,000; plus a product family field — Pro Tools, Media
Composer, Sibelius, or M-Audio hardware — and a maintenance status field: active, expiring within
90 days, or lapsed. Fourth block is the license events table, now tracking both directions: some
records show a B2C user upgrading from free trial to paid subscription, others show a B2B studio
adding seats to an existing perpetual license, a few show a B2B customer downgrading from
perpetual to subscription, which is the edge case that makes the data interesting. Fifth block
adds activities: for B2C, mostly automated email opens and clicks; for B2B, calls, meetings, demo
requests with notes fields mentioning specific project names or production titles. The foreign key
nesting is what makes this work. Snowfakery automatically links every contact to its parent
account, every opportunity to its account, every activity to its opportunity. So when Claude Code
queries through the MCP server, it can ask something like "show me all B2B accounts with expiring
maintenance in the next 90 days that have more than three seats" and get back a clean relational
result. One more thing: add a churn risk score field on B2C accounts computed from usage frequency
and support tickets, and a renewal risk score on B2B accounts computed from maintenance expiry and
seat count trends. Those two scores become the ranking signal the agent uses to decide who to
prioritize.

**Rama** — I'll let Claude Code generate from the description. But tell me exactly what problem
we're solving. What does GTM mean?

**Speaker 1 9:37**

Go-to-market or GTM is everything a company does to find customers, sell to them, and keep them.
Prospecting for new leads, qualifying them, closing the deal, onboarding the customer, then
renewing or expanding that relationship over time. It's the whole revenue engine, not just the
sales pitch. "Claudification" is Anthropic's internal name for the practice of using Claude agents
to run those GTM motions autonomously instead of a human rep doing every step manually. You build
agents that research accounts, draft outreach, update the CRM, flag at-risk renewals, and route
deals to the right person, all with human approval gates where it matters. The Claudification team
at Anthropic builds these agents for Anthropic's own sales org, and that's the $320–405,000 role
you saw.

Now the specific problem for Avid. Avid sells the same products — Pro Tools, Media Composer,
Sibelius — through two completely different channels with two completely different economics. On
the B2C side it's a high volume, low touch subscription motion. Think a freelancer buying a
monthly Pro Tools subscription. The agent needs to detect churn signals early, trigger automated
nurture, and convert free trials efficiently. On the B2B side it's a low-volume, high-touch,
perpetual license motion. Think a broadcast network buying a 50-seat Media Composer deployment
with a multi-year maintenance contract. The agent needs to research the studio, understand their
production pipeline, time the outreach around contract renewals, and coordinate multi-stakeholder
deals. The gap nobody has filled is an agent that can look at an incoming lead, instantly classify
which track it belongs to, apply the right scoring model, pull the right playbook, and execute,
all without a human having to manually route it. Right now, at companies like Avid, that routing
is done by RevOps people or sales ops analysts who eyeball it. The agent replaces that judgment
layer. That's the story: one agent, two revenue models, intelligent classification, autonomous
execution with guardrails.

**Rama 11:47** — Can you send this conversation to my email?

**Speaker 1** — I can't send emails. [Discussion of session persistence omitted.]

**Rama 13:22** — I'm already parked. Generate the complete clean history so I can record it.

**Speaker 1 13:33 — full reconstruction**

*Section one: the big question.* Can current frontier AI models build the next generation of
frontier models by themselves? Short answer: not fully, not yet. What exists today is partial
recursive self-improvement. Claude writes over 80% of the code merged into Anthropic's own
production codebase. OpenAI admitted early versions of GPT-5.3 Codex were instrumental in creating
itself, but genuine methodological novelty is still rare. A systematic evaluation in August 2026
found only three out of 252 agent solutions qualified as truly novel. Chinese researchers from
ByteDance, Tsinghua, and Shanghai AI Lab published a five-level roadmap on September 16, 2026,
called "the last AI built by humans"; we're mostly at levels one and two. Level five, where AI
redesigns its own improvement process, is barely explored. Jack Clark puts roughly 60% odds on
fully autonomous AI research and development by end of 2028. OpenAI targets an automated AI
researcher by March 2028 but admits they don't yet know how to safely reach aligned, full
recursive self-improvement.

*Section two: your situation and goal.* You were laid off from Avid in April. You're not a systems
engineer who can pass LeetCode. You want to build something using Claude Code or Codex that
attracts recruiters from OpenAI and Anthropic. You noticed Anthropic's Claudification team posting
a staff software engineer role at $320–405,000. That role is about building autonomous GTM agents
with evals and guardrails, not about model training or LeetCode. Your Avid domain knowledge is the
unfair advantage.

*Section three: the problem.* [GTM and Claudification definitions as above; the dual-track Avid
problem as above.]

*Section four: the portfolio project.* A public open-source Claude Code system called something
like `subscription-migration-agents` or `dual-track-revenue-agents`. Three layers. Layer one: an
MCP connector that reads the CRM, identifies accounts by segment, scores churn or renewal risk,
and flags top conversion candidates. Layer two: an autonomous outbound agent that researches each
target, drafts personalized outreach referencing their specific Avid products, and queues it
behind an approval gate. Layer three: an eval framework with a golden set of 50 real deal
scenarios, a scoring function, and regression detection. The differentiator that impresses
recruiters is the eval layer and a written retro of every failure mode after 30 days of running.

*Section five: the data strategy.* Since you no longer have Avid Salesforce access, use your
Snowflake trial, which includes $400 of free compute and a managed MCP server. Create a schema
mirroring Salesforce core objects — account, contact, opportunity — plus a custom license type
field with values perpetual or subscription, and a segment field with values B2C or B2B. Seed it
with synthetic relational data using Snowfakery. Alternatively grab the Kaggle sample sales CRM
dataset with 10,000 accounts, 18,000 contacts, and 16,000 opportunities. Wrap Snowflake behind an
MCP server exposing the same tool names Salesforce's hosted MCP uses — `query_sobjects`,
`update_opportunity`, `create_task` — so swapping in a real Salesforce org later requires zero
agent code changes. For the eval framework, add a local SQLite or JSON fallback so regression
tests run in seconds.

*Section six: the Snowfakery recipe.* [As described above — 300 accounts, 70/30 B2C/B2B, nested
contacts, segment-split opportunities, bidirectional license events, segment-split activities, and
two risk score fields: churn risk score on B2C from usage frequency and support tickets, renewal
risk score on B2B from maintenance expiry and seat count trends.]

*Section seven: the agent logic.* The agent reads an incoming lead through the MCP layer,
classifies the segment first, then applies the right playbook. For B2C: detect churn signals,
trigger automated nurture, convert free trials efficiently. For B2B: research the studio,
understand their production pipeline, time outreach around contract renewals, coordinate
multi-stakeholder deals. The agent ranks by risk score, drafts personalized outreach, logs
everything behind approval gates, and updates the CRM only after human sign-off.

*Section eight: what makes this portfolio story strong.* One agent, two revenue models, intelligent
classification, autonomous execution with guardrails, a public GitHub repo with a clean CLAUDE.md,
an eval framework with regression detection, and a written failure retro. That combination is what
the Claudification team screens for.
