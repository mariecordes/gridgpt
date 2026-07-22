# GridGPT Makefile
# Helpful targets for local development and deployment build steps.
# Use `make <target>`.

# Variables
# Dependencies come from pyproject.toml + uv.lock
# uv manages the .venv, so every Python invocation goes through `uv run`.
PYTHON ?= uv run python
BACKEND_PORT ?= 8000
FRONTEND_DIR := frontend
EMBED_DATA_DIR := data/02_intermediary/word_database

.PHONY: help install install-dev precompute refresh-db build-backend dev-backend dev-frontend test clean-embeddings clean all clean-and-build-backend

help:
	@echo "Available targets:"
	@echo "  install          - Install runtime dependencies only (used by the Railway build)"
	@echo "  install-dev      - Install runtime + dev dependencies (local development)"
	@echo "  precompute       - Precompute word embeddings (idempotent)"
	@echo "  refresh-db       - Scrape new NYT mini data, rebuild word DB + embeddings (ARGS=\"--dry-run\" / \"--force\")"
	@echo "  build-backend    - Install runtime deps + precompute embeddings (use this in Railway Build Command)"
	@echo "  dev-backend      - Run uvicorn backend (reload)"
	@echo "  dev-frontend     - Run Next.js dev server"
	@echo "  test             - Run backend test suite"
	@echo "  clean-embeddings - Remove cached embedding artifacts"
	@echo "  clean            - General cleanup (currently just embeddings)"

# Runtime only. `uv sync` prunes anything not in the lock, so this deliberately
# leaves out the dev group; use `install-dev` locally.
install:
	@command -v uv >/dev/null 2>&1 || pip install uv
	uv sync --frozen --no-dev

install-dev:
	@command -v uv >/dev/null 2>&1 || pip install uv
	uv sync --frozen

precompute:
	@echo "[precompute] Building embedding cache if missing (model from parameters.yml)..."
	$(PYTHON) scripts/precompute_embeddings.py

refresh-db:
	@echo "[refresh-db] Refreshing word database and embedding cache..."
	$(PYTHON) -m scripts.refresh_database $(ARGS)

build-backend: install precompute
	@echo "[build] Backend build complete (dependencies + embeddings)."

# Development helpers

dev-backend:
	uv run uvicorn api.main:app --host 0.0.0.0 --port $(BACKEND_PORT) --reload

dev-frontend:
	cd $(FRONTEND_DIR) && npm run dev

test:
	uv run pytest -q

clean-embeddings:
	rm -f $(EMBED_DATA_DIR)/word_embeddings*.npy || true
	rm -f $(EMBED_DATA_DIR)/word_index*.json || true

clean: clean-embeddings
	@echo "Clean complete."

clean-and-build-backend: ## Run clean then build-backend (ordered)
	$(MAKE) clean
	$(MAKE) build-backend

all: build-backend
