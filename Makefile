.PHONY: check-deps install dev

check-deps:
	@echo "Checking prerequisites..."
	@command -v python3 >/dev/null 2>&1 || { echo >&2 "Error: python3 is required but it's not installed. Aborting."; exit 1; }
	@command -v npm >/dev/null 2>&1 || { echo >&2 "Error: npm is required but it's not installed. Aborting."; exit 1; }
	@command -v node >/dev/null 2>&1 || { echo >&2 "Error: node is required but it's not installed. Aborting."; exit 1; }
	@echo "All prerequisites met."

install: check-deps
	@echo "Installing backend dependencies..."
	cd backend && python3 -m venv venv && . venv/bin/activate && pip install -r requirements.txt
	@echo "Installing frontend dependencies..."
	cd frontend && npm ci

dev: check-deps
	@echo "Starting development servers..."
	./start_servers.sh
