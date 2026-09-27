# Results

Two grids. **Never merged** — see
[ADR 0007](../docs/adr/0007-two-providers-never-one-grid.md). An arm difference
across two models is indistinguishable from a model difference, so there is no
combined figure anywhere in here.

| grid | model | cells | status |
|---|---|---|---|
| [`openai-full/`](openai-full/) | `gpt-4.1` | 108/108 | complete, all twelve questions, $1.15 |
| [`pilot2/`](pilot2/) | `claude-sonnet-5` | 25/36 | partial — stopped by a provider spending limit |
| [`discarded/`](discarded/) | `gpt-4.1` | 65 | **thrown away**, with the reason |

`gtm compare --grid openai=openai-full/cards.json --grid claude=pilot2/cards.json`
reports them side by side and refuses to sum them.

## The one result worth arguing about

On the five questions the strict arm could not express, under `gpt-4.1` free SQL
was **wrong on 13 of 15 cells**. Under `claude-sonnet-5`, across four dedicated
q011 trials, the free arm never committed the failure the trap was built to
catch.

The same architecture, the same questions, the same warehouse — and the
governance conclusion inverts depending on the model. ADR 0003 pre-registered
both branches before either grid ran, so both readings are published as they
fell.

**Quoting either number without the other is quoting half of it.**

## Cost

`gpt-4.1`: 108 cells, 407 API calls, **$1.15** — about a cent an answer,
recorded per card rather than estimated. An earlier estimate extrapolated from
Claude tool-call counts said $0.32 a cell, thirty times high. That gap is the
argument for measuring spend rather than reasoning about it.

The `claude-sonnet-5` cells predate spend measurement and carry no usage. They
are counted as **unmeasured, never as free** — those runs cost real money.

## What has been thrown away, and why that is here

`discarded/openai-contaminated-2026-09-26` is 65 cells of a grid that ran while
CI was applying chaos variants to the same database. One cell recorded
461,925,638.35 against a ground truth of 1,032,569.31 and looked exactly like
the fan-out trap firing — the single result the experiment most wanted to see.

It is kept because a run thrown away for a known reason is evidence about the
harness, while one silently deleted is a gap in the record.
