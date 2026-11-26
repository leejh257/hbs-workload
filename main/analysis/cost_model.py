"""Blockchain cost model for hash-based signatures (Section 5).

A signature scheme enters the model through four numbers (Section 5.1):
    sig   signature size in bytes
    pk    public-key bytes that the spend reveals (0 if already on chain)
    c_s   SHA-256 compressions to sign
    c_v   SHA-256 compressions to verify (tweakable-hash calls, one block each)
Each chain turns them into resource units (Section 5.2) and, with the window prices of
results/bigquery/50_prices.csv and 51_l2_prices.csv, into fees (Section 5.3).

Usage:  python main/analysis/cost_model.py            (from the repository root)
Output: main/figures/table_cost_units.csv and, when the price files exist, table_cost_fees.csv
"""
import math
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
BQ = ROOT / "results" / "bigquery"
OUT = ROOT / "figures"

# ---------------------------------------------------------------- constants (Section 5.2)
# Bitcoin (BIP 141): witness bytes weigh 1 WU, 4 WU = 1 vB, 4,000,000 WU per block.
BTC_WU_PER_VB = 4
BTC_BLOCK_WU = 4_000_000

# Ethereum calldata (EIP-2028, EIP-7623 in Pectra; EIP-7976 scheduled for Glamsterdam)
ETH_TX_BASE = 21_000
ETH_STD_TOKEN = 4                 # gas per token; nonzero byte = 4 tokens, zero byte = 1
ETH_FLOOR_PER_TOKEN = {"pectra": 10, "glamsterdam": 16}
ETH_TX_GAS_CAP = 2 ** 24          # EIP-7825 (Fusaka)

# Verification gas inside a verifier contract (Section 5.2), calibrated on real transactions
# to the optimized Yul verifiers in gasbench/ on a local Prague chain:
#   execution gas = G0 + g * (verification compressions) + c * (WOTS chains)
#   sha256: SHA-256 precompile 0x02 (FIPS 205 SLH-DSA-SHA2); keccak: KECCAK256 (non-standard)
EVM_GAS = {"sha256_precompile": (37_906, 363.2, 70.1), "keccak_opcode": (38_081, 165.7, 116.7)}
GAS_PER_HASH = EVM_GAS

# OP Mainnet L1 data fee (Fjord/Jovian formula, OP docs fee-parameters page)
OP_BASEFEE_SCALAR = 5227e-6
OP_BLOB_SCALAR = 1_014_213e-6
OP_FASTLZ_COEF = 0.8365           # estimatedSize per FastLZ byte (incompressible data)

# Signing time per compression
T_DESKTOP = 47.5e-9               # OpenSSL 3.0 SHA-NI, measured in the SoK (2.1 GHz Xeon)
# pqm4 (clean) sphincs-sha2-128f-simple signs in 368,575,228 Cortex-M4 cycles; the model counts
# 106,793 compressions, so about 3,451 cycles per compression, here at 168 MHz (STM32F4 class).
T_EMBEDDED = (368_575_228 / 106_793) / 168e6

# ---------------------------------------------------------------- schemes (baselines)
# SLH-DSA figures from the SPHINCS-Parameters model used in the SoK (c_v = average case).
SCHEMES = {
    "ECDSA/Schnorr (secp256k1)": {"sig": 64, "pk": 33, "c_s": 0, "c_v": 0, "native": True},
    "SLH-DSA-SHA2-128s": {"sig": 7856, "pk": 32, "c_s": 2_218_486, "c_v": 2_193, "chains": 7 * 35, "native": False},
    "SLH-DSA-SHA2-128f": {"sig": 17088, "pk": 32, "c_s": 106_793, "c_v": 6_407, "chains": 22 * 35, "native": False},
}
ECRECOVER_GAS = 3_000


def eth_tx_gas(data_bytes: int, exec_gas: int, regime: str = "pectra") -> int:
    """Gas of a transaction whose calldata is random bytes (all nonzero, 4 tokens each)."""
    tokens = 4 * data_bytes
    std = ETH_STD_TOKEN * tokens + exec_gas
    floor = ETH_FLOOR_PER_TOKEN[regime] * tokens
    return ETH_TX_BASE + max(std, floor)


