-- UTXO chain (Bitcoin): signatures per address in the window.
-- Litecoin was dropped: crypto_litecoin has no data for the measurement window (checked 2026-11-26).
-- Each spent input of a single-key output needs one signature from the address's key, so the
-- number of spent inputs per address counts that key's signatures. Only single-key output types
-- are used (pubkey, pubkeyhash, witness_v0_keyhash, witness_v1_taproot); multisig and script
-- types are excluded because one input can carry several signatures from different keys.
-- Lifetime counts for Bitcoin come from the SoK dataset (hbs-blockchain-signature-limits).
-- Expected scan: tens of GB for six months.
-- Output: one table with columns (chain, population, metric, stat, bin_lo, keys, signatures)
--   stat = 'quantile': bin_lo = quantile level x1000 (500 = median, 1000 = max), keys = value
--   stat = 'hist'    : log2 histogram, bin_lo = lower edge (1, 2, 4, ...), keys = number of keys,
--                      signatures = sum of the metric over those keys
--   stat = 'over'    : keys = number of keys with metric > 2^bin_lo
-- Save the result with "Save results > CSV (local file)" as results/40_utxo.csv

DECLARE m_start DATE      DEFAULT DATE('2026-05-01');
DECLARE m_end   DATE      DEFAULT DATE('2026-10-01');   -- last partition month included
DECLARE days    FLOAT64   DEFAULT CAST(DATE_DIFF(DATE_ADD(m_end, INTERVAL 1 MONTH), m_start, DAY) AS FLOAT64);

CREATE TEMP TABLE spends AS
SELECT 'bitcoin' AS net, i.addresses[OFFSET(0)] AS addr, i.type AS type, COUNT(*) AS n_win
FROM `bigquery-public-data.crypto_bitcoin.transactions` AS t, UNNEST(t.inputs) AS i
WHERE t.block_timestamp_month BETWEEN m_start AND m_end
  AND ARRAY_LENGTH(i.addresses) = 1
  AND i.type IN ('pubkey', 'pubkeyhash', 'witness_v0_keyhash', 'witness_v1_taproot')
GROUP BY 2, 3;


CREATE TEMP TABLE m AS
SELECT addr, net AS population, 'n_win' AS metric, SUM(n_win) AS v FROM spends GROUP BY addr, net
UNION ALL
SELECT addr, net, 'annual_rate', CAST(ROUND(SUM(n_win) * 365.0 / days) AS INT64)
FROM spends GROUP BY addr, net
UNION ALL
SELECT addr, CONCAT(net, ':', type), 'n_win', n_win FROM spends;

-- Common output block: quantiles, log2 histogram, keys above 2^e
SELECT 'utxo' AS chain, population, metric, stat, bin_lo, keys, signatures FROM (
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
