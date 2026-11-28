"""Sensitivity analyses for Section 8.

Usage : python main/analysis/sensitivity.py           (from the repository root)
Input : results/explore/candidates.csv (base: margin 2, wallet 2 s)
        results/sensitivity/{margin4,margin10,wallet1s,wallet10s}/candidates.csv
        results/bigquery/50_prices.csv, 51_l2_prices.csv
Output: results/sensitivity/*.csv and a printed summary

Recommendations follow Section 7: cheapest feasible set per chain and class at median prices,
subject to at least 100 bits at ten times the effective budget.
"""
import pathlib

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = RES / "sensitivity"
OUT.mkdir(exist_ok=True)

p1 = pd.read_csv(RES / "bigquery" / "50_prices.csv")
p2 = pd.read_csv(RES / "bigquery" / "51_l2_prices.csv")
OPB, OPBLOB, OPC = 5227e-6, 1_014_213e-6, 0.8365
PK = 32
# Measured EVM verification gas (gasbench/): G0 + g * compressions + c * WOTS chains
EVM_GAS = {"sha256": (37_906, 363.2, 70.1), "keccak": (38_081, 165.7, 116.7)}
BASE_128S = {"size": 7856, "sv": 2193, "chains": 245}


def px(df, chain, item, q="p50"):
    return float(df[(df.chain == chain) & (df["item"] == item)][q].iloc[0])


def gas(df, h="sha256", floor=40):
    g0, g, c = EVM_GAS[h]
    d = df["size"] + PK
    std = 16 * d + g0 + g * df["sv"] + c * df["chains"]
    return std.where(std > floor * d, floor * d)


def fees(df, q="p50", arb_l1_scale=1.0, pol_floor=False, eth_h="sha256", eth_floor=40):
    """Fee per signature on each chain at price percentile q."""
    base, tip = px(p1, "ethereum", "base_fee", q), px(p1, "ethereum", "priority_fee", q)
    blob, fr = px(p1, "ethereum", "blob_base_fee", q), px(p1, "bitcoin", "feerate", q)
    op, arb, pol = (px(p2, n, "gas_price", q) for n in ("optimism", "arbitrum", "polygon"))
    d = df["size"] + PK
    g_eth = gas(df, eth_h, eth_floor)
    g_sha = gas(df)
    g_pol = gas(df, "sha256", 40 if pol_floor else 0)
    return pd.DataFrame({
        "btc": fr * d / 4,
        "eth": g_eth * (base + tip) / 1e9,
        "op": (OPC * d * (OPB * 16 * base + OPBLOB * blob) + g_sha * op) / 1e9,
        "arb": (arb_l1_scale * d * blob + g_sha * arb) / 1e9,
        "pol": g_pol * pol / 1e18,
    }, index=df.index)


def baseline(q="p50", **kw):
    b = pd.DataFrame([BASE_128S])
    return fees(b, q, **kw).iloc[0]


def pick(cand, chain, cls, fee):
    c = cand[(cand["class"] == cls) & (cand.sec_at_10x >= 100)]
    if chain == "btc":
        c = c[c.btc_ok]
    return c.loc[fee.loc[c.index, chain].idxmin()]


CHAINS = ["btc", "eth", "op", "arb", "pol"]
CLASSES = ["ordinary", "high", "extreme"]
base = pd.read_csv(RES / "explore" / "candidates.csv")
f50 = fees(base)
b50 = baseline()
rec = {(ch, cl): pick(base, ch, cl, f50) for ch in CHAINS for cl in CLASSES}
key = ["family", "h", "d", "a", "k", "w"]

# 0. Recommended sets (Table 3 of Section 7) and the best set of the SLH-DSA construction
rows = []
for cl in CLASSES:
    for ch in CHAINS:
        spx = base[base.family == "SPX"]
        for label, r in (("any", rec[(ch, cl)]), ("FIPS structure", pick(spx, ch, cl, f50.loc[spx.index]))):
            rows.append({"cls": cl, "chain": ch, "set": label, "fam": r["family"],
                         "params": f"h={r.h},d={r.d},a={r.a},k={r.k},w={r.w}", "size": r["size"], "sg": r["sg"],
                         "sv": r["sv"], "fee": f50.loc[r.name, ch], "rel": round(f50.loc[r.name, ch] / b50[ch], 4),
                         "s10": r["sec_at_10x"], "s100": r["sec_at_100x"],
                         "eth_gas": r["eth_gas_sha256"], "exec_gas": r["exec_gas_sha256"]})
pd.DataFrame(rows).to_csv(RES / "explore" / "recommended.csv", index=False)

# 1. Margin and wallet-bound variants: fee of the optimum relative to the base recommendation
rows = []
variants = {"margin 2 (base)": (base, CLASSES), "margin 4": (None, CLASSES), "margin 10": (None, CLASSES),
            "wallet 1 s": (None, ["ordinary"]), "wallet 10 s": (None, ["ordinary"])}
