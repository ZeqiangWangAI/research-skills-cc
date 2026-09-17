#!/usr/bin/env bash
# scholar-pipeline preflight — read-mostly health check for the open-scholar
# runtime. Safe to run at the start of every session.
#
# What it may change (all idempotent, nothing outside these paths):
#   * git pull --ff-only in the runtime clone when the last fetch is >24h old
#   * chmod +x on shebang scripts inside the runtime clone and inside
#     CC Switch-installed scholar-* skills (CC Switch's zip install drops +x,
#     and scholar-auto-research refuses to run non-executable gates)
#   * create <runtime>/.env from .env.example when it is missing
#
# Everything else (agents, hooks, env vars) is only REPORTED; fixing those is
# bootstrap.sh's job and needs the researcher's go-ahead.
#
# Output: KEY=VALUE lines. Exit 0 = ready, 3 = usable with warnings, 4 = blocked.
set -uo pipefail

RUNTIME_DEFAULT="$HOME/.cc-switch/runtime/open-scholar-skill"
RUNTIME="${SCHOLAR_SKILL_DIR:-$RUNTIME_DEFAULT}"
REPO_URL="https://github.com/joshzyj/open-scholar-skill.git"
CCS_SKILLS="$HOME/.cc-switch/skills"
STATUS=0
warn() { echo "WARN=$*"; [ "$STATUS" -lt 3 ] && STATUS=3; }
block() { echo "BLOCK=$*"; STATUS=4; }

echo "HOST_OS=$(uname -s)"
if [ -n "${CODEX_HOME:-}" ] || [ -n "${CODEX_SANDBOX:-}" ] || [ -n "${CODEX_THREAD_ID:-}" ]; then
  echo "HOST_AGENT=codex"
elif [ -n "${CLAUDECODE:-}" ] || [ -n "${CLAUDE_CODE_ENTRYPOINT:-}" ]; then
  echo "HOST_AGENT=claude"
else
  echo "HOST_AGENT=unknown"
fi

for bin in git python3 jq; do
  if command -v "$bin" >/dev/null 2>&1; then echo "HAVE_$bin=1"; else
    case "$bin" in
      jq) warn "jq missing: the open-scholar data-safety hook fails closed without it (brew install jq)";;
      *)  block "$bin missing";;
    esac
  fi
done

# ── runtime clone ───────────────────────────────────────────────────────
if [ -z "${SCHOLAR_SKILL_DIR:-}" ]; then
  warn "SCHOLAR_SKILL_DIR is not set in this shell; prefix Bash calls with: export SCHOLAR_SKILL_DIR=\"$RUNTIME\""
fi
if [ ! -d "$RUNTIME/.git" ]; then
  if command -v git >/dev/null 2>&1 && [ ! -e "$RUNTIME" ]; then
    mkdir -p "$(dirname "$RUNTIME")"
    if git clone -q --depth 1 "$REPO_URL" "$RUNTIME" 2>/dev/null; then
      echo "RUNTIME_CLONED=1"
    else
      block "runtime missing and clone failed: $RUNTIME (check network, then rerun)"
    fi
  else
    block "runtime at $RUNTIME is not a git clone; run bootstrap.sh"
  fi
fi
if [ -d "$RUNTIME/.git" ]; then
  stamp="$RUNTIME/.git/FETCH_HEAD"
  [ -f "$stamp" ] || stamp="$RUNTIME/.git/HEAD"
  age_h=$(( ( $(date +%s) - $(stat -c %Y "$stamp" 2>/dev/null || stat -f %m "$stamp" 2>/dev/null || echo 0) ) / 3600 ))
  if [ "${SCHOLAR_PIPELINE_NO_PULL:-0}" != "1" ] && [ "$age_h" -ge 24 ]; then
    if git -C "$RUNTIME" pull -q --ff-only 2>/dev/null; then
      echo "RUNTIME_PULLED=1"
    else
      warn "git pull failed in $RUNTIME (offline or local edits); continuing with current checkout"
    fi
  fi
  echo "RUNTIME=$RUNTIME"
  echo "RUNTIME_COMMIT=$(git -C "$RUNTIME" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "RUNTIME_VERSION=$(grep -m1 -oE '^## \[?v?[0-9]+\.[0-9]+(\.[0-9]+)?' "$RUNTIME/CHANGELOG.md" 2>/dev/null | tr -d '#[ ' || echo unknown)"
  if [ ! -f "$RUNTIME/.env" ] && [ -f "$RUNTIME/.env.example" ]; then
    {
      echo "# Created by scholar-pipeline preflight on $(date +%Y-%m-%d); edit as needed."
      echo "SCHOLAR_SKILL_DIR=\"$RUNTIME\""
      [ -f "$HOME/Zotero/zotero.sqlite" ] && echo "SCHOLAR_ZOTERO_DIR=\"$HOME/Zotero\""
      echo
      cat "$RUNTIME/.env.example"
    } > "$RUNTIME/.env"
    echo "RUNTIME_ENV_CREATED=1"
  fi
