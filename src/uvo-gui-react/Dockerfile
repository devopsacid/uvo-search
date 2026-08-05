# Build stage
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Serve stage
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx-main.conf /etc/nginx/nginx.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Run as an unprivileged user, matching the k8s pod securityContext
# (runAsUser 10001, see deploy/k8s/base/gui-react.yaml) and closing the
# parity gap with the four Python Dockerfiles (Task 1) -- this closes the
# gap where `docker compose` (no k8s securityContext) still ran nginx as
# root. access.log/error.log are already symlinked to /dev/stdout/stderr in
# this base image, so only the cache and pid paths need to be writable by
# uid 10001; under k8s those are further overridden by the emptyDir mounts
# in gui-react.yaml, this just makes a plain `docker run`/compose safe too.
RUN adduser -u 10001 -D -s /sbin/nologin app \
    && chown -R 10001:10001 /var/cache/nginx /run
USER 10001

EXPOSE 8080
