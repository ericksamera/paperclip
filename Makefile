# Usage:
#   make install-dev
#   make fmt
#   make lint
#   make typecheck
#   make ci

PY ?= python3
EXPORTS = PYTHONPATH=services/server:packages DJANGO_SETTINGS_MODULE=paperclip.settings

install-dev:
	$(PY) -m pip install -U pip
	$(PY) -m pip install -r requirements-dev.txt
	pre-commit install

fmt:
	# Sort imports & apply quick autofixes
	ruff check --fix .
	# Format code
	black .

lint:
	# Fail if formatting/linting not clean
	black --check .
	ruff check .

typecheck:
	@echo "mypy disabled temporarily"

ci: lint typecheck
