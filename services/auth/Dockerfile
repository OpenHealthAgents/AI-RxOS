FROM node:20-alpine AS base
RUN corepack enable

# ---- deps: install full workspace deps needed to build this service ----
FROM base AS deps
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY services/auth/package.json services/auth/package.json
COPY config/eslint-config/package.json config/eslint-config/package.json
COPY config/typescript-config/package.json config/typescript-config/package.json
RUN pnpm install --frozen-lockfile --filter=@ai-rxos/auth...

# ---- build ----
FROM base AS build
WORKDIR /repo
COPY --from=deps /repo /repo
COPY . .
RUN pnpm --filter=@ai-rxos/auth build

# ---- runtime ----
FROM base AS runtime
WORKDIR /repo
ENV NODE_ENV=production
RUN addgroup -S rxos && adduser -S rxos -G rxos
COPY --from=build /repo/node_modules ./node_modules
COPY --from=build /repo/services/auth/node_modules ./services/auth/node_modules
COPY --from=build /repo/services/auth/package.json ./services/auth/package.json
COPY --from=build /repo/services/auth/dist ./services/auth/dist
USER rxos
EXPOSE 8081
ENV PORT=8081
CMD ["node", "services/auth/dist/index.js"]
