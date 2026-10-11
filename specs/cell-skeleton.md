# Cell skeleton

Status: draft

Derived from: the cell operating model, infra-experiment-notes
`design/cell-operating-model.md` (2026-10-11), sections 1, 2, 6 and the
appendix; and the harness spec `specs/cell-operation.md`, which names the
skills, the thresholds file and the request form a cell carries.

## Purpose

stem-cell is the only template (**decided** 2026-10-11: "stem cell only").
It renders the files that are per cell and nothing shared, and it keeps
every rendered cell current by opening a pull request in the cell when the
template changes. Shared procedure lives in the harness as skills,
workflows and the reviewer; a cell reaches them by name and by pinned
reference, never by copy.

The harness's own templates directory and the project-template repository
on GitHub are retired once the first cell renders from this template.

## Behavior

### What a rendered cell contains

| Path | Content | Per cell because |
|---|---|---|
| `CLAUDE.md` | Under 60 lines: the purpose paragraph; the ground rules; the test, lint and type commands; the skills an agent uses and when; the rule that issue state goes through `cellq`; the rule that every threshold comes from `thresholds.yml`; the cloud-session note. Starts from the harness template's current text. | commands and purpose differ per cell |
| `AGENTS.md` | One line importing `CLAUDE.md`, for agents that read that name | |
| `README.md` | Purpose, the pointer to `specs/`, the creation date | |
| `specs/README.md`, `specs/<purpose-slug>.md` | The spec stub: Purpose from the copier answer, every other section empty | the first spec PR fills it |
| `docs/adr/0000-record-architecture-decisions.md` | The ADR seed | |
| `thresholds.yml` | The starter values, as the harness template holds them | revised per cell by the retro |
| `.github/ISSUE_TEMPLATE/request.yml` | The cross-cell request form | |
| `.github/workflows/claude-review.yml`, `claude-fix.yml`, `cell-scope.yml`, `cell-converge.yml`, `cell-ceremony.yml` | Caller stubs, each pinned to the harness commit recorded in the template | the pin is per cell and Renovate bumps it |
| `.github/workflows/template-sync.yml` | The scheduled sync caller (below) | |
| `renovate.json` | Extends the harness preset | |
| `.claude/settings.json` | The marketplace pointer to the harness plugin | |
| `.claude/hooks/session-start.sh` and its settings entry | Copies the harness plugin into a cloud session, since marketplaces do not install there | |
| `CODEOWNERS` | Requests James's review on every PR | |
| `.gitignore` | | |
| `.copier-answers.yml` | Lineage: template version and every answer | |

Language toolchain files (`pyproject.toml`, lint config, a quality
workflow) are not rendered. A cell that chooses a language runs the
harness's setup skill for it as its first task after birth.

### What leaves the template

MANIFESTO, CONTRIBUTING, TESTING, CEREMONIES, REPRODUCTION, CHANGELOG, the
vendored queue and its MCP wiring, the cell-build workflow, the agent
container, the bot-identity wrappers, the Python quality workflow and the
pre-commit config. Their surviving content is in harness skills; the rest
is dropped as decided in step 0 of the design.

### Copier questions

| Question | Used for |
|---|---|
| `project_name` | directory, README, spec slug |
| `project_purpose` | README, `CLAUDE.md`, the spec stub's Purpose |
| `operator_github_handle` | `CODEOWNERS` |
| `harness_ref` | the commit the five caller stubs pin to; default: the value recorded in the template at its last sync with the harness |

No other question. Language, container, bot identity, licence and remote
are gone or defaulted (MIT licence rendered; a remote is assumed).

### Birth

