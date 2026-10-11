# Cell skeleton — implementation plan

Derived from: specs/cell-skeleton.md (approved 2026-10-11)
Status: active

## Approach

Rewrite `template/` down to the files the spec lists, taking each file's
current text from the harness's templates directory at a recorded commit,
and add three things the May template lacked: a sync caller stub, a
cell-owned-files rule, and a migration path for the May cells. The sync
itself is a reusable workflow in the harness, like the gate, so stem-cell
holds only the files that are per cell.

## Structure

| Path | Owns |
|---|---|
| `copier.yml` | Four questions; `_skip_if_exists` for cell-owned files; `_exclude` for nothing else; `_message_after_copy` naming the initialisation step |
| `template/CLAUDE.md.jinja`, `AGENTS.md.jinja`, `README.md.jinja` | Entrypoint and README, from the harness template text, purpose and name rendered |
| `template/specs/README.md`, `template/specs/{{ project_name }}.md.jinja` | Spec scaffold and stub |
| `template/docs/adr/0000-record-architecture-decisions.md` | ADR seed, verbatim from the harness |
| `template/thresholds.yml` | Verbatim from the harness template |
| `template/.github/ISSUE_TEMPLATE/request.yml` | Verbatim from the harness template |
| `template/.github/workflows/{claude-review,claude-fix,cell-scope,cell-converge,cell-ceremony}.yml.jinja` | Caller stubs; the `@<sha>` rendered from `harness_ref` |
| `template/.github/workflows/template-sync.yml.jinja` | Caller stub for the harness's reusable sync workflow, pinned by the same `harness_ref` |
| `template/renovate.json`, `.claude/settings.json`, `.claude/hooks/session-start.sh`, `CODEOWNERS.jinja`, `.gitignore` | Verbatim or lightly rendered from the harness template and chord-recommender's hook |
| `template/.copier-answers.yml.jinja` | Lineage |
| harness `.github/workflows/template-sync.yml` (reusable) | Runs `uvx copier update --defaults --conflict rej` in the cell, opens or updates one PR on a fixed branch name, posts the version comparison; never pushes to the default branch. A harness task, filed from this plan. |
| `docs/adr/` here | 0000 record decisions; 0001 one template; 0002 sync runs in the cell |

Deleted from `template/`: everything else that is there today.

## Contracts

- **`harness_ref`**: a 40-hex commit of `JSBaxter/harness`. Rendered into every stub as `@<sha> # main`. Its default in `copier.yml` is updated by a Renovate-style bump PR in stem-cell when the harness moves (stem-cell's own `renovate.json`, with a custom regex manager on `copier.yml`).
- **Cell-owned files**, never overwritten after birth: `thresholds.yml`, `CLAUDE.md`, `README.md`, `specs/**`, `docs/adr/**`. Listed under `_skip_if_exists`. A change to their template shape is described in a `CHANGES.md` fragment the sync PR body quotes.
- **Sync branch**: `template-sync`, one per cell, force-updated by each run; the PR is reused while open.
- **Sync PR body**: current template version, latest version, the list of changed paths, any `.rej` files produced, and the quoted shape notes for owned files.
- **Initialisation hand-off**: `_message_after_copy` tells the human to run the harness's initialisation (project-creation spec), which creates labels through `cellq` and opens the first issue.

## Constraints inherited

- Design 2 and 6, spec: per-cell files only; birth is the first spec merging.
- Harness ADR 0006: stubs pinned by SHA; Renovate bumps.
- Harness ADR 0007–0009: labels, Actions triggers, `cellq`.
- Cloud sessions cannot write settings or secrets: initialisation is local.
- Design never-list: no per-cell chore for James, no cross-repo credential.

## Decisions requiring an ADR

1. stem-cell is the only template; the harness templates directory and the project-template repository are retired after the first render. ADR 0001.
2. The sync runs inside the cell's own Actions, calling a harness-hosted reusable workflow, with copier on the runner; not from the harness pushing into cells. ADR 0002.

## Risks and unknowns

| Risk | Cheapest check |
|---|---|
| `copier update` from the May template to v2 may not delete the files that left, or may produce conflicts on every hand-edited file | Run the update against a scratch clone of cytometer before the migration task; `--conflict rej` keeps the PR reviewable |
| `_skip_if_exists` silently skips a new owned file on an existing cell that lacks it | The sync PR body lists skipped paths; first run on cytometer shows the behaviour |
| `uvx` absent on the runner | `astral-sh/setup-uv` step in the reusable workflow, pinned |
| Renovate's regex manager for `harness_ref` in `copier.yml` | First Renovate run after install; fallback is a weekly bump job |

## Out of scope

- The initialisation steps (harness project-creation spec).
- Retiring the harness templates directory: a harness issue filed when the first cell renders.
- The May cells other than cytometer.
