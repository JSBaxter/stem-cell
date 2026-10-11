# stem-cell

Status: draft

## Purpose

stem-cell is the copier template that spawns **agent cells**: repositories
shaped to be operated by an autonomous agent with a human reviewer. One
repository, one purpose, one doc spine. Cells are individuals of a species:
they are born from this template and receive species changes through
`copier update`, so a fix made once here reaches every cell as a reviewable
diff. The template exists for James, operating a small number of cells on a
Claude Max subscription with no API billing, and for the agents that work
inside them.

## Behavior

What a cell gets today, from the template as it stands (v1, last changed
2026-05-27).

### Questions asked at spawn

- `project_name` (kebab-case), `project_purpose` (one sentence),
  `project_description` (optional paragraph).
- `operator_name`, `operator_email`.
- `language`: `python` or `none`. Python wires uv, ruff, ty, pytest and
  pre-commit.
- `include_agent_container` (default false): a Docker image for running the
  agent with bounded blast radius.
- `include_bot_identity` (default true): wrappers for a separate GitHub App
  identity so the operator is a real reviewer on agent PRs.
- `github_remote` (default true), `operator_github_handle`, and
  `colony_bot_login` for the CI allowlist.
- `license`, `copyright_holder`, `copyright_year`.

### Every cell gets

- **The doc spine**: `MANIFESTO.md` (identity and principles),
  `CONTRIBUTING.md` (canonical rules: branch and PR discipline, Conventional
  Commits, queue discipline, tooling), `AGENTS.md` and `CLAUDE.md` (agent
  entrypoints that defer to CONTRIBUTING), `TESTING.md` (what to test, what
  not to), `CEREMONIES.md` (four ceremonies on a modulo cadence anchored to
  merged-PR count), `STATE.md` (operational truth, updated in the same PR as
  any operational change), `REPRODUCTION.md` (how this cell was born, how to
  spawn a sibling, how to pull updates), `CHANGELOG.md`, `README.md`.
- **The vendored queue** under `dev-tools/queue/`: a SQLite task queue
  exposed as an MCP server, wired in by `.mcp.json`. Domain layer with
  commands for ideas, scoping, claiming, sessions, token logging, feature
  requests; infra layer with the SQLite repository; thin fastmcp server.
  CONTRIBUTING requires it for non-trivial work.
- **`.copier-answers.yml`** pinning the template version the cell was
  rendered from.

### Cells with a GitHub remote also get

- `.github/CODEOWNERS` requesting the operator's review on every PR.
- `.github/workflows/cell-build.yml`: Claude running **in GitHub Actions**,
  triggered by issue labels, comments, reviews, PR close and manual
  dispatch, restricted to the operator and the colony bot by sender
  allowlist, serialised because the queue database lives on a
  `colony/queue-state` branch.
- `.github/workflows/quality.yml` for Python cells.
- `.yamllint.yml`.

### Optional

- `dev-tools/agent-container/` when `include_agent_container`.
- `dev-tools/agent-bot/` (`mint-token.sh`, `as-bot.sh`) when
  `include_bot_identity`.
- `pyproject.toml` and `.pre-commit-config.yaml` for Python cells.

### Reproduction

`uvx copier copy gh:JSBaxter/stem-cell <path>` renders a cell;
`copier update` inside a cell pulls species changes. The template prints
next steps after copy and after update.

## Non-goals

- **The colony layer.** atlas, morphogen and colony are separate repos and
  stay parked until more than three cells are live. Nothing here depends on
  them.
- **Harness-side skills.** The queue adapter over GitHub Issues, the
  `/ceremony` procedures, the spec completeness check and the converge pass
  are changes to `JSBaxter/harness` and get their own specs there. This spec
  only requires that a cell is *shaped* to use them.
- **Checkout-free creation from a phone.** `JSBaxter/harness`
  `specs/project-creation.md` owns that problem.
- **Beads or any second task store.** GitHub Issues is the one queue.
- **Stealth identity.** A stealth cell cannot name `JSBaxter/harness`; it
  needs its own flow.
- **Replacing the review gate or the ruleset.** Cells consume them as the
  harness ships them.

## Pending changes

### v2: cells carry the harness contract (2026-10-11)

**Why.** Between May and September the harness proved a process on
chord-recommender: spec PR as the human gate, ADRs, agent review as a
required check, small PRs, cloud sessions and self-rearming routines. It has
no update path: `project-template` is copy-once, so every harness fix is
re-vendored by hand (chord-recommender's session-start hook is the
symptom). stem-cell has the update path and the doc spine but a May process.
v2 makes stem-cell the harness's project template. The harness plugin keeps
carrying procedure (skills, agents, hooks). The template carries the repo's
contract (rules, truth, cadence, gate wiring).

**Delta.**

*What changes*

