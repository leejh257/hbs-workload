"""Design-space exploration for chain- and class-specific hash-based signature parameters (Section 6).

For every budget class (Section 4.5) and every scheme family of the SoK decomposition
(FIPS 205 structure, WOTS+C, FORS+C, PORS+FP), enumerate (h, d, a, k, w), keep the sets that
reach 128-bit security after m * q signatures, apply the constraints of Section 5.4, and
evaluate the per-chain cost functions of Section 5.2.

Usage : python explore.py [--workers N] [--out ../results/explore]
Needs : the SPHINCS-Parameters model (./setup_upstream.sh, or SPHINCS_PARAMS=/path)
Output: candidates.csv (every feasible set), optimum.csv (best set per class, stage and chain
        objective), timing.csv (date, workers, tasks, sets evaluated, feasible sets, wall time s,
        phase-1 time s, logical CPUs)

engine.py and paths.py are copied from the SoK repository hbs-blockchain-signature-limits.
"""
import argparse
import csv
import math
import os
import time
from multiprocessing import Pool

import paths  # noqa: F401
import engine as E

M = E.M
N_PK = 32                                  # public key revealed at spend (PK.seed + PK.root)

# Budget classes of Section 4.5: log2 of m * q, and the signing bound C_s of Section 5.4
CLASSES = {
    "ordinary": {"q": 16, "m": 2.0, "cs_max": 97_354},     # 2 s on a 168 MHz Cortex-M4
    "high":     {"q": 20, "m": 2.0, "cs_max": 1_052_631},  # 50 ms on a server core
    "extreme":  {"q": 24, "m": 2.0, "cs_max": 1_052_631},
}
FAMILIES = {                               # family -> allowed w
    "SPX": [4, 16, 256],
    "W+C": [16, 32, 64, 128, 256],
    "W+C_F+C": [16, 32, 64, 128, 256],
    "W+C_P+FP": [16, 32, 64, 128, 256],
}
STAGES = [("S1 FIPS 205 structure, w=16", {"SPX": [16]}),
          ("S2 + choice of w", {"SPX": [4, 16, 256]}),
          ("S3 + WOTS+C", {"SPX": [4, 16, 256], "W+C": FAMILIES["W+C"]}),
          ("S4 + FORS+C", {"SPX": [4, 16, 256], "W+C": FAMILIES["W+C"],
                           "W+C_F+C": FAMILIES["W+C_F+C"]}),
          ("S5 + PORS+FP", FAMILIES)]

# Chain cost functions (Section 5.2), in resource units
GAS_PER_HASH = {"sha256": 258, "keccak": 79}
G0 = 5_000
GAS_CAP = 2 ** 24
BTC_CPB_MAX = 5.26                         # 1 s per full block at 47.5 ns per compression


def eth_gas(size: int, sv: int, g: int, floor_per_byte: int = 40) -> int:
    d = size + N_PK
    return max(16 * d + G0 + sv * g, floor_per_byte * d)


def chain_units(size: int, sv: int) -> dict:
    d = size + N_PK
    return {
        "btc_vbytes": d / 4,
        "eth_gas_sha256": eth_gas(size, sv, GAS_PER_HASH["sha256"]),
        "eth_gas_keccak": eth_gas(size, sv, GAS_PER_HASH["keccak"]),
        "eth_gas_sha256_glam": eth_gas(size, sv, GAS_PER_HASH["sha256"], 64),
        "pol_gas_sha256": 16 * d + G0 + sv * GAS_PER_HASH["sha256"],
        "rollup_l1_bytes": d,
    }


def sec(fam: str, h: int, a: int, k: int, qlog: float) -> float:
    f = E.sec_pors if fam == "W+C_P+FP" else E.sec_fors
    return f(h, a, k, qlog)


SEC = {}   # (class, layer, h, a) -> (k, sec at budget, at 10x, at 100x), filled by phase 1


def task(args):
    """All feasible sets for one (class, family, h, a)."""
    cls, fam, h, a = args
    c = CLASSES[cls]
    out, tried = [], 0
    layer = "pors" if fam == "W+C_P+FP" else "fors"
    k, s_b, s_10, s_100 = SEC[(cls, layer, h, a)]
    if k is None or (fam == "W+C_P+FP" and k * 2 ** a > 2 ** 20):
        return 0, []
    for d in range(1, h + 1):
        if h % d or h // d > 22:
            continue
        for w in FAMILIES[fam]:
            tried += 1
            try:
                m = (M.spx_metrics(h, d, k, a, w) if fam == "SPX"
                     else M.scheme_metrics(fam, h, d, k, a, w, E.SWN.get(w, 0)))
            except Exception:
                continue
            if m["sg"] > c["cs_max"]:
                continue
            u = chain_units(m["size"], m["sv"])
            if u["eth_gas_sha256"] > GAS_CAP:
                continue
            row = {"class": cls, "family": fam, "h": h, "d": d, "a": a, "k": k, "w": w,
                   "size": m["size"], "sg": m["sg"], "sv": m["sv"],
                   "cpb": round(m["sv"] / (m["size"] + N_PK), 4),
                   "btc_ok": m["sv"] / (m["size"] + N_PK) <= BTC_CPB_MAX,
                   "sec_at_budget": s_b, "sec_at_10x": s_10, "sec_at_100x": s_100,
                   **u}
            out.append(row)
    return tried, out


