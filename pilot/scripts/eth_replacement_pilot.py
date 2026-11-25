"""Pilot: how many signatures does an Ethereum key produce per landed transaction?

Input : Flashbots Mempool Dumpster daily CSV files in ./data (see download_dumpster.sh).
Idea  : every distinct transaction hash is a distinct signature. Transactions that share
        (sender, nonce) are replacements (speed-up, cancel, re-broadcast with new fee).
        Only one of them can land, so the extra hashes are signatures that never reach the chain.
Output: summary metrics printed to stdout and written to results/*.csv

Caveats (state them in the paper):
  * Private order flow is not observed, so the counts are lower bounds.
  * Replacement chains that straddle the window edges are truncated; trim_days drops the
    nonces first seen on the first and last day to reduce this effect.
"""
import argparse
import pathlib
import duckdb

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data")
ap.add_argument("--out", default="results")
ap.add_argument("--trim-days", type=int, default=1,
                help="drop (sender, nonce) pairs first seen in the first/last N days")
args = ap.parse_args()

out = pathlib.Path(args.out)
out.mkdir(exist_ok=True)
con = duckdb.connect()

con.execute(f"""
CREATE TABLE raw AS
SELECT * FROM read_csv('{args.data}/*.csv', header=true, all_varchar=true, union_by_name=true);
""")

# One row per distinct hash (the same hash can appear on two daily files).
con.execute("""
CREATE TABLE tx AS
SELECT hash,
       lower(any_value("from"))                       AS sender,
       CAST(any_value(nonce) AS UBIGINT)              AS nonce,
       min(CAST(timestamp_ms AS BIGINT))              AS first_seen_ms,
       max(CASE WHEN included_at_block_height IN ('', '0') THEN NULL
                ELSE included_at_block_height END)    AS included_block
FROM raw
WHERE chain_id = '1' OR chain_id IS NULL
GROUP BY hash;
""")

con.execute(f"""
CREATE TABLE pairs AS
WITH p AS (
  SELECT sender, nonce,
         count(*)                                   AS n_sig,
         bool_or(included_block IS NOT NULL)        AS landed,
         min(first_seen_ms)                         AS first_ms
  FROM tx GROUP BY sender, nonce
), bounds AS (
  SELECT min(first_seen_ms) AS t0, max(first_seen_ms) AS t1 FROM tx
)
SELECT p.* FROM p, bounds
WHERE p.first_ms >= t0 + {args.trim_days} * 86400000
  AND p.first_ms <  t1 - {args.trim_days} * 86400000;
""")

summary = con.execute("""
SELECT
  count(*)                                                    AS pairs_all,
  count(*) FILTER (WHERE landed)                              AS pairs_landed,
  sum(n_sig)                                                  AS signatures_all,
  sum(n_sig) FILTER (WHERE landed)                            AS signatures_landed_pairs,
  round(sum(n_sig) FILTER (WHERE landed) * 1.0
        / count(*) FILTER (WHERE landed), 4)                  AS sig_per_landed_tx,
  round(100.0 * count(*) FILTER (WHERE landed AND n_sig > 1)
        / count(*) FILTER (WHERE landed), 3)                  AS pct_landed_with_replacement,
  round(sum(n_sig) * 1.0 / count(*) FILTER (WHERE landed), 4) AS sig_per_landed_tx_incl_unlanded,
  max(n_sig)                                                  AS max_sig_per_nonce
FROM pairs;
""").df()
print("== summary ==")
print(summary.T.to_string(header=False))
summary.to_csv(out / "summary.csv", index=False)

hist = con.execute("""
SELECT CASE WHEN n_sig >= 5 THEN '5+' ELSE CAST(n_sig AS VARCHAR) END AS sig_per_nonce,
       landed, count(*) AS pairs
FROM pairs GROUP BY 1, 2 ORDER BY 2 DESC, 1;
""").df()
print("\n== signatures per (sender, nonce) ==")
print(hist.to_string(index=False))
hist.to_csv(out / "hist_sig_per_nonce.csv", index=False)

# Per-key view: extra (never landed) signatures relative to landed transactions.
con.execute("""
CREATE TABLE per_key AS
SELECT sender,
       count(*) FILTER (WHERE landed)                  AS landed_tx,
       sum(n_sig)                                      AS signatures,
       sum(n_sig) - count(*) FILTER (WHERE landed)     AS extra_signatures
FROM pairs GROUP BY sender;
""")
keyq = con.execute("""
SELECT count(*)                                                  AS keys,
       round(100.0 * count(*) FILTER (WHERE extra_signatures > 0) / count(*), 3) AS pct_keys_with_extra,
       quantile_cont(signatures * 1.0 / greatest(landed_tx, 1), [0.5, 0.9, 0.99, 0.999]) AS ratio_quantiles,
       max(signatures * 1.0 / greatest(landed_tx, 1))            AS ratio_max
FROM per_key;
""").df()
print("\n== per key (signatures / landed tx) ==")
print(keyq.T.to_string(header=False))
keyq.to_csv(out / "per_key_summary.csv", index=False)
con.execute(f"COPY per_key TO '{out}/per_key.csv' (HEADER)")

# Diagnostics: how is "not included" encoded, and which keys carry the most extra signatures?
print("\n== included_at_block_height encoding (top values) ==")
print(con.execute("""
SELECT coalesce(included_at_block_height, '<NULL>') AS v, count(*) AS n
FROM raw GROUP BY 1 ORDER BY n DESC LIMIT 5;""").df().to_string(index=False))

top = con.execute("""
SELECT * FROM per_key WHERE extra_signatures > 0
ORDER BY extra_signatures DESC LIMIT 50;""").df()
print("\n== top keys by extra signatures ==")
print(top.head(15).to_string(index=False))
top.to_csv(out / "top_extra_keys.csv", index=False)

tail = con.execute("""
SELECT count(*) FILTER (WHERE extra_signatures >= 1)   AS keys_extra_ge1,
       count(*) FILTER (WHERE extra_signatures >= 10)  AS keys_extra_ge10,
       count(*) FILTER (WHERE extra_signatures >= 100) AS keys_extra_ge100,
       max(extra_signatures)                           AS max_extra
FROM per_key;""").df()
print("\n== absolute extra-signature tail ==")
print(tail.T.to_string(header=False))
tail.to_csv(out / "extra_tail.csv", index=False)
