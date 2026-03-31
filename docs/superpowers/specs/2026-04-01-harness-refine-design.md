# Harness Refine Design

## Context

`harness measure` is already able to evaluate a target codebase and produce exactly three actionable suggestions. The current `harness refine` command is only a skeleton: it runs a baseline evaluation, prints the suggestion count, and stops.

The next milestone is to turn `refine` into a real search-and-improve loop that expands candidates from measure feedback, re-measures them, and chooses the best or most promising result for continued evolution.

## Goals

- Define one refine step as a fixed two-level expansion:
  - baseline -> 3 first-layer candidates
  - each first-layer candidate -> re-measure -> 3 second-layer candidates
  - compare baseline + 3 first-layer + 9 second-layer candidates together
- Allow repeated refine rounds when `--loop` is enabled
- Keep scoring transparent and testable
- Keep orchestration separate from CLI presentation
- Preserve the target workspace in a valid, self-checked state after each round

## Non-Goals

- General beam search or arbitrary-depth tree search
- Complex hidden scoring formulas
- Coupling refine orchestration to Git branches as the core execution model
- Retrying candidates only because their score is mediocre

## Refine Semantics

One refine step is a fixed search round:

1. Run baseline measure on the target path
2. Read exactly three suggestions from the baseline report
3. Create three first-layer candidates, one per suggestion
4. For each successful first-layer candidate:
   1. run a full measure
   2. read its next three suggestions
   3. create three second-layer candidates
5. Compare all available candidates across all levels:
   - baseline
   - first-layer candidates
   - second-layer candidates
6. Select the best or most promising candidate
7. Apply the selected candidate back to the target path

When `--loop` is enabled, the selected winner becomes the next round's baseline and the process repeats until a stopping condition is met.

## Core Model

### Candidate

Each explored version is represented as a `Candidate` object with these fields:

- `id`: unique identifier
- `parent_id`: parent candidate id, or `None` for baseline
- `depth`: `0`, `1`, or `2`
- `suggestion_trace`: ordered suggestion chain from baseline to current candidate
- `workspace`: isolated workspace path for this candidate
- `evaluation`: complete measure result, ideally reusing `Evaluator.run()`
- `status`: lifecycle state such as `pending`, `applied`, `self_checked`, `measured`, `failed`, or `selected`
- `retry_count`: retries consumed while trying to apply the current suggestion
- `selection_reason`: explanation recorded for round summary output

### RefineRound

Each refine round owns:

- the round baseline candidate
- all candidates created in the round
- the expansion workflow for depth 1 and depth 2
- the final round selection result

This keeps CLI state simple and makes loop execution a sequence of independent rounds.

## Execution Flow

### Candidate Execution Unit

Both first-layer and second-layer candidates should use the same execution function:

1. create an isolated workspace from the parent candidate
2. apply one suggestion
3. run fast self-checks
4. if self-checks pass, run full measure
5. persist candidate result and metadata

This keeps tree depth and execution mechanics decoupled.

### Workspace Isolation

Candidates should execute in isolated workspaces rather than directly mutating the target path during search.

Recommended model:

- baseline uses the target path
- each candidate gets its own temporary workspace copied from its parent
- mutation, self-check, and measure all run inside that workspace
- only the selected winner is copied back to the target path at the end of the round

This treats refine as search over sandboxes instead of search over live repository state.

### Suggestion Application

Suggestion application should be isolated behind a dedicated boundary. Inputs:

- candidate workspace path
- current suggestion
- optional parent evaluation summary for extra context

Outputs:

- whether application succeeded
- touched files
- failure reason when application fails

This allows the orchestration layer to stay stable even if the editing backend changes later.

### Retry Policy

`max_retries` applies only to execution failure, not to mediocre scoring.

Retry loop:

1. apply suggestion
2. run fast self-checks
3. if self-checks fail, feed the failure summary back into the suggestion applier
4. retry until success or `max_retries` is exhausted

Once a candidate has passed self-checks and completed full measure, its score is final for that branch.

### Self-Checks and Measure Timing

Execution uses two validation layers:

- fast self-checks immediately after applying a suggestion
- full measure only after fast self-checks pass

Fast self-checks should at minimum run:

