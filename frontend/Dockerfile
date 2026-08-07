# syntax=docker/dockerfile:1.7
#
# Multi-stage Next.js build.
# Requires next.config.ts to have output: "standalone".

# ── Stage 1: dependency install ───────────────────────────────────────────────
FROM node:22-alpine AS deps

ENV PNPM_HOME="/pnpm" PATH="$PNPM_HOME:$PATH"
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app
COPY package.json pnpm-lock.yaml .npmrc* ./

# BuildKit cache mount — pnpm store persists across builds
RUN --mount=type=cache,id=pnpm-store,target=/pnpm/store \
    pnpm install --frozen-lockfile --ignore-scripts

# ── Stage 2: build ────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

ENV PNPM_HOME="/pnpm" PATH="$PNPM_HOME:$PATH" \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

RUN corepack enable

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time public env — safe to bake in (no secrets)
ARG NEXT_PUBLIC_APP_URL=http://localhost:3000
ENV NEXT_PUBLIC_APP_URL=${NEXT_PUBLIC_APP_URL}

RUN pnpm build

# ── Stage 3: minimal runtime ──────────────────────────────────────────────────
FROM node:22-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

# Explicit UID/GID for reproducible ownership in K8s / rootless environments
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 --ingroup nodejs nextjs

# Standalone output: only the server, not the full node_modules
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -q --spider http://localhost:3000/api/health 2>/dev/null || \
        wget -q --spider http://localhost:3000 || exit 1

CMD ["node", "server.js"]
