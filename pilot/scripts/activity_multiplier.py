"""Replacement multiplier by key activity level.

Input : results/per_key.csv produced by eth_replacement_pilot.py
Output: printed table and results/activity_multiplier.csv
Usage : python activity_multiplier.py   (run in the same folder as eth_replacement_pilot.py)
"""
import pathlib
import duckdb

src = pathlib.Path("results/per_key.csv")
if not src.exists():
    raise SystemExit("results/per_key.csv not found. Run eth_replacement_pilot.py first.")

df = duckdb.sql(f"""
SELECT CASE WHEN landed_tx <= 1    THEN 'a) 1'
            WHEN landed_tx <= 10   THEN 'b) 2-10'
            WHEN landed_tx <= 100  THEN 'c) 11-100'
            WHEN landed_tx <= 1000 THEN 'd) 101-1000'
            ELSE                        'e) >1000' END              AS activity,
       count(*)                                                     AS keys,
       sum(landed_tx)                                               AS landed_tx,
       sum(signatures)                                              AS signatures,
       round(sum(signatures) * 1.0 / sum(landed_tx), 4)             AS multiplier,
       round(100.0 * avg(CAST(extra_signatures > 0 AS INT)), 2)     AS pct_keys_with_extra,
       round(quantile_cont(signatures * 1.0 / landed_tx, 0.99), 3)  AS key_ratio_p99,
       round(max(signatures * 1.0 / landed_tx), 2)                  AS key_ratio_max
FROM read_csv('{src.as_posix()}', header=true)
WHERE landed_tx > 0
GROUP BY 1 ORDER BY 1
""").df()

print(df.to_string(index=False))
df.to_csv("results/activity_multiplier.csv", index=False)

unlanded_only = duckdb.sql(f"""
SELECT count(*) AS keys, sum(signatures) AS signatures
FROM read_csv('{src.as_posix()}', header=true) WHERE landed_tx = 0
""").df()
print("\nkeys with no landed tx in window:")
print(unlanded_only.to_string(index=False))
