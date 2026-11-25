-- Layer-2 EOAs (Arbitrum One, Optimism, Polygon PoS): signatures per key in the window and lifetime.
-- Same metrics as 10_eth_eoa.sql. Column names follow the Blockchain Analytics schema
-- (from_address, nonce, block_timestamp); confirm them with 00_check.sql part (b).
-- nonce is BIGNUMERIC in these tables, so it is cast to INT64.
-- Only user-signed transaction types are counted (transaction_type 0 to 4: legacy, 2930, 1559,
-- 4844, 7702). This removes unsigned system transactions such as Arbitrum internal (106),
-- deposit and retryable types (100 to 105, 120) and OP-stack deposits (126); the first run
-- without this filter was dominated by ArbOS and L1-attributes system senders.
-- Output: one table with columns (chain, population, metric, stat, bin_lo, keys, signatures)
--   stat = 'quantile': bin_lo = quantile level x1000 (500 = median, 1000 = max), keys = value
--   stat = 'hist'    : log2 histogram, bin_lo = lower edge (1, 2, 4, ...), keys = number of keys,
--                      signatures = sum of the metric over those keys
--   stat = 'over'    : keys = number of keys with metric > 2^bin_lo
-- Save the result with "Save results > CSV (local file)" as results/30_l2.csv

DECLARE t_start TIMESTAMP DEFAULT TIMESTAMP('2026-05-01');
DECLARE t_end   TIMESTAMP DEFAULT TIMESTAMP('2026-11-01');
DECLARE days    FLOAT64   DEFAULT TIMESTAMP_DIFF(t_end, t_start, HOUR) / 24.0;

CREATE TEMP TABLE l2 AS
SELECT 'arbitrum' AS net, from_address AS addr, COUNT(*) AS n_win, CAST(MAX(nonce) AS INT64) + 1 AS lifetime
FROM `bigquery-public-data.goog_blockchain_arbitrum_one_us.transactions`
WHERE block_timestamp >= t_start AND block_timestamp < t_end
  AND transaction_type IN (0, 1, 2, 3, 4)
GROUP BY addr
UNION ALL
SELECT 'optimism', from_address, COUNT(*), CAST(MAX(nonce) AS INT64) + 1
FROM `bigquery-public-data.goog_blockchain_optimism_mainnet_us.transactions`
WHERE block_timestamp >= t_start AND block_timestamp < t_end
  AND transaction_type IN (0, 1, 2, 3, 4)
GROUP BY from_address
UNION ALL
SELECT 'polygon', from_address, COUNT(*), CAST(MAX(nonce) AS INT64) + 1
FROM `bigquery-public-data.goog_blockchain_polygon_mainnet_us.transactions`
WHERE block_timestamp >= t_start AND block_timestamp < t_end
  AND transaction_type IN (0, 1, 2, 3, 4)
GROUP BY from_address;

CREATE TEMP TABLE m AS
SELECT addr, net AS population, 'n_win' AS metric, n_win AS v FROM l2
WHERE addr IS NOT NULL AND addr != '0x0000000000000000000000000000000000000000'
UNION ALL
SELECT addr, net, 'annual_rate', CAST(ROUND(n_win * 365.0 / days) AS INT64) FROM l2
WHERE addr IS NOT NULL AND addr != '0x0000000000000000000000000000000000000000'
UNION ALL
SELECT addr, net, 'lifetime', lifetime FROM l2
WHERE addr IS NOT NULL AND addr != '0x0000000000000000000000000000000000000000';

-- Common output block: quantiles, log2 histogram, keys above 2^e
SELECT 'l2' AS chain, population, metric, stat, bin_lo, keys, signatures FROM (
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
