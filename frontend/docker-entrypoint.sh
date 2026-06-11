#!/usr/bin/env sh
set -eu

API_BASE="${API_BASE-${VITE_API_BASE-http://localhost:8000}}"
NGINX_API_UPSTREAM="${NGINX_API_UPSTREAM-$API_BASE}"
export API_BASE
export NGINX_API_UPSTREAM

envsubst '${API_BASE}' \
  < /usr/share/nginx/html/env-config.template.js \
  > /usr/share/nginx/html/env-config.js

envsubst '${NGINX_API_UPSTREAM}' \
  < /etc/nginx/conf.d/default.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
