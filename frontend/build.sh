#!/bin/sh
# Render static-site build script.
# Injects the deployed backend base URL (from env AVIRA_BACKEND_URL) into a
# runtime config file consumed by js/api.js. Falls back to same-origin /api
# if the env var is not set (e.g. when serving locally behind nginx/Docker).

set -e

# Default: same-origin /api (works behind the local nginx proxy / Docker)
BACKEND_URL="${AVIRA_BACKEND_URL:-/api}"

# Write the config consumed by frontend/js/api.js (properly JSON-quoted)
printf 'window.AVIRA_CONFIG = { backendUrl: %s };\n' "\"${BACKEND_URL}\"" > config.js

echo "config.js generated with backendUrl: ${BACKEND_URL}"
exit 0
