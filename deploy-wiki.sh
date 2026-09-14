#!/usr/bin/env bash
# Deploy the restricted wiki (_private/, built by ./build.sh) to Cloudflare Pages.
#
#   ./deploy-wiki.sh                          # project "csenge-wiki"
#   WIKI_PROJECT=other-name ./deploy-wiki.sh
#
# Refuses to upload unless Cloudflare Access already guards both the production
# hostname and the preview hostnames, so the wiki is never public, even briefly.
# One-time setup is described in README.md ("The restricted wiki").
set -euo pipefail
cd "$(dirname "$0")"

PROJECT="${WIKI_PROJECT:-csenge-wiki}"
WRANGLER=(npx --yes wrangler@4)

[ -f _private/index.html ] || { echo "No _private/ build — run ./build.sh first." >&2; exit 1; }

guarded() {
  # Access answers an unauthenticated request with a redirect to its login page.
  local url="$1" location
  location=$(curl -s -o /dev/null -w '%{redirect_url}' --max-time 20 "$url" || true)
  [[ "$location" == *cloudflareaccess.com* ]]
}

for url in "https://${PROJECT}.pages.dev/" "https://access-check.${PROJECT}.pages.dev/"; do
  if ! guarded "$url"; then
    echo "Refusing to deploy: $url is not behind Cloudflare Access." >&2
    echo "Add both ${PROJECT}.pages.dev and *.${PROJECT}.pages.dev to the Access application first." >&2
    exit 1
  fi
done
echo "Access guards ${PROJECT}.pages.dev and its previews."

"${WRANGLER[@]}" pages deploy _private --project-name "$PROJECT" --branch main --commit-dirty=true
