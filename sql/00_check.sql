-- Step 0: check that every dataset covers the measurement window and that the column names used
-- by the other queries exist. Cheap: scans only the last month of each table.
-- Window used by the study: 2026-05-01 to 2026-10-31 (UTC).

-- (a) Latest block time per dataset
SELECT 'ethereum' AS chain, MAX(block_timestamp) AS latest
FROM `bigquery-public-data.crypto_ethereum.transactions`
WHERE block_timestamp >= TIMESTAMP('2026-10-01')
UNION ALL
SELECT 'bitcoin', MAX(block_timestamp)
FROM `bigquery-public-data.crypto_bitcoin.transactions`
WHERE block_timestamp_month >= DATE('2026-10-01')
UNION ALL
SELECT 'litecoin', MAX(block_timestamp)
FROM `bigquery-public-data.crypto_litecoin.transactions`
WHERE block_timestamp_month >= DATE('2026-10-01')
UNION ALL
SELECT 'arbitrum', MAX(block_timestamp)
FROM `bigquery-public-data.goog_blockchain_arbitrum_one_us.transactions`
WHERE block_timestamp >= TIMESTAMP('2026-10-01')
UNION ALL
SELECT 'optimism', MAX(block_timestamp)
FROM `bigquery-public-data.goog_blockchain_optimism_mainnet_us.transactions`
WHERE block_timestamp >= TIMESTAMP('2026-10-01')
UNION ALL
SELECT 'polygon', MAX(block_timestamp)
FROM `bigquery-public-data.goog_blockchain_polygon_mainnet_us.transactions`
WHERE block_timestamp >= TIMESTAMP('2026-10-01')
ORDER BY chain;

-- (b) Column names in the L2 transactions tables (free metadata query).
-- 30_l2.sql expects from_address, nonce, block_timestamp. If a name differs, edit 30_l2.sql.
-- SELECT table_schema, column_name, data_type
-- FROM `bigquery-public-data.goog_blockchain_arbitrum_one_us.INFORMATION_SCHEMA.COLUMNS`
-- WHERE table_name = 'transactions'
--   AND column_name IN ('from_address', 'nonce', 'block_timestamp', 'transaction_type');

-- (c) Input types in Bitcoin for one month. 40_utxo.sql keeps pubkey, pubkeyhash,
-- witness_v0_keyhash and witness_v1_taproot. If taproot spends appear under another name
-- (for example witness_unknown), add that name to the type list in 40_utxo.sql.
-- SELECT i.type, COUNT(*) AS inputs
-- FROM `bigquery-public-data.crypto_bitcoin.transactions` AS t, UNNEST(t.inputs) AS i
-- WHERE t.block_timestamp_month = DATE('2026-10-01')
-- GROUP BY i.type ORDER BY inputs DESC;
