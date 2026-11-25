-- ERC-4337 smart accounts: UserOperations per account on Ethereum mainnet (BigQuery).
-- Every executed UserOperation carries one owner signature, so the count per account is the
-- number of signatures that account's key(s) produced on chain. Smart accounts can rotate keys,
-- so this is an upper bound for signatures per key.
--
-- Checked values
--   topic0 of UserOperationEvent(bytes32,address,address,uint256,bool,uint256,uint256)
--     = 0x49628fd1471006c1482da88028e9ce4dbb080b815c9b0344d39e5a8e6ec1419f (same for all versions)
--   sender = topics[2]
--   EntryPoint v0.6 0x5ff137d4b0fdcd49dca30c7cf57e578a026d2789
--   EntryPoint v0.7 0x0000000071727de22e5e9d8baf0edac6f37da032
--   EntryPoint v0.8 0x4337084d9e255ff0702461cf8895ce9e3b5ff108
--   (v0.9 exists; add its address after checking the official release page)
--
-- COST: crypto_ethereum.logs is very large. Run ONE month first and read the byte estimate
-- shown at the top right of the editor before pressing Run.
--
-- Run the whole script: it returns two result tabs (summary, activity classes).

DECLARE t_start TIMESTAMP DEFAULT TIMESTAMP('2026-10-01');
DECLARE t_end   TIMESTAMP DEFAULT TIMESTAMP('2026-11-01');

CREATE TEMP TABLE per_account AS
SELECT
  CONCAT('0x', SUBSTR(l.topics[SAFE_OFFSET(2)], 27)) AS account,
  COUNT(*)                                          AS user_ops,
  COUNT(DISTINCT l.address)                         AS entrypoints_used
FROM `bigquery-public-data.crypto_ethereum.logs` AS l
WHERE l.block_timestamp >= t_start AND l.block_timestamp < t_end
  AND l.topics[SAFE_OFFSET(0)] =
      '0x49628fd1471006c1482da88028e9ce4dbb080b815c9b0344d39e5a8e6ec1419f'
  AND l.address IN (
      '0x5ff137d4b0fdcd49dca30c7cf57e578a026d2789',  -- v0.6
      '0x0000000071727de22e5e9d8baf0edac6f37da032',  -- v0.7
      '0x4337084d9e255ff0702461cf8895ce9e3b5ff108'   -- v0.8
  )
GROUP BY account;

-- Result 1: summary
SELECT
  COUNT(*)                                      AS accounts,
  SUM(user_ops)                                 AS user_ops,
  APPROX_QUANTILES(user_ops, 1000)[OFFSET(500)] AS p50,
  APPROX_QUANTILES(user_ops, 1000)[OFFSET(900)] AS p90,
  APPROX_QUANTILES(user_ops, 1000)[OFFSET(990)] AS p99,
  APPROX_QUANTILES(user_ops, 1000)[OFFSET(999)] AS p999,
  MAX(user_ops)                                 AS max_ops,
  COUNTIF(entrypoints_used > 1)                 AS accounts_multi_entrypoint
FROM per_account;

-- Result 2: same activity classes as the Ethereum EOA analysis
SELECT
  CASE WHEN user_ops <= 1    THEN 'a) 1'
       WHEN user_ops <= 10   THEN 'b) 2-10'
       WHEN user_ops <= 100  THEN 'c) 11-100'
       WHEN user_ops <= 1000 THEN 'd) 101-1000'
       ELSE                       'e) >1000' END AS activity,
  COUNT(*)      AS accounts,
  SUM(user_ops) AS user_ops
FROM per_account
GROUP BY activity
ORDER BY activity;

-- Optional: top accounts (small result, safe to download)
-- SELECT account, user_ops FROM per_account ORDER BY user_ops DESC LIMIT 100;
