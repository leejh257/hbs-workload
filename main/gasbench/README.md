# gasbench: measured EVM verification gas for SLH-DSA parameter sets

This folder measures the gas of on-chain SLH-DSA verification (FIPS 205, SHA2 instantiation,
n = 16 bytes) for the parameter sets recommended in the paper and for the SLH-DSA-128s and
-128f baselines. The measured constants replace the earlier per-hash estimates in
`explore/explore.py`, `analysis/cost_model.py` and `analysis/sensitivity.py`.

## Contents

| Path | What it is |
|---|---|
| `src/SlhDsaVerifier.sol` | Readable reference verifier (Solidity), configurable (h, d, a, k, lg w); optional Keccak variant |
| `src/SlhDsaVerifierSha.sol` | Gas-optimized verifier (Yul, fixed memory), SHA-256 precompile, standard-conforming |
| `src/SlhDsaVerifierKeccak.sol` | Same with KECCAK256 instead of SHA-256 (non-standard, for gas comparison only) |
| `tools/gen_vectors.py` | Key generation and signing with the `slhdsa` reference package (FIPS 205 internal functions) for custom parameters; an independent Python verifier cross-checks every signature and counts tweakable-hash calls |
| `tools/gen_opt.py` | Generates the two optimized verifiers from one template |
| `tools/onchain.py` | Deploys the optimized verifiers on a local Prague chain (anvil) and sends real verification transactions; records receipt `gasUsed` |
| `test/Gas.t.sol` | Foundry test: correctness (valid signatures accepted, a modified signature rejected) and in-EVM gas of every verifier |
| `test/Micro.t.sol` | Micro-benchmark: gas of one tweakable-hash call (SHA-256 precompile and KECCAK256) |
| `vectors/*.json` | Public keys, messages and signatures (16 per set; 4 for 128s) |
| `results/onchain.csv`, `results/onchain_summary.csv` | Receipt gas of every verification transaction |
| `results/*_{sha256,keccak}_{ref,opt}.csv` | In-EVM gas from the Foundry test |

Parameter sets: `eth_ordinary` (18, 3, 9, 18, w=4), `eth_high` (20, 2, 12, 14, w=4),
`eth_extreme` (30, 3, 12, 11, w=4), `slh_dsa_128s` (63, 7, 12, 14, w=16), `slh_dsa_128f` (66, 22, 6, 33, w=16).

## Results (receipt gasUsed, mean over the signatures of each set)

| Set | Calldata (B) | gasUsed, SHA-256 | gasUsed, Keccak |
|---|---|---|---|
| eth_ordinary | 6,692 | 387,462 | 283,431 |
| eth_high | 5,668 | 319,503 | 241,926 |
| eth_extreme | 6,276 | 365,917 | 267,583 |
| SLH-DSA-128s | 8,100 | 1,000,240 | 578,158 |
| SLH-DSA-128f | 17,316 | 2,714,190 | 1,484,999 |

Execution gas (gasUsed minus the 21,000 base and the standard calldata cost, for transactions where
the EIP-7623 floor does not bind) is fitted by

    exec = G0 + g * c_v + c * chains

with c_v the verification compressions of the cost model and chains = d * len (WOTS chains):

| Hash | G0 | g (per compression) | c (per chain) | Max error |
|---|---|---|---|---|
| SHA-256 precompile | 37,906 | 363.2 | 70.1 | 1.2% |
| KECCAK256 | 38,081 | 165.7 | 116.7 | 1.7% |

The signatures are generated for the SHA-256 instantiation, so the Keccak verifier rejects them;
it runs the same computation and fails only at the final root comparison, so its gas equals that of a
valid verification. The Keccak rows serve only to compare hash costs.

A single F call costs 345 gas with the SHA-256 precompile (257 for the STATICCALL and the
precompile, 88 for loop and memory work) and 130 gas with KECCAK256 (`test/Micro.t.sol`).

## Reproduce

```sh
pip install slh-dsa                      # reference signer (pure Python, FIPS 205)
python tools/gen_vectors.py              # writes vectors/*.json (128s takes a few minutes)
python tools/gen_opt.py                  # writes src/SlhDsaVerifierSha.sol and src/SlhDsaVerifierKeccak.sol
forge test                               # correctness and in-EVM gas (solc 0.8.28, via-IR, Prague)
anvil --hardfork prague --gas-limit 60000000 &
forge build && python tools/onchain.py eth_ordinary eth_high eth_extreme slh_dsa_128s slh_dsa_128f
```

Measured with Foundry 1.5.1 and solc 0.8.28 (optimizer, 200 runs, via-IR).
