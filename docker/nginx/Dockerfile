FROM nginx:1.27-alpine

# `entrypoint.sh` generates a htpasswd file via `openssl passwd -apr1`.
RUN apk add --no-cache openssl

COPY nginx.conf /etc/nginx/nginx.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
