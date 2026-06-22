#!/usr/bin/env bash
set -e

# 1. Install Python deps
pip install -r requirements.txt --break-system-packages 2>/dev/null || pip install -r requirements.txt

# 2. Clone bgutil POT provider (script mode -- no separate process needed)
#    Pin to latest stable tag so builds are reproducible.
BGUTIL_VERSION="1.3.1"
BGUTIL_DIR="$HOME/bgutil-ytdlp-pot-provider"

if [ ! -d "$BGUTIL_DIR" ]; then
  git clone --single-branch --branch "$BGUTIL_VERSION" \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
    "$BGUTIL_DIR"
fi

cd "$BGUTIL_DIR/server"
npm ci
npx tsc
echo "bgutil POT provider built OK"

# 3. Install the yt-dlp plugin that hooks into bgutil
pip install bgutil-ytdlp-pot-provider --break-system-packages 2>/dev/null || \
pip install bgutil-ytdlp-pot-provider
echo "bgutil yt-dlp plugin installed OK"