paths = {"margin 4": "margin4", "margin 10": "margin10", "wallet 1 s": "wallet1s", "wallet 10 s": "wallet10s"}
for name, (df, classes) in variants.items():
    if df is None:
        df = pd.read_csv(OUT / paths[name] / "candidates.csv")
    f = fees(df)
    for cl in classes:
        for ch in CHAINS:
            b = pick(df, ch, cl, f)
            r = rec[(ch, cl)]
            rows.append({"variant": name, "class": cl, "chain": ch, "fee_vs_128s": round(f.loc[b.name, ch] / b50[ch], 3),
                         "fee_vs_base_rec": round(f.loc[b.name, ch] / f50.loc[r.name, ch] - 1, 3),
                         "same_set": all(b[k] == r[k] for k in key),
                         **{k: b[k] for k in key}, "size": b["size"], "sg": b["sg"], "sv": b["sv"],
                         "sec_at_10x": b["sec_at_10x"]})
t1 = pd.DataFrame(rows)
t1.to_csv(OUT / "variants.csv", index=False)

# 2. Price percentiles: does the median recommendation stay optimal, and what does it lose?
rows = []
for q in ("p10", "p90"):
    fq = fees(base, q)
    for cl in CLASSES:
        for ch in CHAINS:
            r = rec[(ch, cl)]
            best = pick(base, ch, cl, fq)
            rows.append({"prices": q, "class": cl, "chain": ch, "same_set": best.name == r.name,
                         "regret": round(fq.loc[r.name, ch] / fq.loc[best.name, ch] - 1, 4),
                         "fee_rec": fq.loc[r.name, ch], "fee_vs_128s": round(fq.loc[r.name, ch] / baseline(q)[ch], 3)})
t2 = pd.DataFrame(rows)
t2.to_csv(OUT / "prices.csv", index=False)

# 3. Ethereum pricing regimes: regret of a set chosen for one regime and deployed under another
regimes = {"SHA-256, Pectra": dict(eth_h="sha256", eth_floor=40), "Keccak, Pectra": dict(eth_h="keccak", eth_floor=40),
           "SHA-256, Glamsterdam": dict(eth_h="sha256", eth_floor=64), "Keccak, Glamsterdam": dict(eth_h="keccak", eth_floor=64)}
fr = {n: fees(base, **kw)["eth"] for n, kw in regimes.items()}
rows = []
for cl in CLASSES:
    chosen = {}
    for n in regimes:
        c = base[(base["class"] == cl) & (base.sec_at_10x >= 100)]
        chosen[n] = fr[n].loc[c.index].idxmin()
    for design in regimes:
        for deploy in regimes:
            rows.append({"class": cl, "chosen_for": design, "deployed_under": deploy,
                         "regret": round(fr[deploy][chosen[design]] / fr[deploy][chosen[deploy]] - 1, 3)})
t3 = pd.DataFrame(rows)
t3.to_csv(OUT / "eth_regimes.csv", index=False)

# 3b. Draft EIP-8311 floor of 96 gas per byte: optimum and regret of the recommended Ethereum set
rows = []
for h in ("sha256", "keccak"):
    f96 = fees(base, eth_h=h, eth_floor=96)
    b96 = baseline(eth_h=h, eth_floor=96)["eth"]
    for cl in CLASSES:
        best = pick(base, "eth", cl, f96)
        r = rec[("eth", cl)]
        rows.append({"hash": h, "class": cl, "same_set": best.name == r.name,
                     "regret": round(f96.loc[r.name, "eth"] / f96.loc[best.name, "eth"] - 1, 3),
                     "opt_vs_128s": round(f96.loc[best.name, "eth"] / b96, 3), **{k: best[k] for k in key}})
t3b = pd.DataFrame(rows)
t3b.to_csv(OUT / "eth_floor96.csv", index=False)

# 4. Arbitrum layer-1 approximation and Polygon floor
rows = []
for scale in (1, 10, 100):
    fa = fees(base, arb_l1_scale=scale)
    for cl in CLASSES:
        best = pick(base, "arb", cl, fa)
        r = rec[("arb", cl)]
        rows.append({"case": f"Arbitrum L1 price x{scale}", "class": cl, "same_set": best.name == r.name,
                     "regret": round(fa.loc[r.name, "arb"] / fa.loc[best.name, "arb"] - 1, 4),
                     **{k: best[k] for k in key}})
fp = fees(base, pol_floor=True)
for cl in CLASSES:
    best = pick(base, "pol", cl, fp)
    r = rec[("pol", cl)]
    rows.append({"case": "Polygon with EIP-7623 floor", "class": cl, "same_set": best.name == r.name,
                 "regret": round(fp.loc[r.name, "pol"] / fp.loc[best.name, "pol"] - 1, 4),
                 **{k: best[k] for k in key}})
t4 = pd.DataFrame(rows)
t4.to_csv(OUT / "approximations.csv", index=False)

pd.set_option("display.width", 220)
for t in (t1, t2, t3, t3b, t4):
    print(t.to_string(index=False), "\n")
