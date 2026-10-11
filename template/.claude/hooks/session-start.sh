#!/usr/bin/env bash
# SessionStart hook: vendor the jsb-harness plugin into .claude/ when the
# plugin is absent.
#
# Marketplaces do not install plugins in cloud sessions (claude.ai/code), so
# the harness's skills (/ship, /adr, /spec, ...) and its agents would be
# inert there — see CLAUDE.md "Cloud sessions". Repo-local .claude/ *is*
# loaded, so copying the plugin's skills/ and agents/ into this repo's
# gitignored .claude/ makes them work again.
#
# This is a workaround, not the design: the plugin stays canonical in
# JSBaxter/harness, and nothing vendored here is ever committed (.gitignore).
# Locally, where the plugin is installed from the marketplace, this hook does
# nothing, so the installed plugin and a vendored copy never both load.
#
# Derived from chord-recommender's .claude/hooks/session-start.sh (commit
# c53d5f1b2f5e488790e1b4c5c497c8aa87ff2f52), minus that repo's package
# install and PreToolUse guard sections.
set -euo pipefail

# Claude Code sets CLAUDE_PROJECT_DIR; the fallback (this file lives at
# .claude/hooks/) needs no repository, so the hook also runs in a freshly
# rendered dir that is not initialised yet.
root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
plugin_rel="plugins/jsb-harness"

# --- installed plugin? ------------------------------------------------------
# A marketplace install lands under ~/.claude/plugins/cache/<marketplace>/
# <plugin>/<version>; depth 1 is only the marketplace, so look at depth 2.
# If the plugin is installed, Claude Code loads it and a vendored copy would
# only duplicate every skill and agent. Nothing to do.
plugins_cache="$HOME/.claude/plugins/cache"
if [ -d "$plugins_cache" ] \
   && [ -n "$(find "$plugins_cache" -mindepth 2 -maxdepth 2 -type d -name jsb-harness -print -quit 2>/dev/null)" ]; then
  exit 0
fi

# --- locate a harness checkout ----------------------------------------------
# Sessions configured with both repos get a sibling clone; JSB_HARNESS_DIR
# overrides for local use.
harness=""
for candidate in \
  "${JSB_HARNESS_DIR:-}" \
  "$root/../harness" \
  "$HOME/harness"
do
  [ -n "$candidate" ] || continue
  if [ -d "$candidate/$plugin_rel" ]; then
    harness="$candidate"
    break
  fi
done

# Never fail the session: without a checkout the skills are simply not
# vendored, and the agent follows them from source (CLAUDE.md "Cloud
# sessions"). Printed on stdout so the session sees it.
if [ -z "$harness" ]; then
  echo "session-start: no jsb-harness checkout found (set JSB_HARNESS_DIR or attach JSBaxter/harness as ../harness); skills not vendored, follow them from source."
  exit 0
fi

src="$harness/$plugin_rel"

# --- skills -----------------------------------------------------------------
# Skills are only discovered under .claude/skills/, so vendored copies go in
# beside the repo's own. Never overwrite a repo-owned skill.
mkdir -p "$root/.claude/skills"
# Retirement sweep, only over directories carrying the .vendored-from-harness
# marker — a repo-owned skill must never be swept. Without this a retired
# skill keeps loading forever on any filesystem that survives between
# sessions (every local checkout and any JSB_HARNESS_DIR setup).
for stale in "$root"/.claude/skills/*/; do
  [ -d "$stale" ] || continue
  [ -e "$stale/.vendored-from-harness" ] || continue
  if [ ! -d "$src/skills/$(basename "$stale")" ]; then
    echo "session-start: removing retired skill $(basename "$stale")." >&2
    rm -rf "$stale"
  fi
done
skills=0
if [ -d "$src/skills" ]; then
  for d in "$src"/skills/*/; do
    [ -d "$d" ] || continue
    name="$(basename "$d")"
    dest="$root/.claude/skills/$name"
    if [ -e "$dest" ] && [ ! -e "$dest/.vendored-from-harness" ]; then
      echo "session-start: keeping repo-owned skill '$name'; not overwriting." >&2
      continue
    fi
    rm -rf "$dest"
    cp -R "$d" "$dest"
    printf '%s\n' "Vendored from JSBaxter/harness $plugin_rel/skills/$name. Do not edit; edit it there." \
      > "$dest/.vendored-from-harness"
    skills=$((skills + 1))
  done
fi

# --- agents -----------------------------------------------------------------
# Agents are flat files under .claude/agents/. Each harness agent is copied
# over; nothing else in the directory is touched, so a cell's deliberate
# .claude/agents/reviewer-override.md (the one committed file there, see
# .gitignore) survives every run.
mkdir -p "$root/.claude/agents"
agents=0
if [ -d "$src/agents" ]; then
  for f in "$src"/agents/*.md; do
    [ -e "$f" ] || continue
    name="$(basename "$f")"
    [ "$name" = "reviewer-override.md" ] && continue
    cp "$f" "$root/.claude/agents/$name"
    agents=$((agents + 1))
  done
fi

echo "session-start: vendored $skills skill(s) and $agents agent(s) from $src into .claude/."
exit 0
