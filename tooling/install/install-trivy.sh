#!/usr/bin/env bash
# tooling/install/install-trivy.sh
set -euo pipefail
TRIVY_VERSION="0.74.0"
curl -fsSL "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz" -o /tmp/trivy.tar.gz
tar -xzf /tmp/trivy.tar.gz -C /tmp trivy
sudo mv /tmp/trivy /usr/local/bin/trivy
sudo chmod +x /usr/local/bin/trivy
rm /tmp/trivy.tar.gz
echo "trivy $(trivy --version | grep -oP 'Version:\s*\K[0-9.]+' | head -n1) installed"
