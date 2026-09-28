.PHONY: bootstrap dev build lint test test-python up down logs helm-lint helm-template

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

test-python:
	cd apps/ai-services && python -m pytest -q
	cd apps/knowledge-service && python -m pytest -q
	cd services/agents && python -m pytest -q
	cd services/docking && python -m pytest -q
	cd services/kg && python -m pytest -q
	cd services/literature && python -m pytest -q
	cd services/reports && python -m pytest -q
	cd services/workflows && python -m pytest -q

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
