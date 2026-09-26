.PHONY: install install-python install-ollama ollama-serve \
	ollama-pull-preprocess ollama-pull-analyze ollama-pull-all \
	preprocess analyze evaluation serve check test build clean-build help

CONFIG ?= config.yaml
UV ?= uv
PYTHON ?= $(UV) run python
OLLAMA ?= ollama
# Prefer local Ollama. Unconditional so a stale shell OLLAMA_HOST
# (e.g. http://my-ollama-server:11434) cannot break make targets.
# Override on the CLI if needed: make analyze OLLAMA_HOST=remote:11434
OLLAMA_HOST := 127.0.0.1:11434
export OLLAMA_HOST
HOST ?= 127.0.0.1
PORT ?= 8000
RELOAD ?= 1

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

install: install-ollama install-python ollama-pull-all ## Install Ollama, Python package (uv), and pull all config models
	@echo "✅ Install complete"

install-python: ## Create venv and install the compliance package (+ pre-commit)
	@echo "🚀 Creating virtual environment using uv"
	@$(UV) sync
	@$(UV) run pre-commit install

install-ollama: ## Install the Ollama CLI (macOS Homebrew or official Linux script)
	@echo "🚀 Ensuring Ollama is installed"
	@if command -v $(OLLAMA) >/dev/null 2>&1; then \
		echo "   ollama already on PATH: $$($(OLLAMA) --version 2>/dev/null || true)"; \
	elif [ "$$(uname -s)" = "Darwin" ]; then \
		if command -v brew >/dev/null 2>&1; then \
			brew install ollama; \
		else \
			echo "❌ Homebrew not found. Install Ollama from https://ollama.com/download or install brew."; \
			exit 1; \
		fi; \
	else \
		curl -fsSL https://ollama.com/install.sh | sh; \
	fi

ollama-serve: ## Start the Ollama server if it is not already reachable
	@if OLLAMA_HOST=$(OLLAMA_HOST) $(OLLAMA) list >/dev/null 2>&1; then \
		echo "🟢 Ollama server reachable ($(OLLAMA_HOST))"; \
	else \
		echo "🚀 Starting Ollama server in background (OLLAMA_HOST=$(OLLAMA_HOST))"; \
		OLLAMA_HOST=$(OLLAMA_HOST) $(OLLAMA) serve >/tmp/ollama-serve.log 2>&1 & \
		sleep 2; \
		OLLAMA_HOST=$(OLLAMA_HOST) $(OLLAMA) list >/dev/null 2>&1 || (echo "❌ Ollama did not start; see /tmp/ollama-serve.log"; exit 1); \
	fi

# ---------------------------------------------------------------------------
# Model pulls (names read from config.yaml — no hardcoded model list)
# ---------------------------------------------------------------------------

ollama-pull-preprocess: ollama-serve ## Pull Ollama models used by preprocessing (extraction + OCR retry)
	@echo "🚀 Pulling preprocessing models from $(CONFIG)"
	@models=$$($(PYTHON) -c "from compliance.config import load_config; c=load_config('$(CONFIG)'); print(' '.join(sorted({c.extraction.model, c.ocr_retry.model})))"); \
	for m in $$models; do echo "   ollama pull $$m"; $(OLLAMA) pull "$$m"; done

ollama-pull-analyze: ollama-serve ## Pull Ollama models used by claim analysis (classification + checking + stages)
	@echo "🚀 Pulling analysis models from $(CONFIG)"
	@models=$$($(PYTHON) -c "from compliance.config import load_config; c=load_config('$(CONFIG)'); s=c.analysis; print(' '.join(sorted({c.classification.model, c.checking.model, s.coverage.model, s.cancellation_reason.model, s.cancellation_document.model, s.personal_effects_document.model, s.missed_departure_document.model})))"); \
	for m in $$models; do echo "   ollama pull $$m"; $(OLLAMA) pull "$$m"; done

ollama-pull-all: ollama-pull-preprocess ollama-pull-analyze ## Pull every Ollama model referenced by preprocess + analyze

# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------

preprocess: ollama-pull-preprocess ## Pull preprocess models, then run preprocessing over data/raw
	@echo "🚀 Running preprocessing (--mode preprocess)"
	@$(PYTHON) src/main.py --config "$(CONFIG)" --mode preprocess

analyze: ollama-pull-analyze ## Pull analysis models, then run ClaimPipeline over preprocessed/
	@echo "🚀 Running claim analysis (--mode analyze)"
	@$(PYTHON) src/main.py --config "$(CONFIG)" --mode analyze

evaluation: ## Score predictions vs answer.json; write metrics, confusion PNG, and analysis stats
	@echo "🚀 Running prediction evaluation"
	@$(PYTHON) -m evaluation --config "$(CONFIG)"

# ---------------------------------------------------------------------------
# API server
# ---------------------------------------------------------------------------

serve: ollama-pull-all ## Pull all config models, then run the FastAPI claims API
	@echo "🚀 Starting FastAPI claims API on http://$(HOST):$(PORT)"
	@reload_flag=""; \
	if [ "$(RELOAD)" = "1" ]; then reload_flag="--reload"; fi; \
	$(UV) run uvicorn api.app:create_app --factory \
		--host "$(HOST)" --port "$(PORT)" $$reload_flag

# ---------------------------------------------------------------------------
# Existing quality / build targets
# ---------------------------------------------------------------------------

check: ## Run code quality tools.
	@echo "🚀 Checking lock file consistency with 'pyproject.toml'"
	@$(UV) lock --locked
	@echo "🚀 Linting code: Running pre-commit"
	@$(UV) run pre-commit run -a
	@echo "🚀 Static type checking: Running mypy"
	@$(UV) run mypy

test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	@$(UV) run python -m pytest --doctest-modules

build: clean-build ## Build wheel file
	@echo "🚀 Creating wheel file"
	@uvx --from build pyproject-build --installer uv

clean-build: ## Clean build artifacts
	@echo "🚀 Removing build artifacts"
	@$(UV) run python -c "import shutil; import os; shutil.rmtree('dist') if os.path.exists('dist') else None"

help:
	@$(UV) run python -c "import re; \
	[[print(f'\033[36m{m[0]:<24}\033[0m {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open(makefile).read(), re.M)] for makefile in ('$(MAKEFILE_LIST)').strip().split()]"

.DEFAULT_GOAL := help
