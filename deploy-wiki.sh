#!/usr/bin/env bash
# Deploy the restricted wiki (_private/, built by ./build.sh) to Cloudflare Pages.
#
#   ./deploy-wiki.sh                          # project "csenge-wiki"
#   WIKI_PROJECT=other-name ./deploy-wiki.sh
#
# Access control is cloudflare/functions/_middleware.js — GitHub sign-in, with a
# list of permitted usernames. It is uploaded with every deployment and fails
# closed when unconfigured. This script refuses to upload unless the project and
# all its secrets exist, and afterwards checks that a signed-out request is refused.
# One-time setup is described in README.md ("The restricted wiki").
set -euo pipefail
cd "$(dirname "$0")"

PROJECT="${WIKI_PROJECT:-csenge-wiki}"
WRANGLER=(npx --yes wrangler@4)
SECRETS=(GITHUB_CLIENT_ID GITHUB_CLIENT_SECRET SESSION_SECRET ALLOWED_GITHUB_USERS)

[ -f _private/wiki/index.html ] || { echo "No _private/ build — run ./build.sh first." >&2; exit 1; }
# The deployment is the wiki only; anything else at the top level is a stale build.
stray=$(find _private -mindepth 1 -maxdepth 1 ! -name wiki ! -name assets ! -name robots.txt)
[ -z "$stray" ] || { echo "Refusing to deploy non-wiki files: $stray — rerun ./build.sh." >&2; exit 1; }
[ -f cloudflare/functions/_middleware.js ] || { echo "Missing cloudflare/functions/_middleware.js." >&2; exit 1; }

# If the Pages project does not exist, recent wrangler versions hand `pages`
# commands to Cloudflare Workers instead, which would publish without the
# sign-in middleware. Require the project.
if ! "${WRANGLER[@]}" pages project list --json 2>/dev/null | grep -q "\"${PROJECT}\""; then
  echo "Refusing to deploy: Pages project '${PROJECT}' not found (or wrangler is not logged in)." >&2
  echo "Create it once with: npx wrangler@4 pages project create ${PROJECT} --production-branch main --force" >&2
  exit 1
fi

secrets=$("${WRANGLER[@]}" pages secret list --project-name "$PROJECT" 2>/dev/null || true)
for name in "${SECRETS[@]}"; do
  if ! grep -q "$name" <<<"$secrets"; then
    echo "Refusing to deploy: secret $name is not set on '${PROJECT}'." >&2
    echo "Set it with: npx wrangler@4 pages secret put $name --project-name ${PROJECT}" >&2
    exit 1
  fi
done

# Functions are picked up from the working directory, so deploy from cloudflare/.
(cd cloudflare && "${WRANGLER[@]}" pages deploy ../_private --project-name "$PROJECT" --branch main --commit-dirty=true)

echo "Checking that the live wiki refuses signed-out visitors…"
sleep 5
failed=0
for path in / /wiki/ /wiki/search.json /assets/style.css; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://${PROJECT}.pages.dev${path}" || echo 000)
  echo "  ${path} -> ${code}"
  [ "$code" = 401 ] || failed=1
done
# The client ID is public (it is in the link to GitHub); the secret must never be.
# Secrets are 40 hex characters, IDs are not — catch the two being swapped.
client_id=$(curl -s -o /dev/null -w '%{redirect_url}' --max-time 20 "https://${PROJECT}.pages.dev/auth/login" |
  sed -nE 's/.*[?&]client_id=([^&]*).*/\1/p')
if [[ "$client_id" =~ ^[0-9a-f]{40}$ ]]; then
  echo "WARNING: GITHUB_CLIENT_ID looks like a client secret, and /auth/login shows it publicly." >&2
  echo "Regenerate the client secret on GitHub, then set GITHUB_CLIENT_ID to the Client ID and redeploy." >&2
  failed=1
fi
if [ "$failed" = 1 ]; then
  echo "WARNING: a signed-out request was not answered with 401. Check https://${PROJECT}.pages.dev/ now." >&2
  echo "(Right after a deploy the edge can briefly serve the previous deployment; rerun the check in a minute.)" >&2
  exit 1
fi
echo "OK: the wiki is behind GitHub sign-in."
