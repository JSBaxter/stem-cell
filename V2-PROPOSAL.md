# Proposal: the next iteration of the agent harness

Written 2026-10-11. For James to review and decide. Needs no memory of the
earlier projects; everything relevant is restated here. Merging this PR means
"build this, in the phases listed, decisions as marked".

## 1. What we are trying to build

A way of running software projects where agents do the implementation and
James does the steering and the approving, on a Claude Max subscription with
no API billing, that still works after James has ignored it for three
months. The last clause is the hard one and the one both previous attempts
underweighted.

## 2. The two previous attempts, in one paragraph each

**stem-cell (May 2026).** A copier template that stamped out "cells": one
repo, one purpose, each with nine process documents (manifesto,
contributing, testing, state, ceremonies, reproduction, changelog, two agent
entrypoints), a SQLite task queue vendored into the repo as an MCP server, a
GitHub Actions workflow that ran Claude *inside CI* to do the work, an
optional bot identity so agent PRs had a separate author, and a modulo rule
that fired "ceremonies" (grooming, health check, structural review, retro)
every N merged PRs. Four cells were built in three weeks and then work took
over. The good ideas: `copier update` pushes template fixes into every cell
as a reviewable diff; `STATE.md` as operational truth; the ceremony cadence;
the one-repo-one-purpose boundary. The problems: too much machinery per
repo, a queue that duplicated GitHub Issues, implementation running in
Actions where it is slow and opaque, and nothing that helped re-entry.

**harness (August to September 2026).** A Claude Code plugin carrying skills
(spec, split-spec, dispatch, ship, adr) and a reusable GitHub Actions review
gate, plus a copy-once project template. It ran a real project,
chord-recommender, to roughly sixty merged PRs and sixteen architecture
decision records in twelve days, with cloud sessions and self-rearming
overnight routines stewarding PRs against the gate. The good ideas: the spec
PR as the only human gate; ADRs; a fresh-context reviewer as a required
check; one issue = one PR under ten minutes to review; "proposal" PRs that
skip the agent reviewer; the steward posture that stops agents grinding on
advisory findings. The problems: no update path (every fix to the harness
had to be hand-copied into each project; chord-recommender has a 100-line
hook doing exactly that for cloud sessions); the roadmap file went stale
within weeks while reality moved on; two spec deltas were never folded back
after shipping; the sizing rule lived in an agent's head; nothing measured
cost, review rounds, or James's time; and the harness repo gates every
project's PRs but not its own.

**What the research added (October 2026).** A literature review of the
public spec-driven frameworks found: spec completeness predicts outcomes
more than framework choice; specs pay off on multi-session, multi-file work
and are overhead on small changes; drift after implementation is universal
and the two leading tools both added a "converge" step this year; context
bloat is the hidden cost and the fix is moving reusable guidance into
skills. No one has data on a living spec over months, which is our whole bet.

## 3. The design

Five rules. Each one answers a failure above.