def units(s: dict) -> dict:
    """Resource units of one signature on each chain (prices not applied)."""
    data = s["sig"] + s["pk"]
    r = {}
    # Bitcoin: witness bytes; verification is node CPU, not a fee
    r["btc_vbytes"] = data / BTC_WU_PER_VB
    r["btc_sigs_per_block"] = math.floor(BTC_BLOCK_WU / data)
    r["btc_verify_us"] = s["c_v"] * T_DESKTOP * 1e6
    # Ethereum smart-account verification (gas above the 21,000 base)
    for h, (g0, g, c) in EVM_GAS.items():
        exec_gas = ECRECOVER_GAS if s["native"] else round(g0 + s["c_v"] * g + s["chains"] * c)
        for regime in ETH_FLOOR_PER_TOKEN:
            r[f"eth_gas_{h}_{regime}"] = eth_tx_gas(data, exec_gas, regime) - ETH_TX_BASE
        r[f"eth_exec_gas_{h}"] = exec_gas
    # Rollups: bytes posted to layer 1 (incompressible signature data)
    r["op_l1_size_units"] = data * OP_FASTLZ_COEF
    r["arb_l1_data_units"] = data * 16
    # Signing time
    r["sign_desktop_s"] = s["c_s"] * T_DESKTOP
    r["sign_embedded_s"] = s["c_s"] * T_EMBEDDED
    return r


def price(df: pd.DataFrame, chain: str, item: str, col: str = "p50") -> float:
    row = df[(df.chain == chain) & (df["item"] == item)]
    return float(row[col].iloc[0]) if len(row) else float("nan")


def fees(u: dict, p: pd.DataFrame, l2: pd.DataFrame | None, col: str = "p50") -> dict:
    """Fees in native units: sat for Bitcoin, gwei for the EVM chains (per signature)."""
    f = {}
    f["btc_sat"] = u["btc_vbytes"] * price(p, "bitcoin", "feerate", col)
    base = price(p, "ethereum", "base_fee", col)
    tip = price(p, "ethereum", "priority_fee", col)
    blob = price(p, "ethereum", "blob_base_fee", col)
    for h in GAS_PER_HASH:
        f[f"eth_gwei_{h}"] = u[f"eth_gas_{h}_pectra"] * (base + tip) / 1e9
    # OP Mainnet layer-1 data fee for the signature bytes (wei -> gwei)
    l1_per_unit = OP_BASEFEE_SCALAR * 16 * base + OP_BLOB_SCALAR * blob
    f["op_l1_gwei"] = u["op_l1_size_units"] * l1_per_unit / 1e9
    # Arbitrum: 16 data units per compressed byte, price per unit approximated by blob cost / 16
    f["arb_l1_gwei"] = u["arb_l1_data_units"] * (blob / 16) / 1e9
    if l2 is not None:
        for net, key in (("optimism", "op"), ("arbitrum", "arb"), ("polygon", "pol")):
            gp = price(l2, net, "gas_price", col)
            gas = u["eth_gas_sha256_precompile_pectra"]
            f[f"{key}_l2_exec_gwei"] = gas * gp / 1e9
        f["op_total_gwei"] = f["op_l1_gwei"] + f["op_l2_exec_gwei"]
        f["arb_total_gwei"] = f["arb_l1_gwei"] + f["arb_l2_exec_gwei"]
    return f


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rows = []
    for name, s in SCHEMES.items():
        rows.append({"scheme": name, "sig_plus_pk_bytes": s["sig"] + s["pk"], **units(s)})
    tu = pd.DataFrame(rows)
    tu.to_csv(OUT / "table_cost_units.csv", index=False)
    pd.set_option("display.width", 200)
    print(tu.T.to_string(header=False))

    pfile, lfile = BQ / "50_prices.csv", BQ / "51_l2_prices.csv"
    if not pfile.exists():
        print(f"\n{pfile.name} not found: run main/sql/50_prices.sql to add fees.")
        return
    p = pd.read_csv(pfile)
    l2 = pd.read_csv(lfile) if lfile.exists() else None
    frows = []
    for (name, s), (_, u) in zip(SCHEMES.items(), tu.iterrows()):
        for col in ("p10", "p50", "p90"):
            frows.append({"scheme": name, "price_quantile": col, **fees(u.to_dict(), p, l2, col)})
    tf = pd.DataFrame(frows)
    tf.to_csv(OUT / "table_cost_fees.csv", index=False)
    print(tf.to_string(index=False))


if __name__ == "__main__":
    main()
