.PHONY: secrets-scan lint lint-fix format typecheck security audit deadcode test test-docker check check-server

PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python)

secrets-scan:
	gitleaks detect --source . --config tooling/gitleaks.toml -v --redact

lint:
	$(PYTHON) -m ruff check .

lint-fix:
	$(PYTHON) -m ruff check . --fix

format:
	$(PYTHON) -m ruff format .

typecheck:
	$(PYTHON) -m mypy . --config-file=pyproject.toml

security:
	$(PYTHON) -m bandit -c tooling/bandit.yaml -r .

audit:
	$(PYTHON) -m pip_audit -r requirements.txt
	$(PYTHON) -m pip_audit -r requirements-dev.txt

deadcode:
	$(PYTHON) -m vulture

test:
	$(PYTHON) -m pytest --cov --cov-report=term-missing --cov-report=xml:tests/reports/coverage.xml --cov-fail-under=70

test-docker:
	docker compose run --rm --user root \
	  -e APP_ENV=test \
	  -e USE_WEBHOOK=false \
	  -e SKIP_WEBHOOK_REGISTRATION=true \
	  -v "$(CURDIR)/tests/reports:/app/tests/reports" \
	  bot bash -lc "pip install -r requirements-dev.txt --quiet && python -m pytest --cov --cov-report=term-missing --cov-report=xml:tests/reports/coverage.xml --cov-fail-under=70"

check: lint typecheck security secrets-scan audit deadcode test

check-server: lint typecheck security secrets-scan audit deadcode test-docker
