#!/usr/bin/env bash
# AI-RxOS One-Command Startup Script (POSIX / Linux / macOS)
set -euo pipefail

MODE="${1:-hybrid}"

echo "=========================================================="
echo "  AI-RxOS / NeoZenome One-Command Developer Startup       "
echo "  Selected Mode: $MODE                                    "
echo "=========================================================="

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_PATH="${REPO_ROOT}/.env"

# 1. Environment Validation
if [[ ! -f "$ENV_PATH" ]]; then
    echo "Running dev-setup.sh first..."
    "${REPO_ROOT}/scripts/dev-setup.sh"
fi

# 2. Boot Data Stores
echo -e "\n[1/3] Booting data stores (PostgreSQL, Redis, Neo4j, OpenSearch)..."
docker compose up -d postgres redis neo4j opensearch

sleep 4

if [[ "$MODE" == "datastores" ]]; then
    echo -e "\nData stores are up and running!"
    exit 0
fi

if [[ "$MODE" == "docker" ]]; then
    echo -e "\n[2/3] Launching complete 18-service topology in Docker..."
    docker compose up -d
    echo -e "\nStack is online:"
    echo "  Web Workspace:   http://localhost:3000"
    echo "  Admin Console:   http://localhost:3001"
    echo "  API Gateway:     http://localhost:8080"
    echo "  AI Services:     http://localhost:8090/docs"
    exit 0
fi

if [[ "$MODE" == "hybrid" ]]; then
    echo -e "\n[2/3] Starting development servers..."
    echo "  Workspace live at: http://localhost:3000"
    cd "$REPO_ROOT"
    pnpm dev
fi
