#!/usr/bin/env bash
# scholar-pipeline bootstrap — idempotent machine setup for CC Switch-managed
# research skills (open-scholar-skill + ARIS). Run from a normal terminal:
#
#   bash ~/.cc-switch/skills/scholar-pipeline/scripts/bootstrap.sh [--dry-run]
#
# It never installs or removes skills (CC Switch owns those). It sets up the
# pieces CC Switch cannot manage:
#   1. runtime clones   ~/.cc-switch/runtime/open-scholar-skill, ~/.cc-switch/runtime/aris
#   2. ARIS pointer     ~/.aris/repo  -> runtime/aris
#   3. Claude agents    ~/.claude/agents/<open-scholar agent>.md -> runtime (symlinks)
#   4. Claude hooks     open-scholar PreToolUse/PostToolUse data-safety hooks
#   5. Env vars         SCHOLAR_SKILL_DIR + ARIS_REPO in ~/.claude/settings.json (env),
#                       ~/.codex/config.toml ([shell_environment_policy.set]) and ~/.zshrc
#   6. Daily updater    LaunchAgent that runs `git pull --ff-only` on both clones
set -uo pipefail

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
RT="$HOME/.cc-switch/runtime"
OSS="$RT/open-scholar-skill"
ARIS="$RT/aris"
OSS_URL="https://github.com/joshzyj/open-scholar-skill.git"
ARIS_URL="https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git"
STAMP="$(date +%Y%m%d-%H%M%S)"
say() { printf '%s\n' "$*"; }
run() { if [ "$DRY" = 1 ]; then say "  [dry-run] $*"; else "$@"; fi; }

for bin in git python3; do
  command -v "$bin" >/dev/null 2>&1 || { say "✗ $bin is required"; exit 1; }
done
if ! command -v jq >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    say "▸ Installing jq (needed by the open-scholar data-safety hook)"; run brew install jq
  else
    say "⚠ jq not found and Homebrew unavailable — the data-safety hook will fail closed until jq is installed"
  fi
fi

# ── 1. runtime clones ───────────────────────────────────────────────────
ensure_clone() {
  local dir="$1" url="$2"
  if [ -d "$dir/.git" ] && git -C "$dir" rev-parse -q --verify HEAD >/dev/null 2>&1 \
     && git -C "$dir" fsck --connectivity-only >/dev/null 2>&1; then
    say "  ✓ $(basename "$dir") clone ok — pulling"
    run git -C "$dir" pull -q --ff-only || say "  ⚠ pull failed in $dir (kept current checkout)"
  else
    if [ -e "$dir" ]; then
      say "  ↻ $dir is not a healthy clone — moving it aside"
      run mv "$dir" "$dir.broken-$STAMP"
    fi
    say "  + cloning $url"
    run git clone -q --depth 1 "$url" "$dir" || { say "  ✗ clone failed: $url"; return 1; }
  fi
  if [ "$DRY" = 0 ]; then
    local f l
    while IFS= read -r -d '' f; do
      IFS= read -r l < "$f" || l=""
      case "$l" in '#!'*) [ -x "$f" ] || chmod +x "$f" ;; esac
    done < <(find "$dir" -path "$dir/.git" -prune -o -type f \( -name '*.sh' -o -name '*.py' \) -print0)
  fi
}
say "▸ Runtime clones in $RT"
run mkdir -p "$RT"
ensure_clone "$OSS" "$OSS_URL"
ensure_clone "$ARIS" "$ARIS_URL"
if [ -d "$RT/_to_delete" ]; then run rm -rf "$RT/_to_delete"; fi

# ── 2. ARIS global pointer ──────────────────────────────────────────────
say "▸ ARIS pointer ~/.aris/repo"
run mkdir -p "$HOME/.aris"
if [ "$DRY" = 0 ]; then printf '%s\n' "$ARIS" > "$HOME/.aris/repo"; fi

