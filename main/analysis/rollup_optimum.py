"""Price-dependent optima on the rollups (Sections 6 and 7).

On OP Mainnet and Arbitrum One a signature pays a layer-1 data fee (size) and a layer-2 execution
fee (verification gas), so the optimum depends on the price ratio. This script prices every
feasible candidate of explore.py at the 10th, 50th and 90th percentile window prices (all prices
at the same percentile) and reports the cheapest set per class and decomposition stage.

Usage : python main/analysis/rollup_optimum.py      (from the repository root)
Output: main/results/explore/rollup_optimum.csv
"""
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP = ROOT / "results" / "explore"
BQ = ROOT / "results" / "bigquery"

OP_BASEFEE_SCALAR, OP_BLOB_SCALAR, OP_FASTLZ_COEF = 5227e-6, 1_014_213e-6, 0.8365
STAGE_FAMILIES = {
    "S1": {"SPX": [16]},
    "S2": {"SPX": [4, 16, 256]},
    "S3": {"SPX": [4, 16, 256], "W+C": None},
    "S4": {"SPX": [4, 16, 256], "W+C": None, "W+C_F+C": None},
    "S5": {"SPX": [4, 16, 256], "W+C": None, "W+C_F+C": None, "W+C_P+FP": None},
}

cand = pd.read_csv(EXP / "candidates.csv")
p1 = pd.read_csv(BQ / "50_prices.csv")
p2 = pd.read_csv(BQ / "51_l2_prices.csv")


def px(df, chain, item, q):
    return float(df[(df.chain == chain) & (df["item"] == item)][q].iloc[0])


def in_stage(row, fams):
    allowed = fams.get(row["family"], "absent")
    return allowed is None or (allowed != "absent" and row["w"] in allowed)


rows = []
for q in ("p10", "p50", "p90"):
    base, blob = px(p1, "ethereum", "base_fee", q), px(p1, "ethereum", "blob_base_fee", q)
    op_gp, arb_gp = px(p2, "optimism", "gas_price", q), px(p2, "arbitrum", "gas_price", q)
    d = cand["size"] + 32
    gas = cand["eth_gas_sha256"]
    cand[f"op_gwei_{q}"] = (OP_FASTLZ_COEF * d * (OP_BASEFEE_SCALAR * 16 * base + OP_BLOB_SCALAR * blob)
                            + gas * op_gp) / 1e9
    cand[f"op_l1_share_{q}"] = (OP_FASTLZ_COEF * d * (OP_BASEFEE_SCALAR * 16 * base + OP_BLOB_SCALAR * blob)
                                / 1e9) / cand[f"op_gwei_{q}"]
    cand[f"arb_gwei_{q}"] = (d * blob + gas * arb_gp) / 1e9
    for stage, fams in STAGE_FAMILIES.items():
        sub = cand[cand.apply(in_stage, axis=1, fams=fams)]
        for cls in ("ordinary", "high", "extreme"):
            c = sub[sub["class"] == cls]
            for chain, col in (("OP Mainnet", f"op_gwei_{q}"), ("Arbitrum One", f"arb_gwei_{q}")):
                b = c.loc[c[col].idxmin()]
                rows.append({"prices": q, "stage": stage, "class": cls, "chain": chain,
                             "fee_gwei": round(b[col], 3),
                             "l1_share": round(b[f"op_l1_share_{q}"], 3) if chain == "OP Mainnet" else None,
                             **{k: b[k] for k in ("family", "h", "d", "a", "k", "w", "size", "sg", "sv",
                                                  "sec_at_10x")}})

out = pd.DataFrame(rows)
out.to_csv(EXP / "rollup_optimum.csv", index=False)
pd.set_option("display.width", 220)
print(out[out.stage.isin(["S1", "S5"])].to_string(index=False))
