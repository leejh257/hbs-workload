"""How much of each key's on-chain activity does the public mempool archive see?

Idea  : Ethereum nonces are consecutive. For each sender, every nonce between the smallest and
        largest landed nonce observed in the download (the span) was used on chain. Nonces in the
        span that never appear in the archive were sent through private channels.
Input : data/*.csv (Flashbots Mempool Dumpster), same folder as eth_replacement_pilot.py
Output: printed tables, results/coverage_by_activity.csv, results/coverage_per_key.csv

Notes
  * No day trimming here; the whole download is used.
  * Private tx before the first or after the last observed landed nonce are invisible to this
    method, so coverage is an upper bound and the unseen share a lower bound.
  * Keys with span 1 (one observed landed nonce) carry no information and are reported separately.
"""
import pathlib
import duckdb

out = pathlib.Path("results")
out.mkdir(exist_ok=True)
con = duckdb.connect()

con.execute("""
CREATE TABLE tx AS
SELECT lower("from")                AS sender,
       CAST(nonce AS UBIGINT)       AS nonce,
       bool_or(included_at_block_height NOT IN ('', '0')
               AND included_at_block_height IS NOT NULL) AS landed
FROM read_csv('data/*.csv', header=true, all_varchar=true, union_by_name=true)
WHERE chain_id = '1' OR chain_id IS NULL
GROUP BY 1, 2;
""")

con.execute("""
CREATE TABLE cov AS
WITH r AS (
  SELECT sender,
         min(nonce) FILTER (WHERE landed) AS lo,
         max(nonce) FILTER (WHERE landed) AS hi
  FROM tx GROUP BY sender
)
SELECT r.sender,
       r.hi - r.lo + 1                                   AS span,
       count(*) FILTER (WHERE t.nonce BETWEEN r.lo AND r.hi) AS seen,
       r.hi - r.lo + 1
         - count(*) FILTER (WHERE t.nonce BETWEEN r.lo AND r.hi) AS unseen
FROM r JOIN tx t USING (sender)
WHERE r.lo IS NOT NULL
GROUP BY r.sender, r.lo, r.hi;
""")
con.execute(f"COPY cov TO '{out.as_posix()}/coverage_per_key.csv' (HEADER)")

by_act = con.execute("""
SELECT CASE WHEN span = 1     THEN 'a) 1 (no info)'
            WHEN span <= 10   THEN 'b) 2-10'
            WHEN span <= 100  THEN 'c) 11-100'
            WHEN span <= 1000 THEN 'd) 101-1000'
            ELSE                   'e) >1000' END              AS span_class,
       count(*)                                                AS keys,
       sum(span)                                               AS nonces_used,
       sum(unseen)                                             AS nonces_unseen,
       round(100.0 * sum(seen) / sum(span), 2)                 AS coverage_pct,
       round(100.0 * avg(CAST(unseen > 0 AS INT)), 2)          AS pct_keys_with_unseen,
       round(100.0 * quantile_cont(seen * 1.0 / span, 0.5), 2) AS key_cov_p50,
       round(100.0 * quantile_cont(seen * 1.0 / span, 0.1), 2) AS key_cov_p10
FROM cov GROUP BY 1 ORDER BY 1
""").df()
print("== public-mempool coverage by activity (span of landed nonces) ==")
print(by_act.to_string(index=False))
by_act.to_csv(out / "coverage_by_activity.csv", index=False)

tot = con.execute("""
SELECT count(*) FILTER (WHERE span > 1)                              AS informative_keys,
       sum(span) FILTER (WHERE span > 1)                             AS nonces_used,
       round(100.0 * sum(seen) FILTER (WHERE span > 1)
                   / sum(span) FILTER (WHERE span > 1), 2)           AS coverage_pct
FROM cov""").df()
print("\n== overall (keys with span > 1) ==")
print(tot.T.to_string(header=False))

print("\n== keys with the most unseen nonces ==")
print(con.execute("""
SELECT sender, span, seen, unseen, round(100.0 * seen / span, 1) AS coverage_pct
FROM cov ORDER BY unseen DESC LIMIT 15""").df().to_string(index=False))
