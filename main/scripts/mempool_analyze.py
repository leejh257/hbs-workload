"""Analyse the reduced Mempool Dumpster files for the whole measurement window.

Usage : python mempool_analyze.py [--work work] [--out results/mempool] [--memory 8GB]
Input : work/reduced/*.parquet from mempool_fetch_reduce.py
Output (CSV in --out):
  summary.csv               window totals: signatures per landed transaction, replacement share
  monthly.csv               the same figures per calendar month (stability over time)
  hist_sig_per_nonce.csv    signatures per (sender, nonce)
  activity_multiplier.csv   multiplier and share of keys with replacements by activity class
  coverage_by_activity.csv  share of used nonces visible in the public mempool (nonce-gap method)
  extra_tail.csv            keys with at least 1, 10, 100, 1000 extra signatures
  top_extra_keys.csv        100 keys with the most extra signatures

Definitions follow the pilot (pilot/scripts). Replacements are distinct hashes that share
(sender, nonce). Pairs first seen on the first or last day are dropped from the multiplier
figures so that replacement chains are not cut at the window edges. Coverage uses all days.
DuckDB spills to work/duckdb_tmp when memory is short; a full six-month run needs about 10 to 30 GB
of temporary disk and takes tens of minutes on a laptop.
"""
import argparse
import pathlib
import time

import duckdb

ap = argparse.ArgumentParser()
ap.add_argument("--work", default="work")
ap.add_argument("--out", default="results/mempool")
ap.add_argument("--memory", default="8GB")
a = ap.parse_args()

work = pathlib.Path(a.work)
out = pathlib.Path(a.out)
out.mkdir(parents=True, exist_ok=True)
(work / "duckdb_tmp").mkdir(parents=True, exist_ok=True)

con = duckdb.connect(str(work / "analysis.duckdb"))
con.execute(f"SET memory_limit = '{a.memory}'")
con.execute(f"SET temp_directory = '{(work / 'duckdb_tmp').as_posix()}'")
con.execute("SET preserve_insertion_order = false")

t0 = time.time()


def step(msg: str) -> None:
    print(f"[{time.time() - t0:6.0f} s] {msg}", flush=True)


def save(sql: str, name: str, show: bool = True) -> None:
    df = con.execute(sql).df()
    df.to_csv(out / name, index=False)
    if show:
        print(f"\n== {name} ==")
        print(df.to_string(index=False))


step("deduplicating transactions across days")
con.execute(f"""
CREATE OR REPLACE TABLE tx AS
SELECT h, any_value(sender) AS sender, any_value(nonce) AS nonce,
       bool_or(landed) AS landed, min(ts_ms) AS ts_ms
FROM read_parquet('{(work / 'reduced').as_posix()}/*.parquet')
GROUP BY h
""")

step("building (sender, nonce) pairs")
con.execute("""
CREATE OR REPLACE TABLE pairs_all AS
SELECT sender, nonce, count(*) AS n_sig, bool_or(landed) AS landed, min(ts_ms) AS first_ms
FROM tx GROUP BY sender, nonce
""")
con.execute("""
CREATE OR REPLACE TABLE pairs AS
WITH b AS (SELECT min(first_ms) AS t0, max(first_ms) AS t1 FROM pairs_all)
SELECT p.* FROM pairs_all p, b
WHERE p.first_ms >= b.t0 + 86400000 AND p.first_ms < b.t1 - 86400000
""")

step("summaries")
save("""
SELECT count(*)                                                     AS pairs_all,
       count(*) FILTER (WHERE landed)                               AS pairs_landed,
       sum(n_sig)                                                   AS signatures_all,
       sum(n_sig) FILTER (WHERE landed)                             AS signatures_landed_pairs,
       round(sum(n_sig) FILTER (WHERE landed) * 1.0
             / count(*) FILTER (WHERE landed), 4)                   AS sig_per_landed_tx,
       round(100.0 * count(*) FILTER (WHERE landed AND n_sig > 1)
             / count(*) FILTER (WHERE landed), 3)                   AS pct_landed_with_replacement,
       round(sum(n_sig) * 1.0 / count(*) FILTER (WHERE landed), 4)  AS sig_per_landed_tx_incl_unlanded,
       max(n_sig)                                                   AS max_sig_per_nonce
FROM pairs""", "summary.csv")

