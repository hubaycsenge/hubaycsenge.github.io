#!/usr/bin/env bash
# Rebuild the site from the research vault.
#
#   ./build.sh                        # uses ../PhD_research
#   ./build.sh --vault ~/somewhere    # or point it elsewhere
#
# Creates a local .venv on first run (gitignored). The vault's raw/ directory is
# never read — see build.py.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creating .venv…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet markdown pyyaml
fi

exec ./.venv/bin/python build.py "$@"