fi

# ── executable bits ─────────────────────────────────────────────────────
fixed=0
fix_x() {
  local f line
  for f in "$@"; do
    [ -f "$f" ] || continue
    IFS= read -r line < "$f" || line=""
    case "$line" in '#!'*) ;; *) continue ;; esac
    if [ ! -x "$f" ]; then chmod +x "$f" 2>/dev/null && fixed=$((fixed + 1)); fi
  done
}
shopt -s nullglob globstar 2>/dev/null || shopt -s nullglob
fix_x "$RUNTIME"/scripts/*.sh "$RUNTIME"/scripts/gates/*.sh "$RUNTIME"/scripts/phases/*.sh \
      "$RUNTIME"/.claude/skills/*/scripts/*.sh "$RUNTIME"/.claude/skills/*/scripts/gates/*.sh
fix_x "$CCS_SKILLS"/scholar-*/scripts/*.sh "$CCS_SKILLS"/scholar-*/scripts/*.py \
      "$CCS_SKILLS"/scholar-*/scripts/gates/*.sh "$CCS_SKILLS"/scholar-*/scripts/gates/*.py \
      "$CCS_SKILLS"/scholar-pipeline/scripts/*.sh "$CCS_SKILLS"/scholar-pipeline/scripts/*.py
echo "EXEC_BITS_FIXED=$fixed"

# ── installed skills (CC Switch) ────────────────────────────────────────
expected=()
for d in "$RUNTIME"/.claude/skills/*/; do
  n="$(basename "$d")"; [ "$n" = "_shared" ] && continue; expected+=("$n")
done
for app in claude codex; do
  dir="$HOME/.$app/skills"
  [ -d "$dir" ] || { echo "SKILLS_${app}=absent"; continue; }
  missing=()
  for n in ${expected[@]+"${expected[@]}"}; do [ -e "$dir/$n/SKILL.md" ] || missing+=("$n"); done
  echo "SKILLS_${app}_PRESENT=$(( ${#expected[@]} - ${#missing[@]} ))/${#expected[@]}"
  [ ${#missing[@]} -gt 0 ] && echo "SKILLS_${app}_MISSING=${missing[*]:-}"
done
if [ -e "$HOME/.claude/skills/scholar-pipeline" ] || [ -e "$HOME/.codex/skills/scholar-pipeline" ]; then :; else
  warn "scholar-pipeline itself is not enabled in ~/.claude/skills or ~/.codex/skills"
fi

# ── Claude-only runtime pieces (agents + data-safety hook) ─────────────
if [ -d "$HOME/.claude" ]; then
  have=0; total=0
  for f in "$RUNTIME"/.claude/agents/*.md; do
    total=$((total + 1)); [ -e "$HOME/.claude/agents/$(basename "$f")" ] && have=$((have + 1))
  done
  echo "CLAUDE_AGENTS=$have/$total"
  [ "$have" -lt "$total" ] && warn "open-scholar agents missing in ~/.claude/agents — run bootstrap.sh"
  settings="$HOME/.claude/settings.json"
  if [ -f "$settings" ] && grep -q "$RUNTIME/scripts/gates/pretooluse-data-guard.sh" "$settings" 2>/dev/null; then
    echo "CLAUDE_SAFETY_HOOK=1"
  else
    warn "open-scholar PreToolUse data-safety hook is not registered for $RUNTIME — run bootstrap.sh before touching real data"
    echo "CLAUDE_SAFETY_HOOK=0"
  fi
fi

echo "PREFLIGHT_STATUS=$STATUS"
exit "$STATUS"
