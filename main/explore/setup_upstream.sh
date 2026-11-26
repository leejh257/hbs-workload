#!/bin/sh
# Fetch the Blockstream SPHINCS-Parameters model at the commit used in the paper.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)/third_party/SPHINCS-Parameters"
COMMIT=3172178
if [ ! -d "$DIR/.git" ]; then
  git clone https://github.com/BlockstreamResearch/SPHINCS-Parameters.git "$DIR"
fi
git -C "$DIR" checkout -q "$COMMIT"
echo "SPHINCS-Parameters at $(git -C "$DIR" rev-parse --short HEAD)"
