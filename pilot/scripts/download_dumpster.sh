#!/usr/bin/env bash
# Download Flashbots Mempool Dumpster daily CSV files (Ethereum mainnet) and unzip them.
# Usage: ./download_dumpster.sh 2026-11-01 2026-11-07
# Each day is about 100 MB zipped. Data license: CC-0.
set -euo pipefail

START=${1:?start date YYYY-MM-DD}
END=${2:?end date YYYY-MM-DD}
OUT=data
mkdir -p "$OUT"

d="$START"
while [[ "$d" < "$END" || "$d" == "$END" ]]; do
  month=${d:0:7}
  url="https://mempool-dumpster.flashbots.net/ethereum/mainnet/${month}/${d}.csv.zip"
  if [[ ! -f "$OUT/${d}.csv" ]]; then
    echo "downloading $url"
    curl -fsSL -o "$OUT/${d}.csv.zip" "$url"
    unzip -o -q "$OUT/${d}.csv.zip" -d "$OUT"
    # The archive may contain a file named transactions.csv or <date>.csv; normalize the name.
    if [[ -f "$OUT/transactions.csv" ]]; then mv "$OUT/transactions.csv" "$OUT/${d}.csv"; fi
    rm -f "$OUT/${d}.csv.zip"
  fi
  d=$(date -I -d "$d + 1 day")
done
ls -lh "$OUT"
