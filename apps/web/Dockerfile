FROM node:20-alpine AS base
RUN corepack enable

# ---- deps: install full workspace deps needed to build this app ----
FROM base AS deps
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY apps/web/package.json apps/web/package.json
COPY packages/ui/package.json packages/ui/package.json
COPY packages/sdk/package.json packages/sdk/package.json
COPY packages/types/package.json packages/types/package.json
COPY config/eslint-config/package.json config/eslint-config/package.json
COPY config/typescript-config/package.json config/typescript-config/package.json
RUN pnpm install --frozen-lockfile --filter=@ai-rxos/web...

# ---- build ----
FROM base AS build
WORKDIR /repo
COPY --from=deps /repo /repo
COPY . .
RUN pnpm --filter=@ai-rxos/types... --filter=@ai-rxos/ui... --filter=@ai-rxos/sdk... build
RUN pnpm --filter=@ai-rxos/web build

# ---- runtime ----
FROM base AS runtime
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -S rxos && adduser -S rxos -G rxos
COPY --from=build /repo/apps/web/.next/standalone ./
COPY --from=build /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build /repo/apps/web/public ./apps/web/public
USER rxos
EXPOSE 3000
ENV PORT=3000
CMD ["node", "apps/web/server.js"]
