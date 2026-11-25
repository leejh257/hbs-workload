# Main measurement (window 2026-05-01 to 2026-10-31, UTC)

## 1. Ethereum public mempool (local, Python + DuckDB)

```bash
pip install duckdb pandas
cd main
python scripts/mempool_fetch_reduce.py 2026-05-01 2026-10-31   # about 184 days, restartable
python scripts/mempool_analyze.py --memory 8GB                  # writes results/mempool/*.csv
```

* `mempool_fetch_reduce.py` downloads one day at a time, reduces it to `work/reduced/<day>.parquet`
  (hash prefix, sender, nonce, landed flag, first-seen time) and deletes the raw CSV. Rerun the same
  command to resume or to retry failed days.
* `mempool_analyze.py` reproduces the pilot metrics for the whole window and adds a monthly view
  and two more activity classes (1,001 to 10,000 and above 10,000).
* `work/` is excluded from Git.

## 2. BigQuery (Ethereum EOAs, ERC-4337, layer 2, UTXO chains)

Run in this order in the BigQuery console; each query states its expected scan size.

| Query | Population | Save result as |
|---|---|---|
| `sql/00_check.sql` | dataset freshness; optional column and input-type checks | not needed |
| `sql/10_eth_eoa.sql` | Ethereum EOAs: window count, annual rate, lifetime (nonce) | `results/bigquery/10_eth_eoa.csv` |
| `sql/20_erc4337.sql` | ERC-4337 accounts; EIP-7702 accounts with EOA transactions added | `results/bigquery/20_erc4337.csv` |
| `sql/30_l2.sql` | Arbitrum One, Optimism, Polygon PoS EOAs | `results/bigquery/30_l2.csv` |
| `sql/40_utxo.sql` | Bitcoin and Litecoin single-key addresses | `results/bigquery/40_utxo.csv` |

All four main queries return the same long table:
`chain, population, metric, stat, bin_lo, keys, signatures`, with quantiles, a log2 histogram
and the number of keys above 2^10, 2^16, 2^20 and 2^24.
