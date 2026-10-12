# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS web
WORKDIR /build
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc tsconfig.base.json turbo.json biome.json ./
COPY apps/web ./apps/web
COPY packages/ui-tokens ./packages/ui-tokens
COPY packages/ui-web ./packages/ui-web
COPY packages/chat-ui ./packages/chat-ui
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm install --global pnpm@11.25.0 && pnpm install --frozen-lockfile
RUN pnpm build
FROM python:3.12-slim-bookworm AS server
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LONORA_WEB_ROOT=/app/apps/web/dist
WORKDIR /app
COPY pyproject.toml LICENSE THIRD_PARTY_NOTICES.md ./
COPY packages ./packages
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY scripts ./scripts
COPY entrypoint.sh ./entrypoint.sh
COPY --from=web /build/apps/web/dist ./apps/web/dist
RUN --mount=type=secret,id=system_ca,required=false \
    if [ -f /run/secrets/system_ca ]; then export PIP_CERT=/run/secrets/system_ca; fi; \
    python -m pip install --no-cache-dir .
RUN useradd --system --uid 10001 --create-home lonora && mkdir -p /app/.runtime/artifacts && chown -R lonora:lonora /app/.runtime && chmod +x /app/entrypoint.sh /app/scripts/*.sh
USER lonora
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["api"]
