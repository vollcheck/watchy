.PHONY: install run dev test clean scan help

help: ## Show this help message
	@echo "Footage Tracker - Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies using uv
	uv sync

run: ## Run the FastAPI server
	uv run python main.py

dev: ## Run the server with hot reload
	uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

test: ## Run the test script
	uv run python test_api.py

scan: ## Perform initial filesystem scan
	@echo "Performing initial scan..."
	@curl -s -X POST http://localhost:8000/scan/initial | python -m json.tool

stats: ## Get current statistics
	@curl -s http://localhost:8000/stats | python -m json.tool

clean: ## Clean up database and generated files
	rm -f footage_tracker.db
	rm -rf __pycache__
	rm -rf .pytest_cache
	@echo "Cleaned up database and cache files"

setup: install ## Complete setup: install deps and create footage directory
	mkdir -p footage
	@echo "✓ Setup complete! Run 'make run' to start the server."
