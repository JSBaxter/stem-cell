# Reproduction

This cell was born from the [`stem-cell`][template]
copier template. This file explains how to spawn a sibling cell and
how to pull updates from the template into this cell.

It is identical in every cell that comes from this template — the
specific answers given when this cell was scaffolded live in
`.copier-answers.yml` at the repo root.

[template]: https://github.com/JSBaxter/stem-cell

## What "reproduction" means here

A **cell** is a single agent-driven repository: one purpose, one
queue, one doc spine. Cells reproduce by spawning new cells from
the template. The template is the species; each cell is an
individual.

When you (operator or agent) need a new cell — to host a new tool,
service, library, or agent task — you do not start from a blank
directory. You spawn a cell. It comes pre-equipped with:

- the queue (so the new cell's agent can track its own work)
- the doc spine (CONTRIBUTING, AGENTS, CLAUDE, TESTING, CEREMONIES,
  STATE, MANIFESTO)
- the reproduction protocol (this file)

The new cell then specialises by editing its `MANIFESTO.md`,
adding code under its chosen language, and answering the queue's
first task: "what does this cell exist to do?"

## How to spawn a sibling cell

You need [`copier`](https://copier.readthedocs.io/) and `uv`. The
recommended invocation uses `uvx` so no global install is needed:

```bash
uvx copier copy gh:JSBaxter/stem-cell <new-cell-path>
```

Copier asks a small number of questions — name, purpose, language,
whether to include the agent container or bot identity. Answer them.
The template renders into `<new-cell-path>`.

Then, inside the new cell:

```bash
cd <new-cell-path>
git init
git add -A
git commit -m "chore(repo): initial cell from stem-cell"
```

If `language=python` was chosen, the queue is ready to run:

```bash
uv sync --directory dev-tools/queue
uv run --directory dev-tools/queue pytest
```

The new cell's agent should read `MANIFESTO.md` first, then
`CONTRIBUTING.md`, then begin work via the queue (`add_idea` →
`scope_task` → `claim_task` → `open_session`).

## How to update this cell from the template

Updates to the template (improved queue, refined doc spine, new
ceremonies) flow into existing cells via `copier update`:

```bash
uvx copier update
```

Run from this cell's repo root. Copier reads `.copier-answers.yml`
(committed when the cell was scaffolded), fetches the latest
template, re-renders against the same answers, and presents a diff.
Review carefully — the cell may have hand-edited files that copier
will want to overwrite. Resolve conflicts, then commit:

```bash
git add -A
git commit -m "chore(repo): update from stem-cell <ref>"
```

## What a cell may NOT do during reproduction

- A cell must not edit the template directly. If a pattern needs to
  change, change it in the template repo and pull updates here.
- A cell must not vendor a different queue. If the queue needs a new
  capability, add it to the template's queue, then update.
- A cell must not invent its own commit/branch convention. If the
  conventions in `CONTRIBUTING.md` are wrong for this cell, raise
  the disagreement upstream and update the template.

The point of the template is shared structure across cells. The
moment a cell forks the structure silently, the species drifts.

## Pinning and lineage

`.copier-answers.yml` records:

- The template URL/path the cell was scaffolded from
- The exact commit (or version tag) of the template at scaffold time
- Every answer given

That file is the cell's birth certificate. Keep it accurate; do not
edit it by hand. Copier rewrites it on every `copier update`, so a
git diff of that file is a clean record of which template version
this cell tracks.

## Why this lives in every cell

If a cell can read this file, it can reproduce — even if the
operator is unavailable, the original template URL has rotted, or
the cell's agent is bootstrapping itself in a fresh environment.
The cell carries its own DNA.