save("""
SELECT strftime(make_timestamp(first_ms * 1000), '%Y-%m')           AS month,
       count(*) FILTER (WHERE landed)                               AS pairs_landed,
       round(sum(n_sig) * 1.0 / count(*) FILTER (WHERE landed), 4)  AS sig_per_landed_tx_incl_unlanded,
       round(100.0 * count(*) FILTER (WHERE landed AND n_sig > 1)
             / count(*) FILTER (WHERE landed), 3)                   AS pct_landed_with_replacement,
       max(n_sig)                                                   AS max_sig_per_nonce
FROM pairs GROUP BY month ORDER BY month""", "monthly.csv")

save("""
SELECT CASE WHEN n_sig >= 5 THEN '5+' ELSE CAST(n_sig AS VARCHAR) END AS sig_per_nonce,
       landed, count(*) AS pairs
FROM pairs GROUP BY 1, 2 ORDER BY 2 DESC, 1""", "hist_sig_per_nonce.csv")

step("per-key table")
con.execute("""
CREATE OR REPLACE TABLE per_key AS
SELECT sender,
       count(*) FILTER (WHERE landed)              AS landed_tx,
       sum(n_sig)                                  AS signatures,
       sum(n_sig) - count(*) FILTER (WHERE landed) AS extra_signatures
FROM pairs GROUP BY sender
""")

ACT = """CASE WHEN {x} <= 1     THEN 'a) 1'
              WHEN {x} <= 10    THEN 'b) 2-10'
              WHEN {x} <= 100   THEN 'c) 11-100'
              WHEN {x} <= 1000  THEN 'd) 101-1000'
              WHEN {x} <= 10000 THEN 'e) 1001-10000'
              ELSE                   'f) >10000' END"""

save(f"""
SELECT {ACT.format(x='landed_tx')}                                 AS activity,
       count(*)                                                     AS keys,
       sum(landed_tx)                                               AS landed_tx,
       sum(signatures)                                              AS signatures,
       round(sum(signatures) * 1.0 / sum(landed_tx), 4)             AS multiplier,
       round(100.0 * avg(CAST(extra_signatures > 0 AS INT)), 2)     AS pct_keys_with_extra,
       round(quantile_cont(signatures * 1.0 / landed_tx, 0.99), 3)  AS key_ratio_p99,
       round(max(signatures * 1.0 / landed_tx), 2)                  AS key_ratio_max
FROM per_key WHERE landed_tx > 0
GROUP BY 1 ORDER BY 1""", "activity_multiplier.csv")

save("""
SELECT count(*) FILTER (WHERE extra_signatures >= 1)    AS keys_extra_ge1,
       count(*) FILTER (WHERE extra_signatures >= 10)   AS keys_extra_ge10,
       count(*) FILTER (WHERE extra_signatures >= 100)  AS keys_extra_ge100,
       count(*) FILTER (WHERE extra_signatures >= 1000) AS keys_extra_ge1000,
       max(extra_signatures)                            AS max_extra
FROM per_key""", "extra_tail.csv")

save("""
SELECT * FROM per_key WHERE extra_signatures > 0
ORDER BY extra_signatures DESC LIMIT 100""", "top_extra_keys.csv", show=False)

step("coverage (nonce-gap method, all days)")
con.execute("""
CREATE OR REPLACE TABLE cov AS
WITH r AS (
  SELECT sender,
         min(nonce) FILTER (WHERE landed) AS lo,
         max(nonce) FILTER (WHERE landed) AS hi
  FROM pairs_all GROUP BY sender
)
SELECT r.sender, r.hi - r.lo + 1 AS span,
       count(*) FILTER (WHERE p.nonce BETWEEN r.lo AND r.hi) AS seen
FROM r JOIN pairs_all p USING (sender)
WHERE r.lo IS NOT NULL
GROUP BY r.sender, r.lo, r.hi
""")
save(f"""
SELECT {ACT.format(x='span')}                                      AS span_class,
       count(*)                                                     AS keys,
       sum(span)                                                    AS nonces_used,
       sum(span - seen)                                             AS nonces_unseen,
       round(100.0 * sum(seen) / sum(span), 2)                      AS coverage_pct,
       round(100.0 * avg(CAST(span > seen AS INT)), 2)              AS pct_keys_with_unseen,
       round(100.0 * quantile_cont(seen * 1.0 / span, 0.5), 2)      AS key_cov_p50,
       round(100.0 * quantile_cont(seen * 1.0 / span, 0.1), 2)      AS key_cov_p10
FROM cov GROUP BY 1 ORDER BY 1""", "coverage_by_activity.csv")

step("done")
