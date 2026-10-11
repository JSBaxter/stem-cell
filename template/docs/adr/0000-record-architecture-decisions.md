---
status: accepted
supersedes: none
date: 2026-08-31
deciders: James
---

# 0000 — Record architecture decisions

## Context and problem statement

Agents (and future humans) that can't see why something was built the way it was
will happily refactor the reason away. Decision history needs to live in the
repo, where every agent session can read it.

## Decision

We will record significant architecture decisions as MADR-style records in
`docs/adr/`, numbered sequentially (`NNNN-kebab-title.md`). Records are
superseded, never deleted or rewritten. Agents draft ADRs via the `/adr` skill;
a human flips them from `proposed` to `accepted`.

## Consequences

- Agents must read relevant ADRs before changing an area (enforced via
  CLAUDE.md) and reviewers flag PRs that contradict an accepted ADR.
- Slight ceremony cost per real decision; none for routine implementation
  choices, which don't get ADRs.

## Alternatives considered

- CLAUDE.md as the only decision store — holds current rules well ("what"), but
  accumulates poorly and loses the reasoning ("why").
- External docs/wiki — invisible to agent sessions; goes stale.
