FROM node:20-alpine AS base
RUN corepack enable

# ---- deps: install full workspace deps needed to build this service ----
FROM base AS deps
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY services/auth-adapter/package.json services/auth-adapter/package.json
COPY config/eslint-config/package.json config/eslint-config/package.json
COPY config/typescript-config/package.json config/typescript-config/package.json
RUN pnpm install --frozen-lockfile --filter=@ai-rxos/auth-adapter...

# ---- build ----
FROM base AS build
WORKDIR /repo
COPY --from=deps /repo /repo
COPY . .
RUN pnpm --filter=@ai-rxos/auth-adapter build

# ---- runtime ----
# Install the production dependency graph explicitly so pnpm creates the
# symlinked node_modules layout that ESM packages like dotenv resolve from.
FROM base AS runtime
WORKDIR /repo
ENV NODE_ENV=production
RUN addgroup -S rxos && adduser -S rxos -G rxos
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY services/auth-adapter/package.json services/auth-adapter/package.json
COPY config/eslint-config/package.json config/eslint-config/package.json
COPY config/typescript-config/package.json config/typescript-config/package.json
RUN pnpm install --frozen-lockfile --prod --filter=@ai-rxos/auth-adapter...
COPY --from=build /repo/services/auth-adapter/package.json ./services/auth-adapter/package.json
COPY --from=build /repo/services/auth-adapter/dist ./services/auth-adapter/dist
USER rxos
EXPOSE 8089
ENV PORT=8089
CMD ["node", "services/auth-adapter/dist/index.js"]
