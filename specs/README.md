# Specs

Living specifications: the persistent source of truth for what stem-cell is
intended to do. Managed via the `/spec` and `/split-spec` skills.

- One file per capability area: `specs/<area>.md`
- Specs describe current intended behavior plus pending deltas, not history
  (git and `docs/adr/` hold history)
- Sub-specs created by decomposition carry a `Derived from:` line
- Acceptance criteria must be executable by an agent with no other context
- `<area>.plan.md` files are implementation plans, not specs, and are deleted
  once their work lands (`/plan`)

Start a spec with `/spec` from any Claude Code session in this repo.
