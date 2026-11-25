# hbs-workload

Measurement code and results for the study
**"Workload-Aware Parameter Optimization of Hash-Based Signatures for Blockchain Transactions"**
(Jaeheung Lee, Kyonggi University; in preparation).

The study derives per-key signature budgets for post-quantum hash-based signatures from real
blockchain workloads and selects chain-specific parameters with a blockchain cost model.
This repository currently holds the **pilot** measurements; the full measurement and the
design-space exploration code will be added under separate folders.

Related repository: per-key signature counts for Bitcoin and Ethereum and the variant-search code
used in the earlier systematization study are in
[hbs-blockchain-signature-limits](https://github.com/leejh257/hbs-blockchain-signature-limits).

## Layout

```
pilot/
  scripts/   Ethereum mempool analysis (Python + DuckDB)
  sql/       ERC-4337 query (BigQuery)
  results/
    ethereum/  outputs of the scripts (aggregates only)
    erc4337/   BigQuery results
```

## Data sources

| Source | What | License / access |
|---|---|---|
| Flashbots Mempool Dumpster | Public Ethereum mempool transactions, daily CSV | CC-0, https://mempool-dumpster.flashbots.net |
| `bigquery-public-data.crypto_ethereum.logs` | ERC-4337 `UserOperationEvent` logs | Google BigQuery public dataset |

Pilot windows
* Ethereum mempool: 2026-11-01 to 2026-11-09 (UTC). `eth_replacement_pilot.py` drops the first and
  last day, so its per-key figures cover 2026-11-02 to 2026-11-08.
* ERC-4337: 2026-10-01 to 2026-10-31 (UTC), EntryPoint v0.6, v0.7 and v0.8.

## Reproduce

Requirements: Python 3.10+, `pip install duckdb pandas`, `curl`, `unzip`.

```bash
cd pilot
bash scripts/download_dumpster.sh 2026-11-01 2026-11-09   # creates ./data (about 1 GB)
python scripts/eth_replacement_pilot.py                 # replacement multiplier, per-key table
python scripts/activity_multiplier.py                   # multiplier by activity class
python scripts/coverage.py                              # public-mempool coverage via nonce gaps
python scripts/check_key.py 0x6872b6630a3afcd3117191a8403c2002e13df7de   # single-key check
```

The scripts read `./data` and write to `./results`; the committed pilot outputs are copies placed in
`results/ethereum`.

On Windows, run the download script in Git Bash or WSL, or download the daily `.csv.zip`
files manually into `pilot/data` and unzip them as `YYYY-MM-DD.csv`.

ERC-4337: open `pilot/sql/erc4337_userops.sql` in the BigQuery console, set `t_start` and
`t_end`, check the byte estimate, and run the script. It returns a summary and an
activity-class table.

## Scripts

| Script | Output | Purpose |
|---|---|---|
| `eth_replacement_pilot.py` | `summary.csv`, `hist_sig_per_nonce.csv`, `per_key_summary.csv`, `per_key.csv`, `top_extra_keys.csv`, `extra_tail.csv` | Signatures per landed transaction; replacements share `(sender, nonce)` |
| `activity_multiplier.py` | `activity_multiplier.csv` | Multiplier and share of keys with replacements by activity class |
| `coverage.py` | `coverage_by_activity.csv`, `coverage_per_key.csv` | Share of used nonces visible in the public mempool |
| `check_key.py` | printed | Nonce-range check for a single sender |

`per_key.csv` and `coverage_per_key.csv` have millions of rows and are not committed; rerun the
scripts to regenerate them.

## Pilot findings

Ethereum EOAs (public mempool, one week)
* Replacements add 0.5% to 1.8% signatures per landed transaction across activity classes;
  99% of active keys stay within 1.32x.
* The share of keys whose signature count diverges from the on-chain nonce rises with activity
  and reaches 44.7% for keys with more than 1,000 landed transactions.
* The public mempool covers 94% of nonces used by keys with 2 to 10 transactions but only 57% for
  keys with more than 1,000, and 98.5% of those keys use private channels. Figures for active keys
  are therefore lower bounds.

ERC-4337 smart accounts (October 2026)
* 298,012 accounts executed 1,030,920 UserOperations; 99.9% executed at most 104.
* The most active account executed 2,424 (about 2^14.8 per year); only 8 accounts exceeded 1,000.
* EntryPoint v0.8 accounts for about 29% of UserOperations.

## Limitations

* Private order flow is not visible in public mempool archives.
* Smart accounts can rotate keys, so UserOperations per account bound signatures per key from above.
* EIP-7702 accounts on EntryPoint v0.8 also sign ordinary transactions with the same key; the pilot
  does not merge the two counts.

## License

Code: MIT (see `LICENSE`). Mempool Dumpster data are CC-0; derived aggregates in `results/` are
released under CC-0 as well.

## Citation

If you use this repository, please cite the release you used (see the Releases page).
