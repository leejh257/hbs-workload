"""Check one sender in the Mempool Dumpster window (default: the key with exactly 65,535 landed tx).

Usage : python check_key.py [address]
Run in the same folder as eth_replacement_pilot.py (reads data/*.csv directly).

What it prints
  1. Per-day counts for this sender (hashes, landed hashes, distinct nonces).
  2. Landed nonce range in the window: min, max, span (= max - min + 1) and missing nonces.
     If span equals the landed count, the sender really landed that many tx in the window.
  3. The first and last landed transactions (hash, nonce, block) to look up on Etherscan.
"""
import sys
import duckdb

addr = (sys.argv[1] if len(sys.argv) > 1
        else "0x6872b6630a3afcd3117191a8403c2002e13df7de").lower()
con = duckdb.connect()

con.execute(f"""
CREATE TABLE k AS
SELECT hash,
       CAST(nonce AS UBIGINT)                      AS nonce,
       CAST(timestamp_ms AS BIGINT)                AS ts_ms,
       CASE WHEN included_at_block_height IN ('', '0') THEN NULL
            ELSE CAST(included_at_block_height AS BIGINT) END AS block,
       filename
FROM read_csv('data/*.csv', header=true, all_varchar=true,
              union_by_name=true, filename=true)
WHERE lower("from") = '{addr}';
""")

print(f"== sender {addr} ==")
print("\n-- per daily file --")
print(con.execute("""
SELECT regexp_extract(filename, '([0-9-]{10})', 1) AS day,
       count(*)                                    AS rows,
       count(DISTINCT hash)                        AS hashes,
       count(DISTINCT hash) FILTER (WHERE block IS NOT NULL) AS landed_hashes,
       count(DISTINCT nonce)                       AS nonces
FROM k GROUP BY 1 ORDER BY 1""").df().to_string(index=False))

print("\n-- landed nonce range (whole download, no trimming) --")
print(con.execute("""
WITH l AS (SELECT DISTINCT nonce FROM k WHERE block IS NOT NULL)
SELECT count(*)                       AS landed_nonces,
       min(nonce)                     AS min_nonce,
       max(nonce)                     AS max_nonce,
       max(nonce) - min(nonce) + 1    AS span,
       max(nonce) - min(nonce) + 1 - count(*) AS missing_in_span
FROM l""").df().T.to_string(header=False))

print("\n-- first and last landed tx (look these up on Etherscan) --")
print(con.execute("""
(SELECT 'first' AS which, hash, nonce, block,
        to_timestamp(ts_ms / 1000) AS first_seen_utc
 FROM k WHERE block IS NOT NULL ORDER BY nonce ASC LIMIT 1)
UNION ALL
(SELECT 'last', hash, nonce, block, to_timestamp(ts_ms / 1000)
 FROM k WHERE block IS NOT NULL ORDER BY nonce DESC LIMIT 1)
""").df().to_string(index=False))

print("\nNote: eth_replacement_pilot.py trims the first and last day, so its landed_tx can be")
print("smaller than landed_nonces here. Compare span with landed_nonces in this output.")
