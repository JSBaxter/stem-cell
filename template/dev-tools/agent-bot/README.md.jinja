# `dev-tools/agent-bot/`

Tooling for a **separate GitHub App identity** the cell's agent uses
to author commits and PRs — so the operator account remains a real
reviewer (GitHub disallows self-review on PRs and Environment
gates).

This directory holds the scripts. The credentials they read live in
`.agent-bot/` at the repo root by default (gitignored, `0700`):

- `private-key.pem` (`0600`) — the App's RSA private key, used to
  sign JWTs for installation-token minting.
- `app.env` (`0600`) — `app_id`, `installation_id`, `bot_user_id`,
  `bot_email`, etc. Sourced by both scripts.

To re-point the scripts at credentials in a different location, set
`AGENT_BOT_CRED_DIR=/path/to/dir` in the environment.

### Colony-shared bot pattern (recommended)

If you're using **one GitHub App across all cells in a colony** (the
common case for solo dev or small teams), put the credentials in a
single user-level location and have every cell read from there:

```bash
# One-time, on the operator workstation:
mkdir -p ~/.config/colony-bot && chmod 700 ~/.config/colony-bot
mv ~/Downloads/<app>.<date>.private-key.pem \
   ~/.config/colony-bot/private-key.pem
chmod 600 ~/.config/colony-bot/private-key.pem
# Write app.env with app_id, installation_id, bot_user_id, etc.
chmod 600 ~/.config/colony-bot/app.env
```

Then in each cell's shell environment (or via `direnv`):

```bash
export AGENT_BOT_CRED_DIR=~/.config/colony-bot/
```

Per-cell `.agent-bot/` directories aren't needed in this mode — the
scripts find everything in the shared location.

## Scripts

### `mint-token.sh`

Mints a short-lived (~1h) installation token via JWT signed with the
private key, prints it to stdout. Standalone helper; useful for
ad-hoc API probes.

```bash
TOK=$(dev-tools/agent-bot/mint-token.sh)
GH_TOKEN=$TOK gh api /repos/<owner>/<repo> --jq .name
```

### `as-bot.sh`

The everyday wrapper. Mints a fresh token, exports `GH_TOKEN`, sets
`GIT_AUTHOR_*` / `GIT_COMMITTER_*` to the bot identity, and runs the
command you pass in. For `git`, also threads the token into an
`http.extraheader` so `git push` works without configuring a global
credential helper.

```bash
# Open a PR as the bot:
dev-tools/agent-bot/as-bot.sh gh pr create --fill

# Push a branch as the bot:
dev-tools/agent-bot/as-bot.sh git push -u origin feat/something

# Make a commit attributed to the bot:
dev-tools/agent-bot/as-bot.sh git commit -m 'feat(repo): something'
```

Operator pushes outside the wrapper keep using their normal auth —
the wrapper is opt-in per-invocation, never written into `git
config`.

## Setup runbook

This is a one-time setup on a new cell. The same App can be reused
across multiple cells if you install it on each repo.

### Phase 1 — create the App

In the browser, at <https://github.com/settings/apps>:

1. **New GitHub App.**
2. Permissions:
   - `Contents`: read/write
   - `Pull requests`: read/write
   - `Workflows`: read/write
   - `Metadata`: read-only
3. **Disable webhooks.**
4. **Generate a private key** (download the `.pem`).

### Phase 2 — install on this cell's repo

In the browser, install the App on this cell's repository only.

### Phase 3 — drop credentials in place

```bash
mkdir -p .agent-bot && chmod 700 .agent-bot
mv ~/Downloads/<app-name>.<date>.private-key.pem .agent-bot/private-key.pem
chmod 600 .agent-bot/private-key.pem
cat <<EOF > .agent-bot/app.env
app_id=<app-id>
client_id=<client-id>
installation_id=<installation-id>
bot_user_id=<id-from /users/<slug>%5Bbot%5D>
bot_login=<slug>[bot]
bot_name=<slug>[bot]
bot_email=<bot_user_id>+<slug>[bot]@users.noreply.github.com
EOF
chmod 600 .agent-bot/app.env
```

`<slug>` is the App's slug (visible at
<https://github.com/settings/apps>). The bot user-id is fetched once
via `/users/<slug>%5Bbot%5D` against an installation token:

```bash
TOK=$(dev-tools/agent-bot/mint-token.sh)
GH_TOKEN=$TOK gh api /users/<slug>%5Bbot%5D --jq .id
```

`.agent-bot/` is gitignored — credentials live on operator
workstations and trusted runners only.

## Threat model + rotation

Trust boundary is the operator's workstation (or any container that
mounts `.agent-bot/`). Compromise of the private key gives the
attacker arbitrary access to the repo within the App's permission
scope until the key is rotated.

To rotate:

1. Generate a new private key on the App settings page.
2. Replace `.agent-bot/private-key.pem` with the new file.
3. Delete the old key on the App settings page once the new one is
   confirmed working.

The `client_secret` in `app.env` (if present) is unused — we
authenticate server-to-server with the private key, not via OAuth.
GitHub doesn't allow deleting the only client secret, so it sits
there safely.