**R1. One template renders everything a repo needs, and copier is the only
way changes reach it.** No copy-once template, no hand-vendoring. A fix made
in the template lands in every repo as a PR via `copier update`. *(Fixes:
harness's no-update-path; stem-cell already did this, we keep it.)*

**R2. GitHub Issues is the one queue.** No vendored task store. An issue is
scoped, routed, claimed by assignment, and closed by its PR. Requests
between repos are an issue template with required fields, which is how
tightly repos are coupled: change the fields, change the coupling.
*(Fixes: stem-cell's duplicate queue; keeps its "coupling knob" idea.)*

**R3. Procedure lives in the plugin, contract lives in the repo, nothing in
both.** Skills say *how* (spec, plan, split, ship, review, ceremony,
converge). The repo says *what is true here* (purpose, rules, state,
specs, decisions). A repo's agent entrypoint is short and points at skills.
*(Fixes: context bloat; stem-cell's nine-document spine shrinks to five.)*

**R4. The human gate is one action: merge.** Specs, decisions, proposals and
code all route through a PR that James merges. Nothing else asks for
approval. Agents never merge. *(Keeps harness's proven gate; removes
stem-cell's bot identity by default because the author of a PR does not
matter when the merger is always James.)*

**R5. The process measures itself and adjusts on a cadence.** Every session
exports token, model and attribution telemetry to a local collector (done
today, in the notes repo). The retro ceremony reads it, plus review rounds
per PR and PR sizes, and changes the thresholds. Deterministic triggers,
agent judgement inside, human merge. *(Fixes: harness measured nothing;
stem-cell's ceremonies had no trigger that fired without someone
remembering.)*

### 3.1 What a repo contains after rendering

| Path | Role | From |
|---|---|---|
| `README.md` | purpose, one paragraph, and the directory map | stem-cell manifesto, shortened |
| `CONTRIBUTING.md` | the rules: branch, commits, one issue one PR, routing rule, labels | both, merged, one copy |
| `STATE.md` | operational truth: what is running, where, depends on | stem-cell |
| `CEREMONIES.md` | the catalogue, cadence, and inputs for each ceremony | stem-cell, revised |
| `CLAUDE.md`, `AGENTS.md` | ten lines: read CONTRIBUTING, STATE, the spec; run skills for everything else | harness, cut down |
| `specs/` | living specs with pending deltas; one stub seeded at spawn | harness |
| `docs/adr/` | decisions, MADR format | harness |
| `.claude/settings.json` | plugin marketplace pointer, hooks | harness |
| `.claude/hooks/` | session-start (installs deps, vendors the plugin for cloud sessions), PreToolUse guards | harness, rendered not copied |
| `.github/workflows/claude-review.yml`, `claude-fix.yml` | caller stubs for the harness's reusable gate, pinned by a template answer | harness |
| `.github/workflows/ceremonies.yml` | on merged PR: count, modulo, open a `ceremony` issue | new |
| `.github/ISSUE_TEMPLATE/feature-request.yml` | the cross-repo coupling contract | new, from stem-cell's queue verb |
| `.copier-answers.yml` | which template version this repo is | stem-cell |

Gone from stem-cell: the queue, Claude-in-CI, the testing and reproduction
documents (their content moves into CONTRIBUTING and the template README),
the changelog (git and ADRs hold history), bot identity by default.

### 3.2 What the plugin contains

Existing and kept: spec, plan, split-spec, dispatch, ship, adr, the
reviewer agent, the steward skill, the push and identity guards.

New:

- **scope**: applied when an issue is picked up. Routes it: under six files
  and one session, plan mode then a PR; otherwise `/spec`. Writes the route
  on the issue. The thresholds are read from CONTRIBUTING so retro can
  change them.
- **converge**: after a PR merges against a spec delta, a fresh-context
  check of the merged diff against the delta's acceptance criteria; folds
  the delta into the spec body or files an issue saying why not. *(Fixes:
  the two unfolded deltas.)*
- **ceremony**: the procedures for grooming (route unrouted issues, ask
  whether any spec with piled-up deltas should split), health check
  (STATE and specs against reality; fold or delete stale text), structural
  review, retro (read telemetry and PR data, propose threshold changes as a
  PR to CONTRIBUTING).
- **queue verbs**: idea, scope, claim, complete, request-feature, as a thin
  layer over Issues and Projects so an agent's interface is stable if the
  backend changes.

### 3.3 Where work runs

Local sessions are primary. Cloud sessions and routines steward PRs,
execute ceremony issues, and do work James starts from a phone. Actions runs
only the review gate and the ceremony trigger. Nothing implements in
Actions. *(This is the harness decision; stem-cell had it the other way
round and it was the single most expensive part of that design.)*

## 4. What is genuinely new

Not in either previous attempt: the update path carrying the gate and hooks
(R1 applied to R4); issues with a coupling contract (R2); the scope skill and
its written thresholds; the converge skill; the ceremony trigger as a
stateless Action; telemetry feeding the retro; the harness gating its own
PRs; a template that renders hooks instead of a hook that copies a plugin.

## 5. Decisions James needs to make

Marked with my recommendation. Change any of them in the PR review.

- **D1. Where the template lives.** Recommend: stem-cell, in place. It has
  the copier machinery and the history. Alternative: a new repo named for
  what it is, e.g. `cell`, with stem-cell archived. Either is fine; in-place
  is less work.
- **D2. Bot identity.** Recommend: off by default, available as an option.
  Only matters if someone other than James ever needs to see agent PRs as
  separately authored.
- **D3. Ceremony executor.** Recommend: a ceremony issue is picked up by
  whoever is around: a routine if one is watching, else James's next local
  session. No default executor is wired in phase one.
- **D4. Pinning.** Recommend: skills follow the marketplace unpinned; the
  gate workflows are pinned to a tag chosen at render time. This is the
  harness's existing decision applied to cells.
- **D5. First proving project.** Recommend: the AWS research-compute repo
  for the startup. It needs a spec anyway and has real consequences.

## 6. Phases

Each phase is one or a few PRs, and each leaves something usable.

1. **Minimum cell.** Template renders the table in 3.1 minus ceremonies and
   the issue template. Spawn the proving project from it. Exit: a PR in that
   repo is gated and merges.
2. **Issues as the queue.** Labels, the feature-request template, CONTRIBUTING
   rewritten for issues, the scope skill. Exit: an issue routed, built,
   merged, closed by its PR.
3. **Cadence.** The ceremonies Action and the ceremony skill. Exit: the fifth
   merge opens a grooming issue and an agent completes it.
4. **Closing the loop.** converge, retro reading telemetry. Exit: a delta
   folded automatically; a retro PR proposing a threshold change.
5. **Update path proven.** `copier update` on one of the May cells
   (cytometer) with a clean diff. Exit: the diff merges.

Not in scope: the cross-repo coordination layer from May (atlas, morphogen),
until more than three repos are live and coordination is the bottleneck.

## 7. How we will know it worked

Six months from now, James returns after a gap. He reads STATE.md and the
spec of one repo and knows where it is. Ceremony issues from the gap are
waiting, not forgotten. A template fix he makes reaches every repo as PRs he
can merge from his phone. The retro has changed a threshold at least once
based on data. The telemetry shows what the whole thing cost.
