#!/usr/bin/env bash

# 1. Install Python deps
pip install -r requirements.txt --break-system-packages 2>/dev/null || pip install -r requirements.txt

# 2. Print HOME so we know the real path
echo "HOME is: $HOME"
echo "PWD is: $PWD"

# Use an explicit path relative to repo root (PWD during build = repo root on Render)
BGUTIL_DIR="$PWD/bgutil-ytdlp-pot-provider"

if [ ! -d "$BGUTIL_DIR" ]; then
  git clone --depth 1 --single-branch --branch "1.3.1" \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
    "$BGUTIL_DIR"
else
  echo "bgutil dir already exists at $BGUTIL_DIR"
fi

cd "$BGUTIL_DIR/server"
npm install
npx tsc || npx tsc --skipLibCheck

echo "bgutil POT provider built OK"
echo "Node: $(node --version), NPM: $(npm --version)"
echo "Server dir: $BGUTIL_DIR/server"

# 3. Install the yt-dlp plugin
pip install bgutil-ytdlp-pot-provider --break-system-packages 2>/dev/null || \
pip install bgutil-ytdlp-pot-provider
echo "bgutil yt-dlp plugin installed OK"
