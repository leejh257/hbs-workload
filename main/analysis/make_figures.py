"""Figures and tables for Section 4 (workload measurement).

Usage : python main/analysis/make_figures.py        (run from the repository root)
Input : main/results/bigquery/*.csv, main/results/mempool/*.csv
Output: main/figures/fig_ccdf.{svg,pdf}, main/figures/fig_mempool.{svg,pdf},
        main/figures/table_workload.{csv,tex}, main/figures/table_mempool.{csv,tex}
Window: 2026-05-01 to 2026-10-31 (184 days).
"""
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
BQ = ROOT / "results" / "bigquery"
MP = ROOT / "results" / "mempool"
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)

# Validated categorical palette (fixed order; colour follows the entity in every panel)
C = {"eth": "#257de0", "arb": "#f47230", "op": "#00b894", "pol": "#f2a600",
     "btc": "#ee7fac", "aa": "#008a17", "7702": "#6a4ce2"}
INK, INK2, GRID = "#191919", "#666666", "#e6e6e6"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.titlesize": 8.5,
    "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7,
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
    "ytick.color": INK2, "axes.linewidth": 0.6, "svg.fonttype": "none",
    "pdf.fonttype": 42,
})

bq = pd.concat([pd.read_csv(f) for f in sorted(BQ.glob("[1-4]*.csv"))], ignore_index=True)


def hist(pop: str, metric: str) -> pd.DataFrame:
    d = bq[(bq.population == pop) & (bq.metric == metric) & (bq.stat == "hist")]
    return d.sort_values("bin_lo")[["bin_lo", "keys", "signatures"]].reset_index(drop=True)


def ccdf(pop: str, metric: str):
    h = hist(pop, metric)
    n = h["keys"].sum()
    tail = h["keys"][::-1].cumsum()[::-1]
    return h["bin_lo"].to_numpy(), (tail / n).to_numpy()


def stat(pop: str, metric: str, kind: str, lvl: int):
    d = bq[(bq.population == pop) & (bq.metric == metric) & (bq.stat == kind) & (bq.bin_lo == lvl)]
    return int(d["keys"].iloc[0]) if len(d) else None


def style(ax, xlabel):
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xlim(0.7, 2 ** 26)
    ax.set_xticks([2 ** k for k in range(0, 26, 5)],
                  [rf"$2^{{{k}}}$" for k in range(0, 26, 5)])
    ax.minorticks_off()
    ax.set_xlabel(xlabel)
    ax.grid(True, which="major", color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for e, lab in ((10, r"$2^{10}$"), (16, r"$2^{16}$"), (20, r"$2^{20}$")):
        ax.axvline(2 ** e, color=INK2, lw=0.7, ls=(0, (3, 3)), zorder=1.5)
        ax.text(2 ** e * 1.15, 0.9, lab, color=INK2, fontsize=6.5, va="top",
                transform=ax.get_xaxis_transform())


def plot_series(ax, series):
    for key, pop, metric, label, marker in series:
        x, y = ccdf(pop, metric)
        ax.plot(x, y, color=C[key], lw=1.4, marker=marker, ms=3.2,
                markeredgecolor="white", markeredgewidth=0.5, label=label)
    ax.legend(frameon=False, fontsize=6.8, loc="lower left", handlelength=2.2)


# ---------------------------------------------------------------- Figure: CCDF
fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.6), sharey=True)
plot_series(axes[0], [
    ("eth", "eoa", "n_win", "Ethereum EOA", "o"),
    ("arb", "arbitrum", "n_win", "Arbitrum One", "s"),
    ("op", "optimism", "n_win", "OP Mainnet", "^"),
    ("pol", "polygon", "n_win", "Polygon PoS", "D"),
    ("btc", "bitcoin", "n_win", "Bitcoin (single-key)", "v"),
])
axes[0].set_title("(a) Chains, 184 days", loc="left")
plot_series(axes[1], [
    ("eth", "eoa", "n_win", "Ethereum EOA", "o"),
    ("aa", "smart_account", "user_ops", "ERC-4337 account", "P"),
    ("7702", "eip7702_combined", "user_ops_plus_eoa_tx", "EIP-7702 (UserOps + tx)", "X"),
])
axes[1].set_title("(b) Ethereum accounts, 184 days", loc="left")
plot_series(axes[2], [
    ("eth", "eoa", "lifetime", "Ethereum EOA", "o"),
    ("arb", "arbitrum", "lifetime", "Arbitrum One", "s"),
    ("op", "optimism", "lifetime", "OP Mainnet", "^"),
    ("pol", "polygon", "lifetime", "Polygon PoS", "D"),
])
axes[2].set_title("(c) Lifetime (nonce)", loc="left")
for ax, xl in zip(axes, ("Signatures per key", "Signatures per key", "Signatures per key")):
    style(ax, xl)
