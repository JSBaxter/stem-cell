# Changes

Shape notes for rendered cells. One `## vX.Y.Z` section per stem-cell
release, newest first, each with an `### Owned files` subsection: what
changed in the shape of the cell-owned files (`thresholds.yml`,
`CLAUDE.md`, `README.md`, `.gitignore`, `LICENSE`, `specs/`, `docs/adr/`), which
`copier update` never overwrites. The template sync quotes the sections
newer than a cell's current version into its sync PR under `## Shape
notes`. Write "none" when nothing changed shape.

## v2.0.0

### Owned files

`CLAUDE.md`, `README.md`, `.gitignore`, `LICENSE`, `thresholds.yml`, `specs/`
and `docs/adr/` are new or reshaped in v2 (`LICENSE` is owned so the year
written at birth is never rewritten by a sync; `README.md` carries a lineage
line, no date):

- `CLAUDE.md`: under 60 lines; purpose, ground rules, the test, lint and
  type commands, the skills an agent uses, the `cellq` and
  `thresholds.yml` rules, the cloud-session note. No longer points at
  MANIFESTO.md or CONTRIBUTING.md.
- `README.md`: purpose and the pointer to `specs/`.
- `.gitignore`: now cell-owned; the template renders it once.
- `thresholds.yml`: new; every numeric threshold a cell uses lives here.
- `specs/`: new; `specs/README.md` and the spec stub.
- `docs/adr/`: new; the ADR seed `0000-record-architecture-decisions.md`.

A cell rendered from the May template rewrites `CLAUDE.md` and
`README.md` by hand to the v2 shape after its first sync: the sync skips
them because they already exist.