# ── 3. Claude agents ────────────────────────────────────────────────────
say "▸ Claude agents"
run mkdir -p "$HOME/.claude/agents"
linked=0; skipped=0
for src in "$OSS"/.claude/agents/*.md; do
  [ -f "$src" ] || continue
  dst="$HOME/.claude/agents/$(basename "$src")"
  if [ -L "$dst" ]; then
    [ "$(readlink "$dst")" = "$src" ] && continue
    run rm "$dst"
  elif [ -e "$dst" ]; then
    say "  ⚠ $(basename "$dst") exists as a real file — left untouched"; skipped=$((skipped + 1)); continue
  fi
  run ln -s "$src" "$dst" && linked=$((linked + 1))
done
# drop dangling links left by older open-scholar installs
for l in "$HOME"/.claude/agents/*.md; do
  [ -L "$l" ] && [ ! -e "$l" ] && { say "  - removing dangling agent link $(basename "$l")"; run rm "$l"; }
done
say "  ✓ agents linked: $linked new, $skipped skipped"

# ── 4 + 5. settings.json (hooks + env) ──────────────────────────────────
SETTINGS="$HOME/.claude/settings.json"
say "▸ Claude settings: hooks + env ($SETTINGS)"
if [ "$DRY" = 0 ]; then
  [ -f "$SETTINGS" ] && cp "$SETTINGS" "$SETTINGS.bak-$STAMP"
  python3 - "$SETTINGS" "$OSS" "$ARIS" <<'PY'
import json, os, sys
path, oss, aris = sys.argv[1:4]
data = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read().strip()
    data = json.loads(text) if text else {}
pre = f"bash '{oss}/scripts/gates/pretooluse-data-guard.sh'"
post = f"bash '{oss}/scripts/gates/posttooluse-output-guard.sh'"
hooks = data.setdefault("hooks", {})

def clean(entries, marker):
    out = []
    for e in entries or []:
        hs = [h for h in e.get("hooks", []) if marker not in h.get("command", "")]
        if hs:
            out.append({**e, "hooks": hs})
    return out

hooks["PreToolUse"] = clean(hooks.get("PreToolUse"), "pretooluse-data-guard.sh") + [{
    "matcher": "Read|NotebookRead|NotebookEdit|Grep|Glob|Bash|Edit|Write|MultiEdit",
    "hooks": [{"type": "command", "command": pre}]}]
hooks["PostToolUse"] = clean(hooks.get("PostToolUse"), "posttooluse-output-guard.sh") + [{
    "matcher": "Bash", "hooks": [{"type": "command", "command": post}]}]
env = data.setdefault("env", {})
env["SCHOLAR_SKILL_DIR"] = oss
env["ARIS_REPO"] = aris
os.makedirs(os.path.dirname(path), exist_ok=True)
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
os.replace(tmp, path)
print("  ✓ hooks + env written (backup kept next to settings.json)")
PY
fi

CODEX_CFG="$HOME/.codex/config.toml"
say "▸ Codex env ($CODEX_CFG)"
if [ "$DRY" = 0 ] && [ -f "$CODEX_CFG" ]; then
  cp "$CODEX_CFG" "$CODEX_CFG.bak-$STAMP"
  python3 - "$CODEX_CFG" "$OSS" "$ARIS" <<'PY'
import re, sys
path, oss, aris = sys.argv[1:4]
text = open(path, encoding="utf-8").read()
want = {"SCHOLAR_SKILL_DIR": oss, "ARIS_REPO": aris}
hdr = re.search(r"(?m)^\[shell_environment_policy\.set\][ \t]*$", text)
if hdr:
    start = hdr.end()
    nxt = re.search(r"(?m)^\[", text[start:])
    end = start + nxt.start() if nxt else len(text)
    body = text[start:end]
    for k, v in want.items():
        line = f'{k} = "{v}"'
        if re.search(rf"(?m)^{k}\s*=", body):
            body = re.sub(rf"(?m)^{k}\s*=.*$", line, body)
        else:
            body = body.rstrip("\n") + "\n" + line
    text = text[:start] + body.rstrip("\n") + ("\n\n" if nxt else "\n") + text[end:]
else:
    text = text.rstrip("\n") + "\n\n[shell_environment_policy.set]\n" + "".join(f'{k} = "{v}"\n' for k, v in want.items())
open(path, "w", encoding="utf-8").write(text)
print("  ✓ shell_environment_policy.set updated")
PY
fi

ZRC="$HOME/.zshrc"
say "▸ Shell profile ($ZRC)"
if [ "$DRY" = 0 ]; then
  touch "$ZRC"
  if grep -q '# >>> cc-switch research runtime >>>' "$ZRC"; then
    python3 - "$ZRC" <<'PY'
import re, sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
t = re.sub(r"# >>> cc-switch research runtime >>>.*?# <<< cc-switch research runtime <<<\n?", "", t, flags=re.S)
open(p, "w", encoding="utf-8").write(t)
PY
  fi
  # comment out older exports so the managed block wins
  sed -i.bak-"$STAMP" -E 's/^(export (SCHOLAR_SKILL_DIR|ARIS_REPO)=)/# (superseded by cc-switch block) \1/' "$ZRC"
  cat >> "$ZRC" <<EOF
# >>> cc-switch research runtime >>>
export SCHOLAR_SKILL_DIR="$OSS"
export ARIS_REPO="$ARIS"
# <<< cc-switch research runtime <<<
EOF
  say "  ✓ exports written (backup: $ZRC.bak-$STAMP)"
fi

# ── 6. daily updater ────────────────────────────────────────────────────
if [ "$(uname -s)" = "Darwin" ]; then
  LABEL="com.ccswitch.research-runtime-sync"
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  say "▸ LaunchAgent $LABEL (daily 09:30 git pull)"
  if [ "$DRY" = 0 ]; then
    mkdir -p "$HOME/Library/LaunchAgents" "$RT/logs"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string><string>-c</string>
    <string>for d in "$OSS" "$ARIS"; do /usr/bin/git -C "\$d" pull -q --ff-only; done</string>
  </array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>$RT/logs/sync.log</string>
  <key>StandardErrorPath</key><string>$RT/logs/sync.log</string>
</dict>
</plist>
EOF
    launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST" && say "  ✓ loaded"
  fi
fi

say ""
say "Done. Restart Claude Code and Codex so they pick up the new env/hooks."
say "  SCHOLAR_SKILL_DIR=$OSS"
say "  ARIS_REPO=$ARIS"
