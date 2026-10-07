#!/usr/bin/env bash
# AI-RxOS Local Development Environment Setup Script (POSIX / Linux / macOS)
set -euo pipefail

echo "=========================================================="
echo "  AI-RxOS / NeoZenome Local Development Setup (POSIX)     "
echo "=========================================================="

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE_PATH="${REPO_ROOT}/.env.example"
ENV_PATH="${REPO_ROOT}/.env"

# 1. Verify Prerequisites
echo -e "\n[1/5] Checking prerequisites..."
for cmd in node pnpm python3 docker; do
    if command -v "$cmd" >/dev/null 2>&1; then
        echo "  [OK] $cmd is installed."
    else
        echo "  [WARN] $cmd is not found in PATH."
    fi
done

# 2. Bootstrap .env from .env.example
echo -e "\n[2/5] Configuring environment file (.env)..."
if [[ ! -f "$EXAMPLE_PATH" ]]; then
    echo "ERROR: Missing .env.example at $EXAMPLE_PATH" >&2
    exit 1
fi

if [[ ! -f "$ENV_PATH" ]]; then
    cp "$EXAMPLE_PATH" "$ENV_PATH"
    echo "  Created .env from .env.example."
else
    echo "  Existing .env found. Preserving existing values."
fi

# Generate safe local development tokens if needed
if ! grep -q "^SEARCH_INTERNAL_TOKEN=" "$ENV_PATH" || grep -q "^SEARCH_INTERNAL_TOKEN=$" "$ENV_PATH"; then
    TOKEN=$(openssl rand -hex 16 2>/dev/null || date +%s%N | md5sum | head -c 32)
    sed -i.bak "s|^SEARCH_INTERNAL_TOKEN=.*|SEARCH_INTERNAL_TOKEN=${TOKEN}|" "$ENV_PATH" && rm -f "${ENV_PATH}.bak"
    echo "  Generated local SEARCH_INTERNAL_TOKEN."
fi

# 3. Install JS/TS Dependencies
echo -e "\n[3/5] Installing Node/TypeScript dependencies via pnpm..."
if command -v pnpm >/dev/null 2>&1; then
    pnpm install
    echo "  Node packages installed successfully."
fi

# 4. Check / Setup Python Virtual Environment
echo -e "\n[4/5] Checking Python virtual environment..."
VENV_DIR="${REPO_ROOT}/.venv"
if [[ -d "$VENV_DIR" ]]; then
    echo "  Existing .venv detected."
else
    echo "  Creating .venv at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    echo "  Virtual environment created."
fi

echo -e "\n[5/5] Setup Complete!"
echo "To start development:"
echo "  1. Start datastores:  docker compose up -d postgres redis neo4j opensearch"
echo "  2. Start all services: pnpm dev"
echo "  OR run one command:   ./scripts/dev-start.sh"
