---
status: accepted
supersedes: none
date: 2026-10-11
deciders: James
---

# 0001 — stem-cell is the only template

## Context and problem statement

Two templates made new repositories: the harness's templates directory,
copied once and mirrored to a project-template repository, and this copier
template, which can update a rendered repository later. The cell operating
model requires a template with an update path. Keeping both meant two
places to edit for every per-cell file.

## Considered options

1. **Two templates**, stem-cell wrapping the harness's. Two copies of each file.
2. **stem-cell only.** The per-cell files move here; the harness keeps skills, workflows and the reviewer, referenced by name and pinned SHA.

## Decision

We will adopt option 2 ("stem cell only", James, 2026-10-11). The harness
templates directory and the project-template repository are retired once
the first cell renders from here.

## Consequences

- One copy of every per-cell file.
- The harness's `new-experiment` and `init-project` paths switch to
  rendering with copier; a harness task.
- Cells carry harness references only as pinned caller stubs and the
  plugin pointer.
