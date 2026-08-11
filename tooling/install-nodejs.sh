#!/usr/bin/env bash
# tooling/install-nodejs.sh
set -euo pipefail
NODE_VERSION="24.19.0"
NPM_VERSION="12.0.2"
JSCPD_VERSION="4.2.5"
NODE_DIST="node-v${NODE_VERSION}-linux-x64"

curl -sSL "https://nodejs.org/dist/v${NODE_VERSION}/${NODE_DIST}.tar.xz" -o /tmp/nodejs.tar.xz
sudo rm -rf "/usr/local/lib/nodejs/${NODE_DIST}"
sudo mkdir -p /usr/local/lib/nodejs
sudo tar -xJf /tmp/nodejs.tar.xz -C /usr/local/lib/nodejs
sudo ln -sf "/usr/local/lib/nodejs/${NODE_DIST}/bin/node" /usr/local/bin/node
sudo ln -sf "/usr/local/lib/nodejs/${NODE_DIST}/bin/npm" /usr/local/bin/npm
sudo ln -sf "/usr/local/lib/nodejs/${NODE_DIST}/bin/npx" /usr/local/bin/npx
rm /tmp/nodejs.tar.xz
sudo npm install -g "npm@${NPM_VERSION}"
sudo npm install -g "jscpd@${JSCPD_VERSION}"
sudo ln -sf "/usr/local/lib/nodejs/${NODE_DIST}/bin/jscpd" /usr/local/bin/jscpd
echo "node $(node --version) / npm $(npm --version) / jscpd $(jscpd --version) installed"
