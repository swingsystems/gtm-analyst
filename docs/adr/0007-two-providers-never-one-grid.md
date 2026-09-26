# ADR 0007 — Two model providers, never merged into one grid

Date: 2026-09-26
Status: Accepted

## Context

The Claude pilot stopped at 25 of 36 cells when the provider's spend limit was
reached, with access returning on the first of the month. An OpenAI key was
available.

The obvious move was to finish the grid on OpenAI. It is also the worst
available option, and it is worth writing down why, because it looks like
pragmatism.

## Decision

**A grid is single-model. Cells from different providers are never merged.**

If 25 cells come from `claude-sonnet-5` and 11 from `gpt-4.1`, then any
difference between arms could be a difference between models. The experiment
exists to compare arms — free SQL against declared contracts against
contract-plus-safe-joins — and mixing models makes that comparison
uninterpretable while leaving it looking complete. This is the same failure as
the arm-separation bug found earlier in this project, where both constrained
arms read the same contracts directory and the experiment would have compared an
arm against itself.

Filling in 11 cells would have produced a full-looking table that answered no
question. A partial grid that says it is partial is worth more.

So the provider abstraction exists to enable a **complete separate
replication**, and the code refuses the shortcut:

- `resume_from` replays only cells whose recorded model matches the run's model.
  A Claude cell cannot silently enter an OpenAI grid.
- `provider_for` raises on an unknown provider instead of defaulting. A silent
  fallback would mean a run labelled `openai` was actually Claude — an
  experiment misreporting its own conditions.
- Every card records the model that produced it, so a merge is detectable after
  the fact rather than only preventable before it.

## What comparability requires

A cross-model result is worthless if the two models were asked different
questions. Both providers therefore receive:

- the **identical system prompt**, byte for byte. Not reworded for the platform,
  however reasonable that would be — any edit turns a model comparison into a
  prompt comparison.
- the **identical tool surface**: same tools, same names, same required
  arguments, asserted by comparing the converted schemas field by field.

Three conversion details fail quietly rather than loudly, which is why they are
tested directly rather than only through a live run:

| Detail | How it fails |
|---|---|
| OpenAI nests tools under a `function` wrapper and names the schema `parameters` | No error. The model is offered no tools and answers from memory, which reads as a weak model rather than a bug. |
| Tool results become one message each, role `tool`, carrying the call id | Collapsing several into one loses the pairing, and the model answers against the wrong tool's output without complaining. |
| Arguments must be a JSON **string** | Some clients accept a dict, others reject the call — and a rejected call reads as the model refusing. |

Cached prompt tokens are reported inside `prompt_tokens` by OpenAI and are
subtracted out rather than double counted.

## Consequences

- Two independent result sets, reported separately and never summed.
- The OpenAI replication runs the **full** 12-question grid, 108 cells, because
  a complete grid on one model answers more than a patched grid on two. Measured
  cost made this affordable in a way the estimate did not suggest: the first
  live cell cost one cent, against a $0.32 estimate extrapolated from Claude
  tool-call counts.
- A genuinely new question becomes answerable: whether the governance findings
  are model-dependent. Any reviewer would ask it, and before this the answer was
  unknown.
- The Claude grid stays partial and says so. It is not retroactively completed.