1. **Spec and decision layer added.** Every cell renders `specs/README.md`,
   a `specs/<project_name>.md` stub seeded from `project_purpose` and
   `project_description` with Status: draft, and
   `docs/adr/0000-record-architecture-decisions.md`. `CLAUDE.md` and
   `AGENTS.md` gain the harness ground rules verbatim from
   `JSBaxter/harness` `templates/project/CLAUDE.md`: read the spec and ADRs
   before acting; never push to main; one issue = one PR reviewable in
   under ten minutes; finished work gets agent review, proposals carry the
   `proposal` label; definition of done lives in the issue; `/plan` before
   `/split-spec` when there is a real choice; new conventions get an ADR;
   tests, lint and type check before every PR; the cloud-sessions section.
   Where a cell rule and a harness rule overlap, CONTRIBUTING states the
   merged rule once and the entrypoints point at it.

2. **Harness wiring rendered.** `.claude/settings.json` with the
   `extraKnownMarketplaces` pointer to `JSBaxter/harness`, `enabledPlugins`
   for `jsb-harness@jsb-harness`, a `SessionStart` hook running
   `.claude/hooks/session-start.sh` and a `PreToolUse` hook running
   `.claude/hooks/pretooluse.sh`, both files rendered from the harness's
   current versions. The session-start hook installs the project's packages
   and vendors the plugin into `.claude/` so skills and guards work in cloud
   sessions, where marketplaces do not install. `.claude/skills/steward/SKILL.md`
   rendered. `.gitignore` gains `.claude/settings.local.json`,
   `.claude/worktrees/`, `.claude/agents/reviewer.md`. `.worktreeinclude`
   rendered.

3. **Review gate replaces Claude-in-CI.** `.github/workflows/claude-review.yml`
   and `claude-fix.yml` are rendered as caller stubs of the harness's
   reusable workflows. `cell-build.yml` is **removed**: the harness decision
   is no implementation work in Actions; work runs in local sessions, cloud
   sessions and routines, and the gate is the only Actions job. A new copier
   question `harness_ref` (default `main`) sets the ref on both callers so
   executable CI can be pinned per cell while skills track the marketplace
   unpinned, per harness ADR 0003.

4. **The queue leaves the cell.** `dev-tools/queue/` and the `queue` entry in
   `.mcp.json` are removed. GitHub Issues is the system of record:
   `agent-task` for work an agent may pick up, `proposal` for PRs that ask
   an opinion, `ceremony` for ceremony issues, `external` for requests from
   another cell. A rendered `.github/ISSUE_TEMPLATE/feature-request.yml`
   carries the coupling contract between cells as required fields:
   requesting cell, what is needed, acceptance criteria, deadline if any,
   priority. CONTRIBUTING's queue discipline section is rewritten for
   issues: claim by assignment, one issue per PR, definition of done in the
   issue body. The queue's domain verbs survive as a harness adapter over
   Issues and Projects (harness-side, out of scope here).

5. **Ceremonies get a deterministic trigger.** `.github/workflows/ceremonies.yml`
   runs on `pull_request: closed` when merged, counts merged PRs on the
   default branch, and for each ceremony `i` with `count mod n_i == 0` opens
   an issue titled `Ceremony <i>: <name> (PR #<count>)` labelled `ceremony`
   and `agent-task`, body linking the matching section of `CEREMONIES.md`.
   Idempotent: it never opens a second issue for the same ceremony and
   count. `CEREMONIES.md`'s catalogue is revised: 1 backlog grooming now
   includes routing unrouted issues and asking whether any spec with
   accumulated pending changes should be split; 2 health check covers
   `STATE.md` *and* `specs/` against reality, folding or deleting stale
   deltas; 3 structural review unchanged; 4 retro calibrates the
   right-sizing thresholds from diff sizes, review rounds per PR and rework
   on direct-routed changes. Who executes a ceremony issue is not fixed by
   the template: a routine, a cloud session or James.

6. **Right-sizing rule in CONTRIBUTING.** At scope time every issue gets a
   route. Work expected to touch fewer than six files and fit one session
   goes to plan mode and a PR. Anything larger, multi-session, multi-agent
   or spanning a public contract goes through `/spec`. The thresholds are
   named as starter values that ceremony 4 revises.

7. **Defaults and questions.** `include_bot_identity` default flips to
   `false`: the harness model has James merging every PR and does not need
   a second identity for review to be real. `colony_bot_login` is removed
   with `cell-build.yml`. `include_agent_container` is unchanged.
   `harness_ref` is added (see 3). `_message_after_copy` prints the admin
   steps copier cannot perform and names the exact commands: create the
   `proposal`, `agent-task`, `ceremony` and `external` labels; apply the
   ruleset from `JSBaxter/harness` `templates/ruleset.json`; enable
   delete-branch-on-merge; set `CLAUDE_CODE_OAUTH_TOKEN`.

