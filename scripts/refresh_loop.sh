#!/usr/bin/env bash
# Keep the provider sessions alive, from inside the auth image.
#
# The collector only reads credentials; renewing them is the official CLIs'
# job, and on a dedicated server nobody ever runs those CLIs. The Claude access
# token lasts about 8 hours (Codex's, about 10 days), so without help the panel
# gets stuck on RENEW SESSION a few hours after every login.
#
# This runs as the "refresher" service, in the same image that holds the CLIs
# and with the same credentials volume, so it needs no Docker socket and no
# scheduler on the host. It checks the local expiry - free, no network - and
# only when a token is about to run out does it run the official CLI once,
# which refreshes the token as a side effect. Then it re-reads the file to
# confirm the refresh really happened.
#
#   docker compose run --rm -T refresher bash /app/scripts/refresh_loop.sh --once
#
# Outside the container the same loop works from a systemd timer; point
# CLAUDE_CREDENTIALS and CODEX_CREDENTIALS at the real files.
#
# Environment: REFRESH_INTERVAL_SECONDS (default 1800), CLAUDE_MARGIN_HOURS
# (default 2), CODEX_MARGIN_HOURS (default 48), CLAUDE_CREDENTIALS,
# CODEX_CREDENTIALS.
set -uo pipefail

INTERVAL="${REFRESH_INTERVAL_SECONDS:-1800}"
export CLAUDE_CREDENTIALS="${CLAUDE_CREDENTIALS:-/home/node/.claude/.credentials.json}"
export CODEX_CREDENTIALS="${CODEX_CREDENTIALS:-/home/node/.codex/auth.json}"
declare -A MARGIN=(
  [claude]="${CLAUDE_MARGIN_HOURS:-2}"
  [codex]="${CODEX_MARGIN_HOURS:-48}"
)
# Only an authenticated call makes a CLI renew its token. This was proven for
# Claude: with the token six hours past expiry, "claude auth status" left it
# untouched and a one-word prompt brought it back with eight hours of life.
# "codex login status" was likewise proven to be read-only, so Codex gets the
# same treatment - by analogy, since its token lasts ~10 days and could not be
# tested near expiry. If it ever turns out not to renew, the check below says
# so instead of failing silently.
# Each call costs a negligible slice of quota, a few times a day for Claude and
# about once every ten days for Codex.
declare -A REFRESH=(
  [claude]="claude -p ok"
  [codex]="codex exec --skip-git-repo-check ok"
)

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

# Seconds left on a provider token. Prints a number, or "unreadable".
# Never prints the token itself.
remaining_seconds() {
  node -e '
const fs = require("fs");
const provider = process.argv[1];
try {
  let expiry;
  if (provider === "claude") {
    const oauth = JSON.parse(fs.readFileSync(process.env.CLAUDE_CREDENTIALS, "utf8")).claudeAiOauth;
    expiry = oauth.expiresAt / 1000;
  } else {
    const token = JSON.parse(fs.readFileSync(process.env.CODEX_CREDENTIALS, "utf8")).tokens.access_token;
    const claims = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString("utf8"));
    expiry = Number(claims.exp);
  }
  if (!Number.isFinite(expiry)) throw new Error("bad expiry");
  console.log(Math.floor(expiry - Date.now() / 1000));
} catch (err) {
  console.log("unreadable");
}
' "$1" 2>/dev/null | tail -1
}

refresh_once() {
  local problems=0 provider left margin after
  for provider in claude codex; do
    left="$(remaining_seconds "$provider")"
    if [[ ! "$left" =~ ^-?[0-9]+$ ]]; then
      log "$provider: no readable session; sign in again with the auth profile"
      problems=$((problems + 1))
      continue
    fi
    margin=$(( ${MARGIN[$provider]} * 3600 ))
    if [[ $left -gt $margin ]]; then
      log "$provider: $((left / 3600)) h left, nothing to do"
      continue
    fi
    log "$provider: $((left / 3600)) h left, asking the CLI to renew"
    # The CLI output can echo account details, so it is not logged.
    if ! ${REFRESH[$provider]} >/dev/null 2>&1; then
      log "$provider: the refresh command failed to run"
      problems=$((problems + 1))
      continue
    fi
    after="$(remaining_seconds "$provider")"
    if [[ "$after" =~ ^-?[0-9]+$ ]] && [[ $after -gt $left ]]; then
      log "$provider: renewed, now $((after / 3600)) h left"
    elif [[ $left -le 0 ]]; then
      # Already expired and still not renewed: the refresh token itself is
      # probably gone, and only a real login fixes that.
      log "$provider: expired and the CLI could not renew it - sign in again"
      problems=$((problems + 1))
    else
      # The CLIs renew when a token is close to running out, not on demand.
      # Still valid means there was nothing to do; the next pass retries.
      log "$provider: still valid, the CLI saw no need to renew yet"
    fi
  done
  return $(( problems > 0 ? 1 : 0 ))
}

if [[ "${1:-}" == "--once" ]]; then
  refresh_once
  exit $?
fi

log "refresher started; checking every $((INTERVAL / 60)) min"
while true; do
  refresh_once || true
  sleep "$INTERVAL"
done
