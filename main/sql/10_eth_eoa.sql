-- Ethereum EOAs: signatures per key in the window and lifetime signatures per key.
-- An EOA signs every transaction it sends, so
--   n_win       = transactions sent in the window (landed signatures in the window)
--   annual_rate = n_win scaled to 365 days
--   lifetime    = max nonce + 1 at the end of the window (landed signatures since creation)
-- Expected scan: about 15 GB for six months.
-- Output: one table with columns (chain, population, metric, stat, bin_lo, keys, signatures)
--   stat = 'quantile': bin_lo = quantile level x1000 (500 = median, 1000 = max), keys = value
--   stat = 'hist'    : log2 histogram, bin_lo = lower edge (1, 2, 4, ...), keys = number of keys,
--                      signatures = sum of the metric over those keys
--   stat = 'over'    : keys = number of keys with metric > 2^bin_lo
-- Save the result with "Save results > CSV (local file)" as results/10_eth_eoa.csv

DECLARE t_start TIMESTAMP DEFAULT TIMESTAMP('2026-05-01');
DECLARE t_end   TIMESTAMP DEFAULT TIMESTAMP('2026-11-01');
DECLARE days    FLOAT64   DEFAULT TIMESTAMP_DIFF(t_end, t_start, HOUR) / 24.0;

CREATE TEMP TABLE eoa AS
SELECT from_address AS addr, COUNT(*) AS n_win, MAX(nonce) + 1 AS lifetime
FROM `bigquery-public-data.crypto_ethereum.transactions`
WHERE block_timestamp >= t_start AND block_timestamp < t_end
GROUP BY addr;

CREATE TEMP TABLE m AS
SELECT addr, 'eoa' AS population, 'n_win' AS metric, n_win AS v FROM eoa
UNION ALL SELECT addr, 'eoa', 'annual_rate', CAST(ROUND(n_win * 365.0 / days) AS INT64) FROM eoa
UNION ALL SELECT addr, 'eoa', 'lifetime', lifetime FROM eoa;

-- Common output block: quantiles, log2 histogram, keys above 2^e
SELECT 'ethereum' AS chain, population, metric, stat, bin_lo, keys, signatures FROM (
  SELECT population, metric, 'quantile' AS stat, q.level AS bin_lo, q.value AS keys,
         CAST(NULL AS INT64) AS signatures
  FROM (SELECT population, metric, APPROX_QUANTILES(v, 1000) AS qs
        FROM m GROUP BY population, metric) AS t,
       UNNEST([STRUCT(500 AS level, t.qs[OFFSET(500)] AS value),
               STRUCT(900, t.qs[OFFSET(900)]), STRUCT(990, t.qs[OFFSET(990)]),
               STRUCT(999, t.qs[OFFSET(999)]), STRUCT(1000, t.qs[OFFSET(1000)])]) AS q
  UNION ALL
  SELECT population, metric, 'hist',
         CAST(POW(2, FLOOR(LOG(GREATEST(v, 1), 2) + 1e-9)) AS INT64) AS bin_lo,
         COUNT(*), SUM(v)
  FROM m GROUP BY population, metric, bin_lo
  UNION ALL
  SELECT population, metric, 'over', e, COUNTIF(v > CAST(POW(2, e) AS INT64)),
         CAST(NULL AS INT64)
  FROM m CROSS JOIN UNNEST([10, 16, 20, 24]) AS e
  GROUP BY population, metric, e
)
ORDER BY population, metric, stat, bin_lo;
