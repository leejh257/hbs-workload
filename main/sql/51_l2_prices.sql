-- Layer-2 execution gas prices for the cost model (Section 5), window 2026-05-01 to 2026-10-31.
-- Column check (2026-11-26, results/bigquery/51_l2_price_columns.csv): the paid price is
-- receipts.effective_gas_price (INT64, wei); transactions has no effective price and no layer-1
-- fee column, so the rollups' layer-1 data fee stays modelled from Ethereum prices.
-- User-signed transactions only (types 0 to 4), joined on transaction_hash.
-- If receipts has no block_timestamp column, drop the r.block_timestamp conditions.
-- Output: (chain, item, unit, p10, p50, p90, mean, n). Save as results/bigquery/51_l2_prices.csv

DECLARE t_start TIMESTAMP DEFAULT TIMESTAMP('2026-05-01');
DECLARE t_end   TIMESTAMP DEFAULT TIMESTAMP('2026-11-01');

CREATE TEMP TABLE px AS
SELECT 'arbitrum' AS net, CAST(r.effective_gas_price AS FLOAT64) AS p
FROM `bigquery-public-data.goog_blockchain_arbitrum_one_us.receipts` AS r
JOIN `bigquery-public-data.goog_blockchain_arbitrum_one_us.transactions` AS t
  USING (transaction_hash)
WHERE t.block_timestamp >= t_start AND t.block_timestamp < t_end
  AND r.block_timestamp >= t_start AND r.block_timestamp < t_end
  AND t.transaction_type IN (0, 1, 2, 3, 4)
UNION ALL
SELECT 'optimism', CAST(r.effective_gas_price AS FLOAT64)
FROM `bigquery-public-data.goog_blockchain_optimism_mainnet_us.receipts` AS r
JOIN `bigquery-public-data.goog_blockchain_optimism_mainnet_us.transactions` AS t
  USING (transaction_hash)
WHERE t.block_timestamp >= t_start AND t.block_timestamp < t_end
  AND r.block_timestamp >= t_start AND r.block_timestamp < t_end
  AND t.transaction_type IN (0, 1, 2, 3, 4)
UNION ALL
SELECT 'polygon', CAST(r.effective_gas_price AS FLOAT64)
FROM `bigquery-public-data.goog_blockchain_polygon_mainnet_us.receipts` AS r
JOIN `bigquery-public-data.goog_blockchain_polygon_mainnet_us.transactions` AS t
  USING (transaction_hash)
WHERE t.block_timestamp >= t_start AND t.block_timestamp < t_end
  AND r.block_timestamp >= t_start AND r.block_timestamp < t_end
  AND t.transaction_type IN (0, 1, 2, 3, 4);

SELECT net AS chain, 'gas_price' AS item, 'wei/gas' AS unit,
       q[OFFSET(10)] AS p10, q[OFFSET(50)] AS p50, q[OFFSET(90)] AS p90, m AS mean, n
FROM (SELECT net, APPROX_QUANTILES(p, 100) AS q, AVG(p) AS m, COUNT(*) AS n
      FROM px GROUP BY net)
ORDER BY chain;
