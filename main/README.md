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

Window prices for Section 5.3 come from `sql/50_prices.sql` (Bitcoin feerate, Ethereum base,
priority and blob fees) and `sql/51_l2_prices.sql` (layer-2 gas prices); save them as
`results/bigquery/50_prices.csv` and `results/bigquery/51_l2_prices.csv`.

All four main queries return the same long table:
`chain, population, metric, stat, bin_lo, keys, signatures`, with quantiles, a log2 histogram
and the number of keys above 2^10, 2^16, 2^20 and 2^24.

## 3. Design-space exploration (Section 6)

```bash
cd main/explore
sh setup_upstream.sh          # fetches the SPHINCS-Parameters model (pinned commit)
python explore.py --workers 8 # writes ../results/explore/{candidates,optimum,timing}.csv
```

`engine.py` and `paths.py` come from the SoK repository
[hbs-blockchain-signature-limits](https://github.com/leejh257/hbs-blockchain-signature-limits).
Budget classes, signing bounds and chain cost functions follow Sections 4.5, 5.2 and 5.4.

`results/explore/timing_v1_i7-12700KF.csv` and `timing_v2_i7-12700KF.csv` hold the run times of
Table 9 (first, one-phase version and the two-phase version). They were recorded before the final
revision of the cost model and therefore list 19,446 feasible sets; the current code yields 18,753.
The enumeration and its run time are unaffected, because only the feasibility filter changed.

Sensitivity runs of Section 8 rerun the exploration with other margins and wallet bounds, for example
`python explore.py --margin 10 --out ../results/sensitivity/margin10` and
`python explore.py --wallet-s 1 --classes ordinary --out ../results/sensitivity/wallet1s`.

## 4. Cost model, figures and sensitivity (Sections 4, 5, 7 and 8)

Run from the repository root (`pip install pandas matplotlib`):

```bash
python main/analysis/make_figures.py     # Figs. 1 and 2, Tables 2 and 3
python main/analysis/cost_model.py       # Tables 5 and 6 (main/figures/table_cost_*.csv)
python main/analysis/rollup_optimum.py   # rollup optima per price percentile and stage
python main/analysis/sensitivity.py      # recommended sets (Table 10), Section 8 tables, the EIP-8311 floor case and the stage decomposition (Table 11)
```

## 5. On-chain verification gas (Section 5.2)

`gasbench/` contains the Solidity verifiers, the signatures and the Foundry measurements that
calibrate the EVM gas model. See `gasbench/README.md`.
