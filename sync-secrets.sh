#!/usr/bin/env bash
# sync-secrets.sh — Push local credentials to GitHub Secrets for the
#                   clip-reviewer GitHub Actions workflow.
#
# Usage:
#   ./sync-secrets.sh                        # sync all secrets
#   ./sync-secrets.sh --dry-run              # just print what would be set
#
# Requires: gh CLI authenticated with admin scope on this repo.
# Install gh: https://cli.github.com/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/config"
DRY=false

for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY=true
done

gh_secret_set() {
  local name="$1"
  local value="$2"
  if $DRY; then
    echo "[DRY] Would set secret: $name (${#value} chars)"
  else
    echo "$value" | gh secret set "$name" --repo "$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "UNKNOWN")"
    echo "✅  $name set"
  fi
}

echo "=== ClipSurge — Sync secrets to GitHub Actions ==="
echo ""

# 1. YouTube clipper OAuth token
TOKEN_PATH="/home/varad/Downloads/client_secret_1005549529661-0l2b6rft66m2golopp5pfdjtgk8rrhak.apps.googleusercontent.com.json"
if [[ -f "$TOKEN_PATH" ]]; then
  gh_secret_set "YOUTUBE_TOKEN_CLIPPER" "$(cat "$TOKEN_PATH")"
else
  echo "⚠️  $TOKEN_PATH not found — skipping YOUTUBE_TOKEN_CLIPPER"
fi

# 2. YouTube client secret (clipper channel)
SECRET_PATH="$CONFIG_DIR/youtube_client_secret_clipper.json"
if [[ -f "$SECRET_PATH" ]]; then
  gh_secret_set "YOUTUBE_CLIENT_SECRET_CLIPPER" "$(cat "$SECRET_PATH")"
else
  echo "⚠️  $SECRET_PATH not found — skipping YOUTUBE_CLIENT_SECRET_CLIPPER"
fi

# 3. Upload history (staged clips state)
HISTORY_PATH="$CONFIG_DIR/youtube_upload_history.json"
if [[ -f "$HISTORY_PATH" ]]; then
  COUNT=$(python3 -c "import json,sys; d=json.load(open('$HISTORY_PATH')); print(len(d))" 2>/dev/null || echo "?")
  gh_secret_set "YOUTUBE_UPLOAD_HISTORY" "$(cat "$HISTORY_PATH")"
  echo "   ($COUNT entries in upload history)"
else
  echo "⚠️  $HISTORY_PATH not found — skipping YOUTUBE_UPLOAD_HISTORY"
fi

# 4. Groq key
DOTENV_PATH="$SCRIPT_DIR/.env"
if [[ -f "$DOTENV_PATH" ]]; then
  GROQ_KEY=$(grep -E "^GROQ_API_KEY=" "$DOTENV_PATH" | cut -d= -f2- | tr -d '"' || true)
  if [[ -n "$GROQ_KEY" ]]; then
    gh_secret_set "GROQ_API_KEY" "$GROQ_KEY"
  else
    echo "⚠️  GROQ_API_KEY not in .env — skipping"
  fi

  APINEX_KEY=$(grep -E "^APINEX_API_KEY=" "$DOTENV_PATH" | cut -d= -f2- | tr -d '"' || true)
  if [[ -n "$APINEX_KEY" ]]; then
    gh_secret_set "APINEX_API_KEY" "$APINEX_KEY"
  else
    echo "⚠️  APINEX_API_KEY not in .env — skipping"
  fi
else
  echo "⚠️  .env not found — skipping GROQ_API_KEY / APINEX_API_KEY"
fi

echo ""
echo "=== Done. Run the workflow: gh workflow run clip-reviewer.yml ==="
