# stem-cell

The [copier](https://copier.readthedocs.io/) template for **cells**:
repositories operated by agents under the cell operating model. It is the
only template ([ADR 0001](docs/adr/0001-one-template.md)). It renders the
files that are *per cell* and nothing shared; shared procedure (skills,
reusable workflows, the reviewer) lives in
[`JSBaxter/harness`](https://github.com/JSBaxter/harness), and a cell
reaches it by name and by pinned commit, never by copy.

The template also keeps every rendered cell current: a weekly workflow in
each cell runs `copier update` and opens a pull request when the template
has changed ([ADR 0002](docs/adr/0002-sync-runs-in-the-cell.md)).

Intent lives in [`specs/`](specs/) (`cell-skeleton.md` is the contract this
README summarises); decisions live in [`docs/adr/`](docs/adr/).

## What a rendered cell contains

| Path | Purpose |
|---|---|
| `CLAUDE.md` | The agent entrypoint, under 60 lines: purpose, ground rules, the test, lint and type commands, the skills an agent uses, the `cellq` and `thresholds.yml` rules, the cloud-session note |
| `AGENTS.md` | One line importing `CLAUDE.md`, for agents that read that name |
| `README.md` | Purpose, the pointer to `specs/`, the lineage line naming this template |
| `LICENSE` | MIT, held by `operator_github_handle`; the year is a literal in `template/LICENSE.jinja`, and the file is cell-owned so a sync never rewrites it |
| `specs/README.md` | How specs work in the cell: one file per capability area, `/spec` to start one |
| `specs/<project_name>.md` | The spec stub: Purpose from the copier answer, every other section empty; the first spec PR fills it |
| `docs/adr/0000-record-architecture-decisions.md` | The ADR seed |
| `thresholds.yml` | Every numeric threshold the cell uses; starter values, revised per cell by the retro |
| `.github/CODEOWNERS` | Requests the operator's review on every PR |
| `.github/ISSUE_TEMPLATE/request.yml` | The cross-cell request form |
| `.github/workflows/claude-review.yml` | Caller stub, pinned to `harness_ref`: the review gate on every PR |
| `.github/workflows/claude-fix.yml` | Caller stub, pinned to `harness_ref`: the human-feedback round on a PR comment |
| `.github/workflows/cell-scope.yml` | Caller stub, pinned to `harness_ref`: runs the `scope` skill when an issue opens |
| `.github/workflows/cell-converge.yml` | Caller stub, pinned to `harness_ref`: runs the `converge` skill on a parent once its sub-issues close |
| `.github/workflows/cell-ceremony.yml` | Caller stub, pinned to `harness_ref`: on merge, marks closed issues done through `cellq` and files ceremony issues by the periods in `thresholds.yml` |
| `.github/workflows/template-sync.yml` | Caller stub, pinned to `harness_ref`: the weekly template sync (see "Keeping cells current") |
| `renovate.json` | Extends the harness Renovate preset, which bumps the stubs' pins |
| `.claude/settings.json` | The marketplace pointer to the harness plugin and the session-start hook entry |
| `.claude/hooks/session-start.sh` | Copies the harness plugin into a cloud session, where marketplaces do not install |
| `.gitignore` | Rendered once; cell-owned from then on |
| `.copier-answers.yml` | Lineage: the template version the cell is on and every answer; `copier update` reads it |

Nothing else is rendered. Toolchain files (`pyproject.toml`, lint config, a
quality workflow) are not part of the template: a cell runs the harness
setup skill for its toolchain (for example `python-setup`) as its first
task after birth.

## The questions

Copier asks exactly four questions.

| Question | Feeds |
|---|---|
| `project_name` | the heading of `README.md`, `CLAUDE.md` and `AGENTS.md`, the spec slug `specs/<project_name>.md` (the destination directory is the `<path>` argument, not the answer) |
| `project_purpose` | `README.md`, `CLAUDE.md`, the spec stub's Purpose |
| `operator_github_handle` | `.github/CODEOWNERS`, the `LICENSE` holder; default `JSBaxter` |
| `harness_ref` | the `JSBaxter/harness` commit the six workflow stubs pin to, rendered as `@<sha> # main`; default: the harness commit recorded in `copier.yml` |

There is no creation-date question; git history carries the date.

## Rendering a cell

```bash
uvx copier copy gh:JSBaxter/stem-cell <path>
```

With no `--vcs-ref`, copier renders the **latest tag**, and
`.copier-answers.yml` records that tag as the cell's template version.
Render real cells this way, never from an untagged commit: a cell rendered
past the latest tag records a version like `v2.0.0-3-g1a2b3c4`, and its
first sync, which targets the latest tag, refuses with "Downgrades are not
supported" until a newer tag exists. When the template has no tag at all,
copier only warns ("No git tags found in template; using HEAD as ref") and
records a bare commit, which the sync cannot update from either. So a tag
must exist before the first real render; see "Releases".

## Birth

1. **Render.** The command above. Copier writes the files in the table and
   nothing else happens inside copier.
2. **Commit.** Inside the new cell:

   ```bash
   cd <path>
   git init && git add -A && git commit -m "chore(repo): initial cell from stem-cell"
   ```

3. **Push.** Create the GitHub repository and push the default branch.
4. **Initialise, locally.** Run the harness's one-time initialisation
   (harness `specs/project-creation.md`) from a local session: it needs
   repository settings and secrets that a cloud session cannot write. It
   applies the branch ruleset and the OAuth secret and creates every
   `state:`, `route:`, `source:` and `priority:` label through `cellq`, so
   the request form's default label exists before the first issue.
5. **First issue.** Initialisation opens "write the first spec" through
   `cellq idea`. The cell is born when that spec PR merges.

## Keeping cells current

| Mechanism | Behaviour |
|---|---|
| Scheduled sync | `.github/workflows/template-sync.yml` runs weekly (and on `workflow_dispatch`) in each cell. It calls the harness-hosted reusable sync workflow, pinned by SHA, which runs `uvx copier update --defaults --conflict rej` against the template version in `.copier-answers.yml`. When anything changed it pushes the branch `template-sync` (one per cell, force-updated each run) and opens one PR, reused while open. It never pushes to the default branch. |
| Conflicts | A change copier cannot merge lands as a `.rej` file in the PR diff, listed under `## Conflicts` in the PR body, and the run fails after opening the PR: visible, never silent. |
| Owned files | `thresholds.yml`, `CLAUDE.md`, `README.md`, `.gitignore`, `LICENSE`, `specs/`, `docs/adr/` belong to the cell. They are rendered once and `copier update` never overwrites them (`_skip_if_exists` in `copier.yml`). |
| Shape notes | A template change to the shape of an owned file is described in [`CHANGES.md`](CHANGES.md), not applied. The sync PR quotes every `CHANGES.md` section newer than the cell's version under `## Shape notes`; the cell applies what matters by hand. |
| Pin bumps | Renovate bumps the six workflow stubs' SHA in each cell, and bumps the `harness_ref` default in this repository's `copier.yml` so new cells start on the current harness. |

The sync PR body has these sections, in order: `## Template version`,
`## Changed paths`, `## Conflicts`, `## Owned files not touched`,
`## Shape notes`.

## Releases

- Releases are git tags named `vMAJOR.MINOR.PATCH`.
- `copier update` targets the latest tag, so a template change reaches
  cells only once it is tagged. Tag before the first real render (see
  "Rendering a cell").
- `CHANGES.md` has one `## vX.Y.Z` section per tag, newest first, each with
  an `### Owned files` subsection: what changed in the shape of the owned
  files, or "none".

## Iterating on the template

```
stem-cell/
├── README.md       # this file
├── CHANGES.md      # shape notes per release; quoted into sync PRs, not rendered
├── copier.yml      # the four questions, _skip_if_exists, post-copy messages
├── renovate.json   # bumps the harness_ref default in copier.yml; not rendered
├── specs/          # the cell-skeleton spec
├── docs/adr/       # decisions
└── template/       # everything in here renders into the cell
```

Conventions:

- A file whose content uses Jinja carries the **`.jinja` suffix**; copier
  strips it on render (`CLAUDE.md.jinja` becomes `CLAUDE.md`). A file
  without the suffix is copied verbatim.
- A path can use an answer: `specs/{{ project_name }}.md.jinja`.
- A file that the cell owns after birth is listed in **`_skip_if_exists`**
  in `copier.yml`, as a block list (the sync parser reads it that way).
  Adding a rendered file that cells should edit means adding it there and
  describing the shape in `CHANGES.md`.
- A change that alters the shape of an owned file gets a line under the
  next release's `### Owned files` in `CHANGES.md`.

Smoke test before pushing a template change, from the repository root:

```bash
uvx copier copy --defaults --vcs-ref HEAD . /tmp/test-cell -d project_name=test-cell -d project_purpose="smoke test"
```

`--vcs-ref HEAD` renders the working tree, uncommitted edits included,
instead of the latest tag; `--defaults` accepts every default, and the
`-d` flags supply the two answers that have none. The rendered paths must
be exactly those in the table above.