- `ruff`
- `mypy`
- `pytest`

Full measure continues to use the existing evaluator flow and final report generation.

### Second-Layer Expansion Condition

A first-layer candidate expands into second-layer candidates only when:

- it successfully completes full measure
- its final report still contains suggestions

Failed first-layer candidates remain part of the final comparison set but do not expand further.

## Scoring and Selection

Selection should be transparent, deterministic, and easy to test.

### Primary Ordering

Candidates should be ranked by a tuple-like ordering derived from measure results:

1. whether hard and QC evaluations pass
2. whether the final verdict is `Pass`
3. average maintainability index
4. understandability score
5. number of critical CC issues, fewer is better

Metric extraction should reuse the existing helpers in `soft_eval_report.py` instead of reimplementing threshold logic.

### Potential

"Most promising" is only a secondary ordering concept for near ties, especially among failing candidates.

Examples:

- a candidate that clears hard failures but still fails soft quality is more promising than one that still fails hard gates
- a candidate closer to pass thresholds is more promising than one that regresses several metrics

Potential is not a separate black-box score. It is a deterministic tie-breaker layered on top of the primary ordering.

### Comparison Set

Round selection compares every available level together:

- baseline
- all first-layer candidates
- all second-layer candidates

This avoids losing a strong first-layer candidate when second-layer exploration regresses.

## Looping

Without `--loop`, refine performs exactly one round.

With `--loop`, the selected winner becomes the next round baseline.

Recommended stopping conditions:

- the winner has no suggestions for further expansion
- the winner is not better or more promising than the previous baseline
- `--max-rounds` is reached

`--loop` should mean "allow multiple refine rounds", not "run forever".

## CLI Design

Recommended `refine` parameters:

- `path`
- `--max-retries`
- `--loop`
- `--max-rounds`

The existing `--steps` option should be removed because one refine step now has a fixed product meaning: the two-level `3 + 9` expansion round. Keeping `steps` would create conflicting meanings between branch depth and outer refine rounds.

CLI output should clearly show:

- baseline verdict and key metrics
- first-layer candidate summary
- second-layer candidate summary
- round winner
- loop continuation or stopping reason

## Module Boundaries

Refine logic should be split into focused modules instead of expanding `cli.py`.

Suggested modules:

- `refine_models.py`
  - `Candidate`, `RefineRound`, `SelectionResult`
- `refine_scoring.py`
  - metric extraction adapters, ranking, tie-breakers
- `refine_workspace.py`
  - workspace creation, copy-back, cleanup
- `refine_apply.py`
  - suggestion application backend boundary
- `refine_engine.py`
  - round orchestration and loop orchestration

`cli.py` should remain a thin adapter for argument parsing and console presentation.

## Testing Strategy

Testing should start with orchestration and scoring behavior, not with real LLM-driven code edits.

### CLI Tests

- argument handling for `--loop`, `--max-rounds`, and `--max-retries`
- correct delegation from CLI to refine engine

### Engine Tests

- exit early when baseline has no suggestions
- create exactly three first-layer candidates from baseline suggestions
- create up to nine second-layer candidates from successful first-layer candidates
- compare all levels rather than only leaf candidates
- stop looping when there is no improvement, no suggestions, or max rounds is reached

### Scoring Tests

- hard and QC passing candidates outrank failing candidates
- pass verdict outranks fail verdict
- MI, QA, and CC ordering behaves deterministically
- potential only affects secondary ordering

### Integration Tests

- selected winner is copied back to the target path
- self-check failures trigger retries
- candidates that fail self-check do not proceed to full measure

## Open Assumptions Chosen Explicitly

- One refine step is fixed to a two-level `3 + 9` candidate expansion round
- Selection compares all levels, not only second-layer leaves
- Search uses isolated workspaces rather than Git branches as the primary execution model
- Retry is for execution failure only
- `--loop` is bounded by explicit stopping conditions and `--max-rounds`

## Implementation Direction

The first implementation milestone should focus on the orchestration skeleton with deterministic tests:

1. introduce refine models, scoring, workspace, and engine modules
2. move CLI refine command to the new engine
3. implement single-round orchestration and winner selection
4. add loop orchestration
5. connect suggestion application backend
6. validate with full repository self-checks and tests
