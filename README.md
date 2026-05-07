# stem-cell

A [copier](https://copier.readthedocs.io/) template for spawning
**agent cells** — repositories shaped to be operated by an autonomous
agent, with a task queue, a doc spine, and a reproduction protocol
baked in.

A cell is the atomic unit of agent organisation. Each cell is one
repository, one purpose, one queue. Cells reproduce by spawning new
cells from this template. Updates to the species flow from this
template via `copier update`.

## What a generated cell contains

Every cell, regardless of language, gets:

| Path                       | Purpose                                                |
|----------------------------|--------------------------------------------------------|
| `MANIFESTO.md`             | The cell's identity and operating principles           |
| `CONTRIBUTING.md`          | Branching, commits, queue discipline, PR rules         |
| `AGENTS.md`, `CLAUDE.md`   | Agent entrypoints — point at CONTRIBUTING + MANIFESTO  |
| `TESTING.md`               | What to test, what not to test, per-language checklists|
| `CEREMONIES.md`            | Modulo cadence rule + four ceremonies                  |
| `STATE.md`                 | Operational truth scaffold                             |
| `REPRODUCTION.md`          | How this cell was born + how to spawn a sibling        |
| `CHANGELOG.md`             | Keep-a-Changelog skeleton                              |
| `.mcp.json`                | Wires Claude Code (or any MCP client) to the in-cell queue |
| `dev-tools/queue/`         | Vendored task queue: MCP server, SQLite-backed         |

Optional, gated on copier answers:

| Path                       | When                                    |
|----------------------------|-----------------------------------------|
| `dev-tools/agent-container/` | `include_agent_container: true`       |
| `dev-tools/agent-bot/`     | `include_bot_identity: true`           |
| `pyproject.toml`, `.pre-commit-config.yaml` | `language: python`     |
| `.github/workflows/quality.yml`             | `language: python && github_remote: true` |

## Spawning a cell

```bash
uvx copier copy gh:JSBaxter/stem-cell <new-cell-path>
# or, while iterating locally:
uvx copier copy ~/Documents/repos/cells/stem-cell <new-cell-path>
```

Answer the questions; copier writes the cell. Then, inside the new
cell:

```bash
cd <new-cell-path>
git init
git add -A
git commit -m "chore(repo): initial cell from stem-cell"
```

## Updating an existing cell

From inside the cell:

```bash
uvx copier update
```

Copier reads `.copier-answers.yml` (committed at scaffold time),
re-renders against the current template version, and presents the
diff. Review, resolve, commit.

## Iterating on the template

The template's own structure:

```
stem-cell/
├── README.md              # this file
├── copier.yml             # questions, exclusions, post-copy messages
└── template/              # everything in here renders into the cell
    ├── *.jinja            # Jinja-templated files
    ├── REPRODUCTION.md    # verbatim file, identical in every cell
    └── ...
```

Conventions:

- **`.jinja` suffix** for any file with templating. Copier strips the
  suffix on render.
- **No `.jinja` suffix** for files copied verbatim.
- **`{% if %}` directory names** to gate whole directories (e.g.
  `dev-tools/agent-container{% if include_agent_container %}/`).

Smoke test before pushing template changes:

```bash
uvx copier copy --defaults --vcs-ref HEAD ~/Documents/repos/cells/stem-cell /tmp/test-cell
```

(`--defaults` accepts every default; supply real answers for anything
required.)
