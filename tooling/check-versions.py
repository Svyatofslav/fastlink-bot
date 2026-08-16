#!/usr/bin/env python3
"""tooling/check-versions.py

Полная сверка версий Python-пакетов и pre-commit-хуков между всеми
источниками правды в проекте:

  - requirements.txt / requirements-dev.txt (pip-пины пакетов)
  - .pre-commit-config.yaml (rev: у каждого repo + additional_dependencies
    у mypy-хука — pre-commit гоняет хуки в СВОИХ изолированных
    окружениях, версия там не зависит от .venv автоматически)
  - Dockerfile (версия base-образа python:X.Y-slim, builder и runtime)
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
"""

from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

errors: list[str] = []


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


def check_gitleaks_rev(pre_commit_path: Path, install_script_path: Path) -> None:
    if not install_script_path.exists():
        return
    for _repo_url, rev, hook_ids in parse_pre_commit_config(pre_commit_path):
        if "gitleaks" not in hook_ids:
            continue
        version = strip_v_prefix(rev)
        match = re.search(
            r'^GITLEAKS_VERSION="([^"]+)"',
            install_script_path.read_text(),
            re.MULTILINE,
        )
        if not match:
            continue
        expected = match.group(1)
        if expected != version:
            errors.append(
                f"версия 'gitleaks' в '.pre-commit-config.yaml' (rev: {rev}) "
                f"не соответствует версии в "
                f"'tooling/install-gitleaks.sh' ({expected})"
            )


def check_python_version(dockerfile_path: Path, pyproject_path: Path) -> None:
    dockerfile_text = dockerfile_path.read_text()
    docker_versions = set(re.findall(r"FROM python:(\d+\.\d+)-slim", dockerfile_text))

    if not docker_versions:
        errors.append(
            "не удалось найти версию Python в Dockerfile "
            "(ожидался FROM python:X.Y-slim)"
        )
        return

    if len(docker_versions) > 1:
        errors.append(
            f"в Dockerfile указаны разные версии Python в разных стадиях: "
            f"{sorted(docker_versions)}"
        )

    docker_version = min(docker_versions)

    venv_major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    if venv_major_minor != docker_version:
        errors.append(
            f"версия Python в venv ({venv_major_minor}) не соответствует "
            f"версии в Dockerfile ({docker_version})"
        )

    pyproject_text = pyproject_path.read_text()

    mypy_match = re.search(r'python_version\s*=\s*"([^"]+)"', pyproject_text)
    if mypy_match and mypy_match.group(1) != docker_version:
        errors.append(
            f"mypy python_version в 'pyproject.toml' ({mypy_match.group(1)}) "
            f"не соответствует версии в Dockerfile ({docker_version})"
        )

    ruff_match = re.search(r'target-version\s*=\s*"py(\d)(\d+)"', pyproject_text)
    if ruff_match:
        ruff_version = f"{ruff_match.group(1)}.{ruff_match.group(2)}"
        if ruff_version != docker_version:
            errors.append(
                f"ruff target-version в 'pyproject.toml' "
                f"(py{ruff_match.group(1)}{ruff_match.group(2)}) не "
                f"соответствует версии в Dockerfile ({docker_version})"
            )


def main() -> int:
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
    check_gitleaks_rev(
        ROOT / ".pre-commit-config.yaml", ROOT / "tooling" / "install-gitleaks.sh"
    )
    check_python_version(ROOT / "Dockerfile", ROOT / "pyproject.toml")

    if errors:
        print("Расхождения версий:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("Все версии соответствуют локальному окружению")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
