.PHONY: bootstrap dev build lint test up down logs helm-lint helm-template

bootstrap:
	pnpm install
	cp -n .env.example .env || true

dev:
	pnpm dev

build:
	pnpm build

lint:
	pnpm lint

test:
	pnpm test

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

helm-lint:
	helm lint infra/helm/ai-rxos

helm-template:
	helm template ai-rxos infra/helm/ai-rxos -f infra/helm/ai-rxos/values-dev.yaml
