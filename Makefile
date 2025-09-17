# GridGPT Makefile
# Helpful targets for local development and deployment build steps.
# Use `make <target>`.

# Variables
PYTHON ?= python
BACKEND_PORT ?= 8000
FRONTEND_DIR := frontend
EMBED_DATA_DIR := data/02_intermediary/word_database
EMBED_WORD_LIST := word_list_with_frequencies.json
EMBED_MATRIX := word_embeddings_fp16.npy
EMBED_INDEX := word_index.json
EMBED_MODEL := text-embedding-3-small

.PHONY: help install precompute build-backend dev-backend dev-frontend clean-embeddings clean all clean-and-build-backend

help:
	@echo "Available targets:"
	@echo "  install          - Install backend runtime dependencies"
	@echo "  precompute       - Precompute word embeddings (idempotent)"
	@echo "  build-backend    - Install deps + precompute embeddings (use this in Railway Build Command)"
	@echo "  dev-backend      - Run uvicorn backend (reload)"
	@echo "  dev-frontend     - Run Next.js dev server"
	@echo "  clean-embeddings - Remove cached embedding artifacts"
	@echo "  clean            - General cleanup (currently just embeddings)"

install:
	pip install -r api/requirements.txt

precompute: install
	@echo "[precompute] Building embedding cache if missing..."
	$(PYTHON) scripts/precompute_embeddings.py --model $(EMBED_MODEL) \
		--data-dir $(EMBED_DATA_DIR) \
		--word-list $(EMBED_WORD_LIST) \
		--embeddings-file $(EMBED_MATRIX) \
		--index-file $(EMBED_INDEX)

build-backend: precompute
	@echo "[build] Backend build complete (dependencies + embeddings)."

# Development helpers

dev-backend:
	uvicorn api.main:app --host 0.0.0.0 --port $(BACKEND_PORT) --reload

dev-frontend:
	cd $(FRONTEND_DIR) && npm run dev

clean-embeddings:
	rm -f $(EMBED_DATA_DIR)/$(EMBED_MATRIX) || true
	rm -f $(EMBED_DATA_DIR)/$(EMBED_INDEX) || true

clean: clean-embeddings
	@echo "Clean complete."

clean-and-build-backend: ## Run clean then build-backend (ordered)
	$(MAKE) clean
	$(MAKE) build-backend

all: build-backend
