#!/usr/bin/env sh
set -eu

API_BASE="${API_BASE-${VITE_API_BASE-http://localhost:8000}}"
export API_BASE

envsubst '${API_BASE}' \
  < /usr/share/nginx/html/env-config.template.js \
  > /usr/share/nginx/html/env-config.js

exec nginx -g 'daemon off;'
