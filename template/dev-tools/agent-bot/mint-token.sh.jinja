#!/usr/bin/env bash
# Mint a GitHub App installation access token.
#
# Reads app.env (app_id, installation_id) and private-key.pem from
# AGENT_BOT_CRED_DIR (default: <repo-root>/.agent-bot/). Outputs the
# token to stdout. Tokens are short-lived (~1h, GitHub-issued).
#
# No external deps beyond openssl, curl, jq — all standard.
set -euo pipefail

repo_root() {
    git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel
}

CRED_DIR="${AGENT_BOT_CRED_DIR:-$(repo_root)/.agent-bot}"
# shellcheck source=/dev/null
. "$CRED_DIR/app.env"

now=$(date +%s)
exp=$((now + 540))   # 9 min — GitHub max is 10
header_b64=$(printf '{"alg":"RS256","typ":"JWT"}' \
    | openssl base64 -A | tr '+/' '-_' | tr -d '=')
payload_b64=$(printf '{"iat":%d,"exp":%d,"iss":%d}' "$now" "$exp" "$app_id" \
    | openssl base64 -A | tr '+/' '-_' | tr -d '=')
signing_input="$header_b64.$payload_b64"
sig_b64=$(printf '%s' "$signing_input" \
    | openssl dgst -sha256 -sign "$CRED_DIR/private-key.pem" -binary \
    | openssl base64 -A | tr '+/' '-_' | tr -d '=')
jwt="$signing_input.$sig_b64"

curl -sS -X POST \
    -H "Authorization: Bearer $jwt" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/app/installations/${installation_id}/access_tokens" \
    | jq -er .token
