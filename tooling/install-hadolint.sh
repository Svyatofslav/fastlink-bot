#!/usr/bin/env bash
# tooling/install-hadolint.sh
set -euo pipefail
HADOLINT_VERSION="2.14.0"
curl -sSL "https://github.com/hadolint/hadolint/releases/download/v${HADOLINT_VERSION}/hadolint-Linux-x86_64" -o /tmp/hadolint
sudo mv /tmp/hadolint /usr/local/bin/hadolint
sudo chmod +x /usr/local/bin/hadolint
echo "hadolint $(hadolint --version | grep -oP '\d+\.\d+\.\d+' | head -n1) installed"