axes[0].set_ylabel("Fraction of keys with at least x signatures")
axes[0].set_ylim(1e-8, 1.5)
fig.tight_layout(w_pad=1.0)
for ext in ("svg", "pdf"):
    fig.savefig(OUT / f"fig_ccdf.{ext}", bbox_inches="tight")
plt.close(fig)

# ------------------------------------------------------- Figure: mempool panels
act = pd.read_csv(MP / "activity_multiplier.csv")
cov = pd.read_csv(MP / "coverage_by_activity.csv")
labels = [a.split(") ")[1].replace("-", "–") for a in act["activity"]]
xs = range(len(labels))

fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.5))
ax = axes[0]
ax.plot(xs, act["multiplier"], color=C["eth"], lw=1.4, marker="o", ms=4,
        markeredgecolor="white", markeredgewidth=0.5, label="All keys in class (aggregate)")
ax.plot(xs, act["key_ratio_p99"], color=C["7702"], lw=1.4, marker="s", ms=4,
        markeredgecolor="white", markeredgewidth=0.5, label="99th-percentile key")
for x, v in zip(xs, act["key_ratio_p99"]):
    ax.annotate(f"{v:.2f}", (x, v), textcoords="offset points", xytext=(0, 5),
                ha="center", fontsize=6.5, color=INK)
ax.set_ylabel("Signatures per landed transaction")
ax.set_title("(a) Replacement multiplier", loc="left")
ax.set_ylim(0.95, 2.1)

ax = axes[1]
cov_by = dict(zip(cov["span_class"].str.split(") ", regex=False).str[1], cov["coverage_pct"]))
cov_vals = [cov_by.get(a.split(") ")[1]) for a in act["activity"]]
ax.plot(xs, act["pct_keys_with_extra"], color=C["arb"], lw=1.4, marker="^", ms=4,
        markeredgecolor="white", markeredgewidth=0.5, label="Keys with a replaced signature")
xc = [x for x, v in zip(xs, cov_vals) if x > 0]
yc = [v for x, v in zip(xs, cov_vals) if x > 0]
ax.plot(xc, yc, color=C["eth"], lw=1.4, marker="o", ms=4, markeredgecolor="white",
        markeredgewidth=0.5, label="Used nonces seen in public mempool")
last = len(labels) - 1
for x, v in zip(xs, act["pct_keys_with_extra"]):
    dy = -11 if x == last - 1 else 6
    ax.annotate(f"{v:.1f}", (x, v), textcoords="offset points", xytext=(0, dy),
                ha="center", fontsize=6.5, color=INK)
for x, v in zip(xc, yc):
    dy = -11 if x == last else 6
    ax.annotate(f"{v:.1f}", (x, v), textcoords="offset points", xytext=(0, dy),
                ha="center", fontsize=6.5, color=INK)
ax.set_ylabel("Percent")
ax.set_ylim(0, 105)
ax.set_title("(b) Replacement exposure and public visibility", loc="left")

