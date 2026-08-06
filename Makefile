.PHONY: secrets-scan lint lint-fix format typecheck security audit deadcode test check

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

deadcode:
	$(PYTHON) -m vulture

test:
	$(PYTHON) -m pytest --cov --cov-report=term-missing --cov-report=xml:tests/reports/coverage.xml --cov-fail-under=70

check: lint typecheck security secrets-scan audit deadcode test
