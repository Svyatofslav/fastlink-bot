#!/usr/bin/env python3
"""tooling/check-versions.py

Полная сверка версий Python-пакетов и pre-commit-хуков между всеми
источниками правды в проекте:

  - requirements.txt / requirements-dev.txt (pip-пины пакетов)
  - .pre-commit-config.yaml (rev: у каждого repo + additional_dependencies
    у mypy-хука — pre-commit гоняет хуки в СВОИХ изолированных
    окружениях, версия там не зависит от .venv автоматически)
  - Dockerfile (версия base-образа python:X.Y-slim, builder и runtime)
  - .github/workflows/ci.yml - соответствие python версии в джобе
    с python версией в Dockerfile
  - pyproject.toml (mypy python_version, ruff target-version)
  - фактически установленные версии в текущем .venv — это то, что
    реально используется при `make check` / `pytest`, поэтому venv
    выступает источником истины для сравнения


Любое расхождение — это сценарий "поправил версию в одном месте,
забыл в другом": `make check` и pre-commit-хук (или venv и прод-образ)
начинают тихо работать на разных версиях без единого явного сигнала
об этом, кроме как случайно заметить разницу в поведении.

Ограничение: файл .pre-commit-config.yaml разбирается построчным
разбором по фиксированным паттернам (repo:/rev:/id:/additional_dependencies:),
а не полноценным YAML-парсером — сознательный трейд-офф, чтобы не
тащить новую зависимость только под один tooling-скрипт. Работает
надёжно при текущей структуре файла; если структура сильно изменится
(например, вложенные списки хуков нестандартной формы) — проверь,
что парсер всё ещё видит нужные блоки.

Режимы работы (определяются через APP_ENV из .env или переменной окружения):
  - development → dev:    без проверки trivy (используется только на проде)
  - test        → ci:     без проверки trivy (не устанавливается в lint-джобе CI)
  - production  → server: полный набор проверок, включая trivy
                           (ставится через deploy/scripts/fastlink-ci update-trivy)

Если APP_ENV не задан или не распознан — используется режим dev.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess  # nosec B404
import sys
from importlib import metadata
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")

errors: list[str] = []

APP_ENV_TO_MODE = {
    "development": "dev",
    "test": "ci",
    "production": "server",
}


def get_mode() -> str:
    app_env = os.environ.get("APP_ENV", "development")
    return APP_ENV_TO_MODE.get(app_env, "dev")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def venv_version(pkg_name: str) -> str | None:
    try:
        return metadata.version(pkg_name)
    except metadata.PackageNotFoundError:
        return None


def parse_requirements(path: Path) -> dict[str, str]:
    pinned: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "-r ")):
            continue
        match = re.match(
            r"^([A-Za-z0-9_.-]+)(\[[^\]]+\])?==([A-Za-z0-9_.-]+)\s*$", line
        )
        if not match:
            continue
        pinned[normalize(match.group(1))] = match.group(3)
    return pinned


def check_requirements_vs_venv(path: Path) -> None:
    for pkg, expected in parse_requirements(path).items():
        actual = venv_version(pkg)
        if actual is None:
            errors.append(
                f"пакет '{pkg}' указан в '{path.name}' ({expected}), "
                f"но не установлен в venv"
            )
        elif actual != expected:
            errors.append(
                f"версия '{pkg}' в '{path.name}' ({expected}) не соответствует "
                f"версии в venv ({actual})"
            )


PRECOMMIT_HOOK_TO_PACKAGE = {
    "ruff-check": "ruff",
    "ruff-format": "ruff",
    "mypy": "mypy",
    "bandit": "bandit",
    "semgrep": "semgrep",
    "pip-audit": "pip-audit",
    "vulture": "vulture",
    "deptry": "deptry",
    "import-linter": "import-linter",
    "xenon": "xenon",
    "sqlfluff-lint": "sqlfluff",
    "sqlfluff-fix": "sqlfluff",
}


def strip_v_prefix(rev: str) -> str:
    return rev.removeprefix("v")


def parse_pre_commit_config(path: Path) -> list[tuple[str, str, list[str]]]:
    entries: list[tuple[str, str, list[str]]] = []
    current_repo: str | None = None
    current_rev: str | None = None
    current_hooks: list[str] = []

    def flush() -> None:
        if current_repo is not None and current_rev is not None:
            entries.append((current_repo, current_rev, list(current_hooks)))

    for raw_line in path.read_text().splitlines():
        repo_match = re.match(r"^\s*-\s*repo:\s*(\S+)", raw_line)
        rev_match = re.match(
            r"^\s*rev:\s*\"?([^\"]+)\"?", raw_line
        )  # <-- поправлено: убираем кавычки
        id_match = re.match(r"^\s*-\s*id:\s*(\S+)", raw_line)

        if repo_match:
            flush()
            current_repo = repo_match.group(1)
            current_rev = None
            current_hooks = []
        elif rev_match and current_repo is not None:
            current_rev = rev_match.group(1)
        elif id_match and current_repo is not None:
            current_hooks.append(id_match.group(1))

    flush()
    return entries


def parse_mypy_additional_dependencies(path: Path) -> dict[str, str]:
    in_mypy_hook = False
    in_deps_block = False
    deps: dict[str, str] = {}

    for line in path.read_text().splitlines():
        if re.match(r"^\s*-\s*id:\s*mypy\s*$", line):
            in_mypy_hook = True
            continue
        if in_mypy_hook and re.match(r"^\s*additional_dependencies:\s*$", line):
            in_deps_block = True
            continue
        if in_deps_block:
            dep_match = re.match(
                r"^\s*-\s*([A-Za-z0-9_.-]+)==([A-Za-z0-9_.-]+)\s*$", line
            )
            if dep_match:
                deps[normalize(dep_match.group(1))] = dep_match.group(2)
                continue
            if re.match(r"^\s*args:", line) or re.match(r"^\s*-\s*repo:", line):
                in_deps_block = False
                in_mypy_hook = False

    return deps


def check_pre_commit_revs(pre_commit_path: Path, requirements_dev_path: Path) -> None:
    dev_pins = parse_requirements(requirements_dev_path)
    for _repo_url, rev, hook_ids in parse_pre_commit_config(pre_commit_path):
        version = strip_v_prefix(rev)
        packages = {
            PRECOMMIT_HOOK_TO_PACKAGE[h]
            for h in hook_ids
            if h in PRECOMMIT_HOOK_TO_PACKAGE
        }
        for package in packages:
            expected = dev_pins.get(normalize(package))
            if expected is None:
                continue
            if expected != version:
                errors.append(
                    f"версия '{package}' в '.pre-commit-config.yaml' "
                    f"(rev: {rev}) не соответствует версии в "
                    f"requirements-dev.txt ({expected})"
                )


def check_mypy_additional_dependencies(
    pre_commit_path: Path, requirements_path: Path, requirements_dev_path: Path
) -> None:
    combined_pins = {
        **parse_requirements(requirements_path),
        **parse_requirements(requirements_dev_path),
    }
    for pkg, version in parse_mypy_additional_dependencies(pre_commit_path).items():
        expected = combined_pins.get(pkg)
        if expected is None:
            continue
        if expected != version:
            errors.append(
                f"версия '{pkg}' в additional_dependencies mypy-хука "
                f".pre-commit-config.yaml ({version}) не соответствует "
                f"версии в requirements.txt/requirements-dev.txt ({expected})"
            )


def check_gitleaks_version(install_script_path: Path) -> None:
    if not install_script_path.exists():
        return

    match = re.search(
        r'^GITLEAKS_VERSION="([^"]+)"',
        install_script_path.read_text(),
        re.MULTILINE,
    )
    if not match:
        return

    script_version = match.group(1)

    gitleaks_bin = shutil.which("gitleaks")
    if gitleaks_bin is None:
        errors.append(
            f"gitleaks не установлен в системе (ожидалась версия {script_version} из install-скрипта)"
        )
        return

    try:
        result = subprocess.run(  # noqa: S603, nosec B603
            [gitleaks_bin, "version"],
            capture_output=True,
            text=True,
            check=True,
        )  # nosec B603
        installed_match = re.search(r"(\d+\.\d+\.\d+)", result.stdout)
        if not installed_match:
            errors.append("не удалось распарсить версию gitleaks из вывода команды")
            return

        installed_version = installed_match.group(1)
        if script_version != installed_version:
            errors.append(
                f"версия 'gitleaks' в 'tooling/install-gitleaks.sh' ({script_version}) "
                f"не соответствует установленной версии ({installed_version})"
            )
    except subprocess.CalledProcessError:
        errors.append("не удалось получить версию gitleaks")


def check_hadolint_version(install_script_path: Path) -> None:
    if not install_script_path.exists():
        return

    match = re.search(
        r'^HADOLINT_VERSION="([^"]+)"',
        install_script_path.read_text(),
        re.MULTILINE,
    )
    if not match:
        return

    script_version = match.group(1)

    hadolint_bin = shutil.which("hadolint")
    if hadolint_bin is None:
        errors.append(
            f"hadolint не установлен в системе (ожидалась версия {script_version} из install-скрипта)"
        )
        return

    try:
        result = subprocess.run(  # noqa: S603, nosec B603
            [hadolint_bin, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )  # nosec B603
        installed_match = re.search(r"(\d+\.\d+\.\d+)", result.stdout)
        if not installed_match:
            errors.append("не удалось распарсить версию hadolint из вывода команды")
            return

        installed_version = installed_match.group(1)
        if script_version != installed_version:
            errors.append(
                f"версия 'hadolint' в 'tooling/install-hadolint.sh' ({script_version}) "
                f"не соответствует установленной версии ({installed_version})"
            )
    except subprocess.CalledProcessError:
        errors.append("не удалось получить версию hadolint")


def check_node_version(_install_script_path: Path, script_node: str) -> None:
    node_bin = shutil.which("node")
    if node_bin is None:
        errors.append(
            f"node не установлен в системе (ожидалась версия {script_node} из install-скрипта)"
        )
        return

    try:
        result = subprocess.run(  # noqa: S603, nosec B603
            [node_bin, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )  # nosec B603
        installed_node = result.stdout.strip().lstrip("v")
        if script_node != installed_node:
            errors.append(
                f"версия 'node' в 'tooling/install-nodejs.sh' ({script_node}) "
                f"не соответствует установленной версии ({installed_node})"
            )
    except subprocess.CalledProcessError:
        errors.append("не удалось получить версию node")


def check_npm_version(_install_script_path: Path, script_npm: str) -> None:
    npm_bin = shutil.which("npm")
    if npm_bin is None:
        errors.append(
            f"npm не установлен в системе (ожидалась версия {script_npm} из install-скрипта)"
        )
        return

    try:
        result = subprocess.run(  # noqa: S603, nosec B603
            [npm_bin, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )  # nosec B603
        installed_npm = result.stdout.strip()
        if script_npm != installed_npm:
            errors.append(
                f"версия 'npm' в 'tooling/install-nodejs.sh' ({script_npm}) "
                f"не соответствует установленной версии ({installed_npm})"
            )
    except subprocess.CalledProcessError:
        errors.append("не удалось получить версию npm")


def check_jscpd_version(_install_script_path: Path, script_jscpd: str) -> None:
    jscpd_bin = shutil.which("jscpd")
    if jscpd_bin is None:
        errors.append(
            f"jscpd не установлен в системе (ожидалась версия {script_jscpd} из install-скрипта)"
        )
        return

    try:
        result = subprocess.run(  # noqa: S603, nosec B603
            [jscpd_bin, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )  # nosec B603
        installed_jscpd_match = re.search(r"(\d+\.\d+\.\d+)", result.stdout)
        if not installed_jscpd_match:
            errors.append("не удалось распарсить версию jscpd из вывода команды")
            return

        installed_jscpd = installed_jscpd_match.group(1)
        if script_jscpd != installed_jscpd:
            errors.append(
                f"версия 'jscpd' в 'tooling/install-nodejs.sh' ({script_jscpd}) "
                f"не соответствует установленной версии ({installed_jscpd})"
            )
    except subprocess.CalledProcessError:
        errors.append("не удалось получить версию jscpd")


def check_nodejs_versions(install_script_path: Path) -> None:
    if not install_script_path.exists():
        return

    script_text = install_script_path.read_text()

    node_match = re.search(r'^NODE_VERSION="([^"]+)"', script_text, re.MULTILINE)
    npm_match = re.search(r'^NPM_VERSION="([^"]+)"', script_text, re.MULTILINE)
    jscpd_match = re.search(r'^JSCPD_VERSION="([^"]+)"', script_text, re.MULTILINE)

    if not (node_match and npm_match and jscpd_match):
        return

    check_node_version(install_script_path, node_match.group(1))
    check_npm_version(install_script_path, npm_match.group(1))
    check_jscpd_version(install_script_path, jscpd_match.group(1))


def check_trivy_version(install_script_path: Path) -> None:
    if not install_script_path.exists():
        return

    match = re.search(
        r'^TRIVY_VERSION="([^"]+)"',
        install_script_path.read_text(),
        re.MULTILINE,
    )
    if not match:
        return

    script_version = match.group(1)

    trivy_bin = shutil.which("trivy")
    if trivy_bin is None:
        errors.append(
            f"trivy не установлен в системе (ожидалась версия {script_version} из install-скрипта)"
        )
        return

    try:
        result = subprocess.run(  # noqa: S603, nosec B603
            [trivy_bin, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )  # nosec B603
        installed_match = re.search(
            r"Version:\s*(\d+\.\d+\.\d+)", result.stdout, re.IGNORECASE
        )
        if not installed_match:
            errors.append("не удалось распарсить версию trivy из вывода команды")
            return

        installed_version = installed_match.group(1)
        if script_version != installed_version:
            errors.append(
                f"версия 'trivy' в 'tooling/install-trivy.sh' ({script_version}) "
                f"не соответствует установленной версии ({installed_version})"
            )
    except subprocess.CalledProcessError:
        errors.append("не удалось получить версию trivy")


def check_python_version(dockerfile_path: Path, pyproject_path: Path) -> str | None:
    dockerfile_text = dockerfile_path.read_text()
    docker_versions = set(re.findall(r"FROM python:(\d+\.\d+)-slim", dockerfile_text))

    if not docker_versions:
        errors.append(
            "не удалось найти версию Python в Dockerfile "
            "(ожидался FROM python:X.Y-slim)"
        )
        return None

    if len(docker_versions) > 1:
        errors.append(
            f"в Dockerfile указаны разные версии Python в разных стадиях: "
            f"{sorted(docker_versions)}"
        )

    docker_version: str | None = min(docker_versions) if docker_versions else None

    venv_major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    if venv_major_minor != docker_version:
        errors.append(
            f"версия Python в venv ({venv_major_minor}) не соответствует "
            f"версии в Dockerfile ({docker_version})"
        )

    check_mypy_python_version(pyproject_path, docker_version)
    check_ruff_target_version(pyproject_path, docker_version)

    return docker_version


def check_mypy_python_version(pyproject_path: Path, docker_version: str | None) -> None:
    if docker_version is None:
        return

    pyproject_text = pyproject_path.read_text()
    mypy_match = re.search(r'python_version\s*=\s*"([^"]+)"', pyproject_text)
    if mypy_match and mypy_match.group(1) != docker_version:
        errors.append(
            f"mypy python_version в 'pyproject.toml' ({mypy_match.group(1)}) "
            f"не соответствует версии в Dockerfile ({docker_version})"
        )


def check_ruff_target_version(pyproject_path: Path, docker_version: str | None) -> None:
    if docker_version is None:
        return

    pyproject_text = pyproject_path.read_text()
    ruff_match = re.search(r'target-version\s*=\s*"py(\d)(\d+)"', pyproject_text)
    if ruff_match:
        ruff_version = f"{ruff_match.group(1)}.{ruff_match.group(2)}"
        if ruff_version != docker_version:
            errors.append(
                f"ruff target-version в 'pyproject.toml' "
                f"(py{ruff_match.group(1)}{ruff_match.group(2)}) не "
                f"соответствует версии в Dockerfile ({docker_version})"
            )


def check_ci_python_version(ci_path: Path, docker_version: str | None) -> None:
    if docker_version is None or not ci_path.exists():
        return

    ci_text = ci_path.read_text()
    match = re.search(r'python-version:\s*"([^"]+)"', ci_text)
    if not match:
        errors.append(
            f"не удалось найти python-version в '{ci_path.name}' "
            f'(ожидался python-version: "X.Y")'
        )
        return

    ci_version = match.group(1)
    if ci_version != docker_version:
        errors.append(
            f"python-version в '{ci_path.name}' ({ci_version}) не "
            f"соответствует версии в Dockerfile ({docker_version})"
        )


def main() -> int:
    mode = get_mode()

    check_requirements_vs_venv(ROOT / "requirements.txt")
    check_requirements_vs_venv(ROOT / "requirements-dev.txt")
    check_pre_commit_revs(
        ROOT / ".pre-commit-config.yaml", ROOT / "requirements-dev.txt"
    )
    check_mypy_additional_dependencies(
        ROOT / ".pre-commit-config.yaml",
        ROOT / "requirements.txt",
        ROOT / "requirements-dev.txt",
    )
    check_gitleaks_version(ROOT / "tooling" / "install-gitleaks.sh")
    check_hadolint_version(ROOT / "tooling" / "install-hadolint.sh")
    check_nodejs_versions(ROOT / "tooling" / "install-nodejs.sh")

    if mode == "server":
        check_trivy_version(ROOT / "tooling" / "install-trivy.sh")

    docker_version = check_python_version(ROOT / "Dockerfile", ROOT / "pyproject.toml")
    check_ci_python_version(ROOT / ".github" / "workflows" / "ci.yml", docker_version)

    if errors:
        print(f"[mode={mode}] Расхождения версий:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        f"[mode={mode}] Все версии в проверенных файлах - соответствуют "
        f"в местах где повторяются и локальному окружению"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
