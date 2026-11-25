-- ERC-4337 smart accounts over the window, with an EIP-7702 correction.
-- Every executed UserOperation carries one owner signature.
-- With EIP-7702 (EntryPoint v0.8) the account address is an EOA whose key also signs ordinary
-- transactions, so for those accounts the key's signatures = UserOperations + EOA transactions.
--   population 'smart_account'      : all accounts, metric user_ops
--   population 'eip7702_combined'   : accounts that also sent EOA transactions in the window,
--                                     metric = user_ops + eoa_tx
-- topic0, sender position and EntryPoint addresses were checked in the pilot.
-- Expected scan: several hundred GB for six months (logs table). Check the estimate first;
-- if it is too large, run month by month by changing t_start and t_end.
-- Output: one table with columns (chain, population, metric, stat, bin_lo, keys, signatures)
--   stat = 'quantile': bin_lo = quantile level x1000 (500 = median, 1000 = max), keys = value
--   stat = 'hist'    : log2 histogram, bin_lo = lower edge (1, 2, 4, ...), keys = number of keys,
--                      signatures = sum of the metric over those keys
--   stat = 'over'    : keys = number of keys with metric > 2^bin_lo
-- Save the result with "Save results > CSV (local file)" as results/20_erc4337.csv

DECLARE t_start TIMESTAMP DEFAULT TIMESTAMP('2026-05-01');
DECLARE t_end   TIMESTAMP DEFAULT TIMESTAMP('2026-11-01');

CREATE TEMP TABLE sa AS
SELECT CONCAT('0x', SUBSTR(l.topics[SAFE_OFFSET(2)], 27)) AS addr, COUNT(*) AS user_ops
FROM `bigquery-public-data.crypto_ethereum.logs` AS l
WHERE l.block_timestamp >= t_start AND l.block_timestamp < t_end
  AND l.topics[SAFE_OFFSET(0)] =
      '0x49628fd1471006c1482da88028e9ce4dbb080b815c9b0344d39e5a8e6ec1419f'
  AND l.address IN ('0x5ff137d4b0fdcd49dca30c7cf57e578a026d2789',   -- v0.6
                    '0x0000000071727de22e5e9d8baf0edac6f37da032',   -- v0.7
                    '0x4337084d9e255ff0702461cf8895ce9e3b5ff108')   -- v0.8
GROUP BY addr;

CREATE TEMP TABLE eoa_tx AS
SELECT t.from_address AS addr, COUNT(*) AS n
FROM `bigquery-public-data.crypto_ethereum.transactions` AS t
JOIN sa ON sa.addr = t.from_address
WHERE t.block_timestamp >= t_start AND t.block_timestamp < t_end
GROUP BY addr;

CREATE TEMP TABLE m AS
SELECT addr, 'smart_account' AS population, 'user_ops' AS metric, user_ops AS v FROM sa
UNION ALL
SELECT sa.addr, 'eip7702_combined', 'user_ops_plus_eoa_tx', sa.user_ops + e.n
FROM sa JOIN eoa_tx AS e USING (addr);

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
