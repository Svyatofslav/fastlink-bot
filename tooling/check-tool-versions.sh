#!/usr/bin/env bash
# tooling/check-tool-versions.sh
#
# Сверяет версии node/npm/jscpd/gitleaks, установленные локально,
# с версиями, зафиксированными в tooling/install-nodejs.sh и
# tooling/install-gitleaks.sh. Блокирует коммит при расхождении —
# защита от сценария "обновил пакет локально, забыл обновить
# install-скрипт, на сервере/CI окажется другая версия".
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODEJS_INSTALL_SCRIPT="${SCRIPT_DIR}/install-nodejs.sh"
GITLEAKS_INSTALL_SCRIPT="${SCRIPT_DIR}/install-gitleaks.sh"

fail=0

extract_pinned_version() {
    local var_name="$1" file="$2"
    grep -oP "^${var_name}=\"\K[^\"]+" "$file"
}

check_version() {
    local tool_name="$1" expected="$2" actual="$3"
    if [[ "$expected" != "$actual" ]]; then
        echo "ERROR: версия ${tool_name} не совпадает — зафиксирована ${expected}, установлена ${actual}" >&2
        fail=1
    fi
}

require_tool() {
    local tool_name="$1"
    if ! command -v "$tool_name" >/dev/null 2>&1; then
        echo "ERROR: ${tool_name} не найден в PATH" >&2
        exit 1
    fi
}

require_tool node
require_tool npm
require_tool jscpd
require_tool gitleaks

NODE_EXPECTED="$(extract_pinned_version NODE_VERSION "$NODEJS_INSTALL_SCRIPT")"
NPM_EXPECTED="$(extract_pinned_version NPM_VERSION "$NODEJS_INSTALL_SCRIPT")"
JSCPD_EXPECTED="$(extract_pinned_version JSCPD_VERSION "$NODEJS_INSTALL_SCRIPT")"
GITLEAKS_EXPECTED="$(extract_pinned_version GITLEAKS_VERSION "$GITLEAKS_INSTALL_SCRIPT")"

NODE_ACTUAL="$(node --version | sed 's/^v//')"
NPM_ACTUAL="$(npm --version)"
JSCPD_ACTUAL="$(jscpd --version | grep -oP '\d+\.\d+\.\d+' | head -n1)"
GITLEAKS_ACTUAL="$(gitleaks version | grep -oP '\d+\.\d+\.\d+' | head -n1)"

check_version "node" "$NODE_EXPECTED" "$NODE_ACTUAL"
check_version "npm" "$NPM_EXPECTED" "$NPM_ACTUAL"
check_version "jscpd" "$JSCPD_EXPECTED" "$JSCPD_ACTUAL"
check_version "gitleaks" "$GITLEAKS_EXPECTED" "$GITLEAKS_ACTUAL"

if [[ "$fail" -eq 1 ]]; then
    echo "" >&2
    echo "Версии локальных инструментов разошлись с tooling/install-*.sh." >&2
    echo "Если обновление осознанное — поправь версию в install-скрипте и закоммить это вместе с остальными правками." >&2
    echo "Если нет — переустанови инструмент версией из install-скрипта (bash tooling/install-nodejs.sh / install-gitleaks.sh)." >&2
    exit 1
fi

echo "Tool versions OK: node ${NODE_ACTUAL}, npm ${NPM_ACTUAL}, jscpd ${JSCPD_ACTUAL}, gitleaks ${GITLEAKS_ACTUAL}"