1. Rendering produces the files above. Nothing else happens inside copier.
2. The one-time initialisation (the harness's project-creation spec: labels, settings, ruleset, the OAuth secret) runs next, from a local session; it creates every `state:`, `route:`, `source:` and `priority:` label through `cellq`, so the request form's default label exists before the first issue.
3. Initialisation opens the first issue, "write the first spec", through `cellq idea`. The cell is born when that spec PR merges (design 6.1).

### Keeping cells current

| Mechanism | Behaviour |
|---|---|
| Scheduled sync | `template-sync.yml` in each cell runs on a schedule, calls the harness-hosted reusable sync workflow pinned by SHA, which runs `copier update` against the template version recorded in `.copier-answers.yml` and opens one PR per cell when anything changed. It never pushes to the default branch. A conflict copier cannot resolve makes the PR fail visibly with the conflict markers in the diff. |
| Drift check | The same run reports, in the PR body or a comment, which template version the cell is on and which is current. A cell behind by more than one template release is listed by the harness's fixture run. |
| Pin bumps | Renovate bumps the five caller stubs' SHA; the template records the SHA it was last synced to in `harness_ref`'s default. |
| Owned files | `thresholds.yml`, `CLAUDE.md`'s purpose and commands, `specs/`, `docs/adr/` are owned by the cell: copier never overwrites them after birth (`_skip_if_exists`). Template changes to their shape arrive as a note in the sync PR body, not as a diff. |

### Migration of a May cell

A cell rendered from the May template takes the v2 template through one
sync PR: the files that leave are deleted, the files that arrive are
added, and the cell's own content is kept. cytometer is the first
migration and the test of the mechanism.

## Acceptance criteria

- `copier copy --defaults` with a name and purpose renders exactly the paths in the table above and no other; the rendered `CLAUDE.md` is under 60 lines; no rendered file contains a numeric threshold other than `thresholds.yml`.
- The five rendered caller stubs each contain `@<40-hex-sha> # main` where the SHA equals `harness_ref`.
- After initialisation on a rendered cell, `gh label list` shows every `state:`, `route:`, `source:` and `priority:` label, and exactly one open issue exists, titled "write the first spec", in `state:new`.
- A change to a template-owned file (for example the ADR seed) followed by the scheduled sync run on a rendered cell yields one open PR in that cell whose diff touches only that file; a change to the shape of `thresholds.yml` yields no diff to the cell's file and a note in the PR body.
- Running the sync against cytometer yields one PR whose diff deletes MANIFESTO.md, CONTRIBUTING.md, TESTING.md, CEREMONIES.md, REPRODUCTION.md, CHANGELOG.md and `dev-tools/queue/`, adds the paths in the table, and leaves `src/` untouched.
- `uvx copier copy` of the template at HEAD into a temporary directory succeeds with `--defaults`, as the smoke test the README already names.

## Non-goals

- The harness skills, workflows and reviewer (harness `specs/cell-operation.md`).
- The one-time initialisation steps themselves (harness `specs/project-creation.md`); this spec only says when they run and what they create.
- Language toolchains; the setup skills carry them.
- Bot identity, the agent container, the colony services.
- Retiring the harness's templates directory: a harness task filed when the first cell renders from here.

## Constraints

- No API billing; everything runs on the Max subscription.
- Agents never merge; the sync PR, like every PR, is James's to merge.
- The sync must run where a cell's workflows run (Actions) and must not need a credential beyond the cell's own token and the OAuth secret the gate already has; it reads the template from a public or user-accessible repository.
- Cloud sessions cannot write repository settings or secrets, so initialisation stays local (harness cloud-capabilities matrix).

## Open questions

1. Whether the sync runs copier inside the cell's Actions runner (needs `uvx copier` on the runner; simple) or in the harness fixture job which then pushes a branch to each cell (needs a cross-repo token; ruled out by the design's never-list). Default: inside the cell.
2. The sync schedule. Default: weekly, plus `workflow_dispatch`.
3. Whether `AGENTS.md` is rendered at all, given Claude Code reads `CLAUDE.md`. Default: yes, one line, for other agents.

## Pending changes

None. This spec is new; its Behavior is the intended contract and the
acceptance criteria above are what the implementing tasks are cut from.

Linked issue: #14

## Decisions

- stem-cell is the only template (James, 2026-10-11). The harness ADR for the retirement of its templates directory is filed with the first render.
- harness ADR 0006: caller stubs pin to a SHA; Renovate bumps.
- harness ADR 0007, 0008, 0009: labels for state, Actions workflows as triggers, `cellq` as the adapter; the skeleton carries their per-cell ends.
