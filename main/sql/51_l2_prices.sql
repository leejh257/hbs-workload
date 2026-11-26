-- Layer-2 execution gas prices for the cost model (Section 5), window 2026-05-01 to 2026-10-31.
-- STEP 1 (free metadata query): list the price columns of the three transactions tables.
--   Run this first and check that effective_gas_price exists in all three; if a table uses
--   another name (for example receipt_effective_gas_price or gas_price), edit STEP 2.
--
-- SELECT table_schema, column_name, data_type
-- FROM `bigquery-public-data.goog_blockchain_arbitrum_one_us.INFORMATION_SCHEMA.COLUMNS`
-- WHERE table_name = 'transactions' AND REGEXP_CONTAINS(column_name, r'price|fee|l1');
-- (repeat with goog_blockchain_optimism_mainnet_us and goog_blockchain_polygon_mainnet_us)
--
-- STEP 2: quantiles of the effective gas price paid by user-signed transactions (types 0 to 4).
-- On Arbitrum and OP Mainnet this is the layer-2 execution price only; their layer-1 data fee
-- is modelled from Ethereum prices (50_prices.sql) and the published fee formulas.
-- Output: (chain, item, unit, p10, p50, p90, mean, n). Save as results/bigquery/51_l2_prices.csv

DECLARE t_start TIMESTAMP DEFAULT TIMESTAMP('2026-05-01');
DECLARE t_end   TIMESTAMP DEFAULT TIMESTAMP('2026-11-01');

SELECT net AS chain, 'gas_price' AS item, 'wei/gas' AS unit,
       q[OFFSET(10)] AS p10, q[OFFSET(50)] AS p50, q[OFFSET(90)] AS p90, m AS mean, n
FROM (
  SELECT 'arbitrum' AS net, APPROX_QUANTILES(CAST(effective_gas_price AS FLOAT64), 100) AS q,
         AVG(CAST(effective_gas_price AS FLOAT64)) AS m, COUNT(*) AS n
  FROM `bigquery-public-data.goog_blockchain_arbitrum_one_us.transactions`
  WHERE block_timestamp >= t_start AND block_timestamp < t_end
    AND transaction_type IN (0, 1, 2, 3, 4)
  UNION ALL
  SELECT 'optimism', APPROX_QUANTILES(CAST(effective_gas_price AS FLOAT64), 100),
         AVG(CAST(effective_gas_price AS FLOAT64)), COUNT(*)
  FROM `bigquery-public-data.goog_blockchain_optimism_mainnet_us.transactions`
  WHERE block_timestamp >= t_start AND block_timestamp < t_end
    AND transaction_type IN (0, 1, 2, 3, 4)
  UNION ALL
  SELECT 'polygon', APPROX_QUANTILES(CAST(effective_gas_price AS FLOAT64), 100),
         AVG(CAST(effective_gas_price AS FLOAT64)), COUNT(*)
  FROM `bigquery-public-data.goog_blockchain_polygon_mainnet_us.transactions`
  WHERE block_timestamp >= t_start AND block_timestamp < t_end
    AND transaction_type IN (0, 1, 2, 3, 4)
)
ORDER BY chain;
