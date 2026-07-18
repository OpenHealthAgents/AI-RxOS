FROM node:20-alpine AS base
RUN corepack enable

FROM base AS deps
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY apps/admin/package.json apps/admin/package.json
COPY packages/ui/package.json packages/ui/package.json
COPY packages/sdk/package.json packages/sdk/package.json
COPY packages/types/package.json packages/types/package.json
COPY config/eslint-config/package.json config/eslint-config/package.json
COPY config/typescript-config/package.json config/typescript-config/package.json
RUN pnpm install --frozen-lockfile --filter=@ai-rxos/admin...

FROM base AS build
WORKDIR /repo
COPY --from=deps /repo /repo
COPY . .
RUN pnpm --filter=@ai-rxos/types... --filter=@ai-rxos/ui... --filter=@ai-rxos/sdk... build
RUN pnpm --filter=@ai-rxos/admin build

FROM base AS runtime
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -S rxos && adduser -S rxos -G rxos
COPY --from=build /repo/apps/admin/.next/standalone ./
COPY --from=build /repo/apps/admin/.next/static ./apps/admin/.next/static
COPY --from=build /repo/apps/admin/public ./apps/admin/public
USER rxos
EXPOSE 3001
ENV PORT=3001
CMD ["node", "apps/admin/server.js"]
