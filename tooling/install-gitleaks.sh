#!/usr/bin/env bash
# tooling/install-gitleaks.sh
set -euo pipefail
GITLEAKS_VERSION="8.30.1"
curl -fsSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" -o /tmp/gitleaks.tar.gz
tar -xzf /tmp/gitleaks.tar.gz -C /tmp gitleaks
sudo mv /tmp/gitleaks /usr/local/bin/gitleaks
sudo chmod +x /usr/local/bin/gitleaks
rm /tmp/gitleaks.tar.gz
echo "gitleaks $(gitleaks version) installed"
