# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS web
WORKDIR /build
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc tsconfig.base.json turbo.json biome.json ./
COPY apps/web ./apps/web
COPY packages/ui-tokens ./packages/ui-tokens
COPY packages/ui-web ./packages/ui-web
COPY packages/chat-ui ./packages/chat-ui
COPY packages/contracts ./packages/contracts
COPY packages/core ./packages/core
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm install --global pnpm@11.25.0 && pnpm install --frozen-lockfile --filter @lonora/web...
RUN pnpm --filter @lonora/web... build
FROM python:3.12-slim-bookworm AS server
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LONORA_WEB_ROOT=/app/apps/web/dist TIKTOKEN_CACHE_DIR=/opt/lonora-tokenizers
WORKDIR /app
# Chromium renders charts and is the workspace's headless browser; the rest is the workspace's
# command line (7.1.2): git, SSH, curl, compilers for pip, Node, and nftables for its guard.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core chromium \
    build-essential curl git jq less nftables nodejs npm openssh-client procps unzip xz-utils \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml LICENSE THIRD_PARTY_NOTICES.md ./
COPY packages ./packages
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
RUN --mount=type=secret,id=system_ca,required=false \
    if [ -f /run/secrets/system_ca ]; then export PIP_CERT=/run/secrets/system_ca REQUESTS_CA_BUNDLE=/run/secrets/system_ca; fi; \
    python -m pip install --no-cache-dir . && \
    python -c 'import tiktoken; [tiktoken.get_encoding(n) for n in ("cl100k_base", "o200k_base")]' && \
    chmod -R a+rX /opt/lonora-tokenizers
COPY --from=web /build/apps/web/dist ./apps/web/dist
COPY scripts ./scripts
COPY entrypoint.sh ./entrypoint.sh
# The production deployment bundle ships inside the image it deploys: the installer
# and `lonora update` copy /app/deploy to the host, so a host needs no source checkout.
COPY infra/compose ./deploy/infra/compose
COPY infra/research ./deploy/infra/research
COPY infra/systemd ./deploy/infra/systemd
COPY infra/release ./infra/release
ARG LONORA_VERSION=""
ARG LONORA_GIT_SHA=unknown
ARG LONORA_BUILT_AT=unknown
RUN python scripts/release_manifest.py --version "$LONORA_VERSION" --git-sha "$LONORA_GIT_SHA" --built-at "$LONORA_BUILT_AT" >/app/release.json && cp /app/release.json /app/deploy/release.json
RUN groupadd --system --gid 10001 lonora && useradd --system --uid 10001 --gid 10001 --create-home lonora && mkdir -p /app/.runtime/artifacts /app/.runtime/cli && chmod -R a+rX /app && chown -R lonora:lonora /app/.runtime && chmod +x /app/entrypoint.sh /app/scripts/*.sh /app/deploy/infra/compose/*.sh /app/deploy/infra/compose/lonora
USER lonora
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["api"]
