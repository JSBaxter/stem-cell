---
status: accepted
supersedes: none
date: 2026-10-11
deciders: James
---

# 0000 — Record architecture decisions

## Context and problem statement

Agents and future humans that cannot see why something was built the way
it was will refactor the reason away. Decision history needs to live in
the repository, where every session can read it.

## Decision

We will record significant decisions as MADR-style records in `docs/adr/`,
numbered sequentially, superseded and never deleted or rewritten, with the
same four-key frontmatter the harness uses.

## Consequences

Decisions are reviewable in PRs and readable by any agent before it
changes the template.
