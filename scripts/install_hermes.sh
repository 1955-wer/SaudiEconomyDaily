#!/usr/bin/env bash
set -euo pipefail

# Official Hermes Agent installer. Browser tooling is deliberately skipped;
# this news worker needs web research tools, not interactive browser automation.
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh \
  | bash -s -- --non-interactive --skip-browser
