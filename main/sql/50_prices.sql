-- Price parameters for the cost model (Section 5), window 2026-05-01 to 2026-10-31 (UTC).
-- Ethereum and Bitcoin only; the layer-2 prices are in 51_l2_prices.sql.
-- Expected scan: about 20 GB.
-- Output: one table (chain, item, unit, p10, p50, p90, mean, n). Save as results/bigquery/50_prices.csv
--   eth base_fee           : block base fee per gas (wei), per block
--   eth priority_fee       : effective gas price minus block base fee (wei), per transaction
--   eth blob_base_fee      : blob gas price paid by type-3 transactions (wei), per transaction
--   btc feerate            : fee / virtual size (sat/vB), per non-coinbase transaction
--   btc feerate_weighted   : the same weighted by vsize (sat/vB): the price of an average vbyte

DECLARE t_start TIMESTAMP DEFAULT TIMESTAMP('2026-05-01');
DECLARE t_end   TIMESTAMP DEFAULT TIMESTAMP('2026-11-01');

CREATE TEMP TABLE out_rows (chain STRING, item STRING, unit STRING,
                            p10 FLOAT64, p50 FLOAT64, p90 FLOAT64, mean FLOAT64, n INT64);

INSERT INTO out_rows
SELECT 'ethereum', 'base_fee', 'wei/gas',
       q[OFFSET(10)], q[OFFSET(50)], q[OFFSET(90)], m, n
FROM (SELECT APPROX_QUANTILES(CAST(base_fee_per_gas AS FLOAT64), 100) AS q,
             AVG(CAST(base_fee_per_gas AS FLOAT64)) AS m, COUNT(*) AS n
      FROM `bigquery-public-data.crypto_ethereum.blocks`
      WHERE timestamp >= t_start AND timestamp < t_end);

INSERT INTO out_rows
SELECT 'ethereum', 'priority_fee', 'wei/gas',
       q[OFFSET(10)], q[OFFSET(50)], q[OFFSET(90)], m, n
FROM (SELECT APPROX_QUANTILES(pf, 100) AS q, AVG(pf) AS m, COUNT(*) AS n
      FROM (SELECT CAST(t.receipt_effective_gas_price AS FLOAT64)
                   - CAST(b.base_fee_per_gas AS FLOAT64) AS pf
            FROM `bigquery-public-data.crypto_ethereum.transactions` AS t
            JOIN `bigquery-public-data.crypto_ethereum.blocks` AS b
              ON b.number = t.block_number
            WHERE t.block_timestamp >= t_start AND t.block_timestamp < t_end
              AND b.timestamp >= t_start AND b.timestamp < t_end));

INSERT INTO out_rows
SELECT 'ethereum', 'blob_base_fee', 'wei/blob-gas',
       q[OFFSET(10)], q[OFFSET(50)], q[OFFSET(90)], m, n
FROM (SELECT APPROX_QUANTILES(CAST(receipt_blob_gas_price AS FLOAT64), 100) AS q,
             AVG(CAST(receipt_blob_gas_price AS FLOAT64)) AS m, COUNT(*) AS n
      FROM `bigquery-public-data.crypto_ethereum.transactions`
      WHERE block_timestamp >= t_start AND block_timestamp < t_end
        AND transaction_type = 3);

INSERT INTO out_rows
SELECT 'bitcoin', 'feerate', 'sat/vB',
       q[OFFSET(10)], q[OFFSET(50)], q[OFFSET(90)], m, n
FROM (SELECT APPROX_QUANTILES(CAST(fee AS FLOAT64) / virtual_size, 100) AS q,
             AVG(CAST(fee AS FLOAT64) / virtual_size) AS m, COUNT(*) AS n
      FROM `bigquery-public-data.crypto_bitcoin.transactions`
      WHERE block_timestamp_month BETWEEN DATE('2026-05-01') AND DATE('2026-10-01')
        AND NOT is_coinbase AND virtual_size > 0);

INSERT INTO out_rows
SELECT 'bitcoin', 'feerate_weighted', 'sat/vB', NULL, NULL, NULL,
       SUM(CAST(fee AS FLOAT64)) / SUM(virtual_size), COUNT(*)
FROM `bigquery-public-data.crypto_bitcoin.transactions`
WHERE block_timestamp_month BETWEEN DATE('2026-05-01') AND DATE('2026-10-01')
  AND NOT is_coinbase AND virtual_size > 0;

SELECT * FROM out_rows ORDER BY chain, item;
