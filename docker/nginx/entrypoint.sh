#!/usr/bin/env sh
set -eu

: "${ADMIN_USER:=admin}"

if [ -z "${ADMIN_PASSWORD:-}" ]; then
  echo "ERROR: ADMIN_PASSWORD is not set"
  exit 1
fi

# Create htpasswd file using APR1 hash (compatible with nginx auth_basic_user_file).
HASH="$(openssl passwd -apr1 "${ADMIN_PASSWORD}")"
printf "%s:%s\n" "${ADMIN_USER}" "${HASH}" > /etc/nginx/.htpasswd
chmod 600 /etc/nginx/.htpasswd

exec nginx -g "daemon off;"

