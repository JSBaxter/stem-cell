---
status: accepted
supersedes: none
date: 2026-10-11
deciders: James
---

# 0002 — Template sync runs inside the cell's own Actions

## Context and problem statement

Rendered cells must receive template changes as a PR without James running
a command per cell. Either the template pushes into each cell, which needs
a credential that can write to every cell, or each cell pulls on a
schedule with its own token.

## Considered options

1. **Push from the harness or stem-cell** into every cell. Needs a cross-repo token: on the design's never-list and refused to Actions tokens.
2. **Pull from inside the cell**: a scheduled workflow in each cell calls a harness-hosted reusable workflow that runs `copier update` and opens a PR with the cell's own token.
3. **James runs copier update per cell.** The May practice; it did not happen.

## Decision

We will adopt option 2. The caller stub is rendered by the template and
pinned like the other stubs; the reusable workflow lives in the harness
with the gate. Copier runs on the runner via `uvx`.

## Consequences

- No new credential; the cell's `GITHUB_TOKEN` opens the PR. A PR opened
  with that token triggers no other workflows, so the gate runs on it only
  after a human or the fix workflow pushes; recorded as a known limit, and
  the sync PR is docs-and-config, reviewed by James.
- Actions minutes per cell per schedule run; weekly by default.
- Conflicts surface as `.rej` files in the PR, visible, never silent.