8. **Telemetry.** The template adds no exporter configuration and no
   resource attribute. Machine-level settings own the OTLP exporter; the
   repository identity attributes Claude Code already emits give per-cell
   attribution; an experiment tag, when wanted, goes in the untracked
   `.claude/settings.local.json`. CONTRIBUTING says so in one paragraph.

*What stays*

- The doc spine and its roles: MANIFESTO for principles, CONTRIBUTING for
  rules, STATE for operational truth, TESTING, REPRODUCTION, CHANGELOG.
- The ceremony catalogue's modulo rule and starter periods.
- `language` handling, the Python toolchain, `quality.yml`, `.yamllint.yml`,
  CODEOWNERS, licensing questions, the agent container option.
- `copier update` as the only way species changes reach a cell.

*What is removed*

- `dev-tools/queue/`, the `queue` MCP server, queue discipline as a rule.
- `.github/workflows/cell-build.yml` and the `colony_bot_login` question.
- The `colony/queue-state` branch convention.

**Acceptance criteria.**

- `uvx copier copy` from this branch with default answers and
  `github_remote: true` renders a cell whose tracked files include every
  path named under *What changes* 1 to 5 and none named under *What is
  removed*. `grep -r "dev-tools/queue"` over the rendered cell returns
  nothing.
- In the rendered cell, a local Claude Code session with the harness
  marketplace available lists `jsb-harness@jsb-harness` as enabled, and
  `/spec`, `/split-spec`, `/ship` and `/adr` appear in the slash menu.
- A cloud session on the rendered cell's repository, with no marketplace
  access, runs the session-start hook and afterwards has `.claude/skills/`
  populated with the harness skills and the PreToolUse guards active.
  Verified by `ls .claude/skills` and by a blocked push to the default
  branch.
- Pushing the rendered cell to GitHub, applying the printed admin steps,
  and opening a PR produces a `claude-review` check on the PR; adding the
  `proposal` label re-runs the gate and it passes without a review.
- After the fifth merged PR on the default branch, exactly one issue
  labelled `ceremony` titled `Ceremony 1: Backlog grooming (PR #5)` exists;
  after the tenth, ceremony 1 and ceremony 2 issues both exist; re-running
  the workflow for a past merge opens nothing new.
- `CONTRIBUTING.md` in the rendered cell contains the routing rule with the
  six-file and one-session thresholds, and `CEREMONIES.md` contains the
  revised catalogue with retro's calibration input list.
- The feature-request issue template refuses submission with any required
  field empty (verified on github.com with the rendered template).
- `copier update` run inside `JSBaxter/cytometer` (a v1 cell) from this
  branch produces a diff that deletes `dev-tools/queue/`, `cell-build.yml`
  and the `.mcp.json` queue entry, adds the files under *What changes* 1 to
  5, and raises merge conflicts only in files the cell edited by hand
  (`MANIFESTO.md`, `STATE.md`, `README.md`). No conflict in any rendered
  workflow or `.claude/` file.
- A Python cell passes `uv run ruff check . && uv run ruff format --check .`,
  `uv run ty check` and `uv run pytest -q` immediately after render.
- No file in the rendered cell contains an OTLP endpoint, an
  `OTEL_` variable or a `CLAUDE_CODE_ENABLE_TELEMETRY` setting.

**Size.** This is more than one PR. After merge, `/split-spec` should
decompose it; the natural cuts are 1 and 2 (contract and wiring), 3 and 7
(gate and questions), 4 (queue removal and issue template), 5 and 6
(ceremonies and routing), then the cytometer update as the proving run.

Linked issues: none yet. Filed by `/split-spec` after this spec merges.

## Decisions

Decisions already recorded in the harness that this spec builds on:

- `JSBaxter/harness` `docs/adr/0002-no-spec-kit-add-plan-phase.md`: living
  specs with deltas, not per-feature pipelines.
- `JSBaxter/harness` `docs/adr/0003-harness-distribution-pinning.md`: skills
  auto-update, executable CI is versioned. `harness_ref` is this principle
  applied to a cell.
- `JSBaxter/harness` `docs/adr/0005-reviewer-delivered-from-harness.md`: the
  reviewer agent is delivered by the gate at run time, never vendored, hence
  the `.gitignore` entry.

Decisions this change introduces, to be recorded with `/adr` in this repo
when the spec merges:

- 0001: GitHub Issues replaces the vendored queue; coupling between cells is
  the issue template's required fields.
- 0002: No implementation work in Actions; `cell-build.yml` retired in
  favour of cloud sessions and routines, the gate is the only Actions job.
- 0003: Ceremonies are triggered by a stateless Action and executed by
  whoever takes the issue; procedure lives in the harness.
- 0004: The template owns the repo contract, the plugin owns procedure;
  telemetry configuration belongs to neither.

Research behind the change: `infra-experiment-notes`
`experiments/2026-10-stem-cell-v2.md` and
`research/2026-10-spec-driven-development.md`.