def few_time(args):
    """Phase 1a: minimal k and its security at 1x, 10x and 100x the effective budget for one
    (class, few-time layer, h, a). Shared by every family that uses the same layer."""
    cls, layer, h, a = args
    c = CLASSES[cls]
    qlog = c["q"] + math.log2(c["m"])
    k = E.mink(layer, h, a, qlog)
    if k is None:
        return args, (None, None, None, None)
    fam = "W+C_P+FP" if layer == "pors" else "SPX"
    return args, (k, round(sec(fam, h, a, k, qlog), 2),
                  round(sec(fam, h, a, k, qlog + math.log2(10)), 2),
                  round(sec(fam, h, a, k, qlog + math.log2(100)), 2))


def octopus_table(tk):
    """Phase 1b: the PORS+FP grinding-cost table for one (t, k), the expensive shared input."""
    t, k = tk
    return tk, dict(M.interleave_cost_table(t, k))


def init_worker(tables, sec_map):
    """Phase 2 worker: install the precomputed grinding-cost tables and few-time security."""
    M._INTERLEAVE_CACHE.update(tables)
    SEC.update(sec_map)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "results", "explore"))
    ap.add_argument("--hspan", type=int, default=12, help="h from q-hspan to q+hspan")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    # One task per (class, family, h, a). The few-time security sum costs about
    # sqrt(2^(Q - h)) terms, and PORS+FP adds its message grinding, so the tasks are
    # scheduled longest first by that estimate (longest-processing-time rule).
    tasks = [(cls, fam, h, aa) for cls, c in CLASSES.items() for fam in FAMILIES
             for h in range(max(4, c["q"] - a.hspan), c["q"] + a.hspan + 1)
             for aa in range(4, (20 if fam == "W+C_P+FP" else 24) + 1)]

    def est(t):
        cls, fam, h, _ = t
        lam = 2.0 ** (CLASSES[cls]["q"] + math.log2(CLASSES[cls]["m"]) - h)
        return (10 if fam == "W+C_P+FP" else 1) * (math.sqrt(lam) + 10)
    tasks.sort(key=est, reverse=True)
    t0 = time.time()
    # Phase 1: the PORS+FP grinding-cost tables depend only on (t, k) and dominate the run time,
    # so they are computed once, in parallel, and shared with every phase-2 worker.
    ft_units = sorted({(cls, "pors" if fam == "W+C_P+FP" else "fors", h, aa)
                       for cls, fam, h, aa in tasks},
                      key=lambda u: -2.0 ** (CLASSES[u[0]]["q"] - u[2]))
    with Pool(a.workers) as pool:
        sec_map = dict(pool.map(few_time, ft_units, chunksize=1))
        tk = sorted({(v[0] * 2 ** u[3], v[0]) for u, v in sec_map.items()
                     if u[1] == "pors" and v[0] is not None and v[0] * 2 ** u[3] <= 2 ** 20},
                    key=lambda x: -x[0] * x[1])
        tables = dict(pool.map(octopus_table, tk, chunksize=1))
    t1 = time.time()
    # Phase 2: enumerate every (class, family, h, a) with the tables in place.
    with Pool(a.workers, initializer=init_worker, initargs=(tables, sec_map)) as pool:
        results = pool.map(task, tasks, chunksize=1)
    wall = time.time() - t0
    print(f"phase 1: {len(sec_map)} few-time security units and {len(tk)} grinding tables "
          f"in {t1 - t0:.1f} s; "
          f"phase 2: {len(tasks)} tasks in {wall - (t1 - t0):.1f} s", flush=True)
    tried = sum(r[0] for r in results)
    rows = [row for r in results for row in r[1]]
    print(f"{len(tasks)} tasks, {tried:,} parameter sets evaluated, {len(rows):,} feasible, "
          f"{wall:.1f} s with {a.workers} workers", flush=True)

    with open(os.path.join(a.out, "candidates.csv"), "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    with open(os.path.join(a.out, "timing.csv"), "a", newline="") as f:
        csv.writer(f).writerow([time.strftime("%Y-%m-%d %H:%M"), a.workers, len(tasks), tried,
                                len(rows), round(wall, 1), round(t1 - t0, 1), os.cpu_count()])

    objectives = {"bitcoin (vbytes)": ("btc_vbytes", True),
                  "ethereum (gas, SHA-256)": ("eth_gas_sha256", False),
                  "ethereum (gas, Keccak)": ("eth_gas_keccak", False),
                  "ethereum (gas, SHA-256, Glamsterdam)": ("eth_gas_sha256_glam", False),
                  "polygon (gas, SHA-256)": ("pol_gas_sha256", False),
                  "rollup L1 data (bytes)": ("rollup_l1_bytes", False)}
    opt = []
    for cls in CLASSES:
        for stage, allowed in STAGES:
            pool_rows = [r for r in rows if r["class"] == cls and r["family"] in allowed
                         and r["w"] in allowed[r["family"]]]
            for obj, (col, needs_btc) in objectives.items():
                cand = [r for r in pool_rows if (r["btc_ok"] or not needs_btc)]
                if not cand:
                    continue
                best = min(cand, key=lambda r: (r[col], r["size"], r["sg"]))
                opt.append({"class": cls, "stage": stage, "objective": obj, "value": best[col],
                            **{k: best[k] for k in ("family", "h", "d", "a", "k", "w", "size",
                                                    "sg", "sv", "sec_at_10x", "sec_at_100x")}})
    with open(os.path.join(a.out, "optimum.csv"), "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(opt[0].keys()))
        wr.writeheader()
        wr.writerows(opt)
    for r in opt:
        if r["stage"].startswith("S5") or r["stage"].startswith("S1"):
            print(r["class"], r["stage"][:2], r["objective"], r["value"], r["family"],
                  (r["h"], r["d"], r["a"], r["k"], r["w"]), r["size"], r["sg"], r["sv"])


if __name__ == "__main__":
    main()