for ax in axes:
    ax.set_xticks(list(xs), labels)
    ax.set_xlabel("Landed transactions per key in 184 days")
    ax.grid(True, axis="y", color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
axes[0].legend(frameon=False, fontsize=6.8, loc="upper left")
axes[1].legend(frameon=False, fontsize=6.8, loc="center left", bbox_to_anchor=(0.0, 0.52))
for ax in axes:
    ax.tick_params(axis="x", labelsize=6.5)
fig.tight_layout(w_pad=1.5)
for ext in ("svg", "pdf"):
    fig.savefig(OUT / f"fig_mempool.{ext}", bbox_inches="tight")
plt.close(fig)

# ------------------------------------------------------------------ Tables
rows = []
spec = [
    ("Ethereum EOA", "eoa", "n_win", "annual_rate", "lifetime"),
    ("Arbitrum One EOA", "arbitrum", "n_win", "annual_rate", "lifetime"),
    ("OP Mainnet EOA", "optimism", "n_win", "annual_rate", "lifetime"),
    ("Polygon PoS EOA", "polygon", "n_win", "annual_rate", "lifetime"),
    ("Bitcoin single-key address", "bitcoin", "n_win", "annual_rate", None),
    ("ERC-4337 account", "smart_account", "user_ops", None, None),
    ("EIP-7702 account (UserOps + tx)", "eip7702_combined", "user_ops_plus_eoa_tx", None, None),
]
for name, pop, win, rate, life in spec:
    h = hist(pop, win)
    rows.append({
        "population": name,
        "keys": int(h["keys"].sum()),
        "signatures_184d": int(h["signatures"].sum()),
        "p50": stat(pop, win, "quantile", 500), "p99": stat(pop, win, "quantile", 990),
        "p999": stat(pop, win, "quantile", 999), "max": stat(pop, win, "quantile", 1000),
        "annual_gt_2e20": stat(pop, rate, "over", 20) if rate else None,
        "lifetime_gt_2e20": stat(pop, life, "over", 20) if life else None,
        "lifetime_gt_2e24": stat(pop, life, "over", 24) if life else None,
    })
tw = pd.DataFrame(rows)
tw.to_csv(OUT / "table_workload.csv", index=False)


def fmt(v):
    if v is None or pd.isna(v):
        return "--"
    return f"{int(v):,}"


with open(OUT / "table_workload.tex", "w") as f:
    f.write("% Signatures per key, 2026-05-01 to 2026-10-31 (184 days)\n")
    f.write("\\begin{tabular}{lrrrrrrrr}\n\\hline\n")
    f.write("Population & Keys & p50 & p99 & p99.9 & Max & "
            "$>2^{20}$/yr & Life $>2^{20}$ & Life $>2^{24}$\\\\\n\\hline\n")
    for r in rows:
        f.write(" & ".join([r["population"], fmt(r["keys"]), fmt(r["p50"]), fmt(r["p99"]),
                            fmt(r["p999"]), fmt(r["max"]), fmt(r["annual_gt_2e20"]),
                            fmt(r["lifetime_gt_2e20"]), fmt(r["lifetime_gt_2e24"])]) + "\\\\\n")
    f.write("\\hline\n\\end{tabular}\n")

tm = act.copy()
tm["coverage_pct"] = cov_vals
tm.to_csv(OUT / "table_mempool.csv", index=False)
with open(OUT / "table_mempool.tex", "w") as f:
    f.write("% Ethereum public mempool, 2026-05-02 to 2026-10-30 (edge days trimmed)\n")
    f.write("\\begin{tabular}{lrrrrrr}\n\\hline\n")
    f.write("Landed tx per key & Keys & Multiplier & Keys replaced (\\%) & "
            "p99 key ratio & Max key ratio & Coverage (\\%)\\\\\n\\hline\n")
    for lab, (_, r), cv in zip(labels, tm.iterrows(), cov_vals):
        tl = lab.replace("–", "--").replace(">", "$>$")
        f.write(f"{tl} & {int(r['keys']):,} & {r['multiplier']:.4f} & "
                f"{r['pct_keys_with_extra']:.2f} & {r['key_ratio_p99']:.3f} & "
                f"{r['key_ratio_max']:.2f} & {'--' if lab == '1' else f'{cv:.1f}'}\\\\\n")
    f.write("\\hline\n\\end{tabular}\n")
    f.write("% Coverage classes use the span of landed nonces over all days; the other columns\n"
            "% use landed transactions after trimming the first and last day.\n")

print(tw.to_string(index=False))
print("figures written to", OUT)
