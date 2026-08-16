.PHONY: install-hooks secrets-scan lint lint-fix format typecheck security semgrep license-check audit check-versions deadcode deps architecture architecture-diagram complexity-report complexity-gate sql-lint sql-fix dockerfile-lint duplication migrations-check migrations-check-server security-image test test-docker check check-server

PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,python)
LINT_IMPORTS := $(if $(wildcard .venv/bin/lint-imports),.venv/bin/lint-imports,lint-imports)
SEMGREP := $(if $(wildcard .venv/bin/semgrep),.venv/bin/semgrep,semgrep)
PIP_LICENSES := $(if $(wildcard .venv/bin/pip-licenses),.venv/bin/pip-licenses,pip-licenses)

install-hooks:
	pre-commit install
	pre-commit install --hook-type pre-push

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

semgrep:
	$(SEMGREP) --config tooling/semgrep.yml --error .

license-check:
	$(PIP_LICENSES) --fail-on="GNU Affero General Public License v3;GNU Affero General Public License v3 or later (AGPLv3+);GNU General Public License (GPL);GNU General Public License v2 (GPLv2);GNU General Public License v2 or later (GPLv2+);GNU General Public License v3 (GPLv3);GNU General Public License v3 or later (GPLv3+)"

audit:
	$(PYTHON) -m pip_audit -r requirements.txt
	$(PYTHON) -m pip_audit -r requirements-dev.txt

check-versions:
	$(PYTHON) tooling/check-versions.py

deadcode:
	$(PYTHON) -m vulture

deps:
	$(PYTHON) -m deptry .

architecture:
	$(LINT_IMPORTS) --config tooling/import-linter.cfg

architecture-diagram:
	.venv/bin/pydeps database --max-cluster-size=10 --max-bacon=2 -T svg \
	  -o tests/reports/dependencies-db.svg \
	  --only handlers webhooks scheduler tasks middlewares services clients infrastructure database domain schemas keyboards states utils --noshow
	.venv/bin/pydeps services --max-cluster-size=10 --max-bacon=2 -T svg \
	  -o tests/reports/dependencies-services.svg \
	  --only handlers webhooks scheduler tasks middlewares services clients infrastructure database domain schemas keyboards states utils --noshow

complexity-report:
	$(PYTHON) -m radon cc . -a -nc -j --exclude "alembic/*,.venv/*,venv/*,tests/*" > tests/reports/complexity-cc.json
	$(PYTHON) -m radon mi . -j --exclude "alembic/*,.venv/*,venv/*,tests/*" > tests/reports/complexity-mi.json
	$(PYTHON) -m radon cc . -a -nc --exclude "alembic/*,.venv/*,venv/*,tests/*"
	$(PYTHON) -m radon mi . --exclude "alembic/*,.venv/*,venv/*,tests/*"

complexity-gate:
	$(PYTHON) -m xenon --max-absolute B --max-modules B --max-average A --exclude "alembic/*,.venv/*,venv/*,tests/*" .

sql-lint:
	$(PYTHON) -m sqlfluff lint database/sql --config tooling/.sqlfluff

sql-fix:
	$(PYTHON) -m sqlfluff fix database/sql --config tooling/.sqlfluff

dockerfile-lint:
	hadolint --config tooling/.hadolint.yaml Dockerfile

duplication:
	jscpd --config tooling/.jscpd.json .

migrations-check:
	@bash -c 'set -o pipefail; $(PYTHON) -m alembic check 2>&1 | grep -v "^INFO"'

migrations-check-server:
	docker compose run --rm --user root bot bash -lc 'set -o pipefail; /opt/venv/bin/python -m alembic check 2>&1 | grep -v "^INFO"'

security-image:
	trivy image --severity MEDIUM,HIGH,CRITICAL --ignore-unfixed --exit-code 1 --ignorefile tooling/.trivyignore "$$(grep '^FASTLINK_IMAGE=' .env | cut -d= -f2-)"
	trivy image --severity LOW,UNKNOWN --exit-code 0 --ignorefile tooling/.trivyignore "$$(grep '^FASTLINK_IMAGE=' .env | cut -d= -f2-)"

test:
	$(PYTHON) -m pytest --cov --cov-report=term-missing --cov-report=xml:tests/reports/coverage.xml --cov-fail-under=70

test-docker:
	docker compose run --rm --user root \
	  -e APP_ENV=test \
	  -e USE_WEBHOOK=false \
	  -e SKIP_WEBHOOK_REGISTRATION=true \
	  -v "$(CURDIR)/tests/reports:/app/tests/reports" \
	  bot bash -lc "pip install -r requirements-dev.txt --quiet && python -m pytest --cov --cov-report=term-missing --cov-report=xml:tests/reports/coverage.xml --cov-fail-under=70"

check: install-hooks lint typecheck security semgrep license-check secrets-scan audit check-versions deadcode deps architecture complexity-report complexity-gate sql-lint dockerfile-lint duplication migrations-check test

check-server: lint typecheck security semgrep license-check secrets-scan audit check-versions deadcode deps architecture complexity-report complexity-gate sql-lint dockerfile-lint duplication migrations-check-server security-image test-docker
