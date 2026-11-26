"""Generate SLH-DSA test vectors for custom (h, d, a, k, lg w) at n = 16 (SHA2, category 1).

Uses the slhdsa reference package (FIPS 205 internal functions) for keygen, signing and
verification, and counts tweakable-hash calls made during verification.
"""
import json, os, sys, time, hashlib
from slhdsa.lowlevel.parameters import Sha2_1Parameter
import slhdsa.lowlevel.slhdsa as low
from slhdsa.lowlevel import parameters as P

SETS = {
    # name: (h, d, a, k, lgw)
    "eth_ordinary": (18, 3, 9, 18, 2),
    "eth_high": (20, 2, 12, 14, 2),
    "eth_extreme": (30, 3, 12, 11, 2),
    "slh_dsa_128s": (63, 7, 12, 14, 4),
    "slh_dsa_128f": (66, 22, 6, 33, 4),
}

def param(h, d, a, k, lgw):
    m = (k * a + 7) // 8 + (h - h // d + 7) // 8 + (h // d + 7) // 8
    return Sha2_1Parameter(0, 16, h, d, h // d, a, k, lgw, m)

def sha(b):
    return hashlib.sha256(b).digest()

def adrs(layer, tree, typ, w1, w2, w3):
    return bytes([layer]) + tree.to_bytes(8, "big") + bytes([typ]) + w1.to_bytes(4, "big") + w2.to_bytes(4, "big") + w3.to_bytes(4, "big")

def my_verify(msg, sig, seed, root, h, d, a, k, lgw, m):
    """Independent re-implementation (same logic as the Solidity verifier); returns (ok, thash_calls)."""
    n = 16; hp = h // d; w = 1 << lgw
    len1 = (8 * n + lgw - 1) // lgw
    import math
    len2 = int(math.log2(len1 * (w - 1))) // lgw + 1
    calls = [0]
    def th(ad, x):
        calls[0] += 1
        return sha(seed + bytes(64 - n) + ad + x)[:n]
    r = sig[:n]
    inner = sha(r + seed + root + msg)
    mg = b"".join(sha(r + seed + inner + c.to_bytes(4, "big")) for c in range((m + 31) // 32))[:m]
    md_b = (k * a + 7) // 8; tb = (h - hp + 7) // 8; lb = (hp + 7) // 8
    bits = int.from_bytes(mg[:md_b], "big"); nb = md_b * 8
    tree = int.from_bytes(mg[md_b:md_b + tb], "big") % (1 << (h - hp))
    leaf = int.from_bytes(mg[md_b + tb:md_b + tb + lb], "big") % (1 << hp)
    off = n; roots = b""
    for i in range(k):
        idx = (bits >> (nb - (i + 1) * a)) & ((1 << a) - 1)
        ti = (i << a) + idx
        node = th(adrs(0, tree, 3, leaf, 0, ti), sig[off:off + n]); off += n
        for j in range(a):
            au = sig[off:off + n]; off += n
            if (idx >> j) & 1 == 0:
                ti >>= 1; node = th(adrs(0, tree, 3, leaf, j + 1, ti), node + au)
            else:
                ti = (ti - 1) >> 1; node = th(adrs(0, tree, 3, leaf, j + 1, ti), au + node)
        roots += node
    node = th(adrs(0, tree, 4, leaf, 0, 0), roots)
    for layer in range(d):
        v = int.from_bytes(node, "big"); digs = []; cs = 0
        for i in range(len1):
            dg = (v >> (8 * n - (i + 1) * lgw)) & (w - 1); digs.append(dg); cs += w - 1 - dg
        l2b = len2 * lgw; lby = (l2b + 7) // 8; cs <<= (8 - l2b % 8) % 8
        for i in range(len2):
            digs.append((cs >> (lby * 8 - (i + 1) * lgw)) & (w - 1))
        pk = b""
        for i, dg in enumerate(digs):
            x = sig[off + i * n: off + (i + 1) * n]
            for j in range(dg, w - 1):
                x = th(adrs(layer, tree, 0, leaf, i, j), x)
            pk += x
        off += (len1 + len2) * n
        node = th(adrs(layer, tree, 1, leaf, 0, 0), pk)
        ti = leaf
        for kk in range(hp):
            au = sig[off:off + n]; off += n
            if (leaf >> kk) & 1 == 0:
                ti >>= 1; node = th(adrs(layer, tree, 2, 0, kk + 1, ti), node + au)
            else:
                ti = (ti - 1) >> 1; node = th(adrs(layer, tree, 2, 0, kk + 1, ti), au + node)
        leaf = tree & ((1 << hp) - 1); tree >>= hp
    return node == root, calls[0]

def main(names):
    out = os.path.join(os.path.dirname(__file__), "..", "vectors")
    for name in names:
        h, d, a, k, lgw = SETS[name]
        par = param(h, d, a, k, lgw)
        t0 = time.time()
        sk, pk = low.keygen(par)
        NV = int(os.environ.get("NV", "16"))
        msgs, sigs, calls = [], [], []
        for v in range(NV):
            msg = hashlib.sha256(b"workload-aware hbs gas benchmark %d" % v).digest()
            sig = low.sign(msg, sk, par, randomize=False)
            assert low.verify(msg, sig, pk, par)
            ok, ncalls = my_verify(msg, sig, pk[0], pk[1], h, d, a, k, lgw, par.m)
            assert ok, "independent verifier disagrees"
            msgs.append(msg.hex()); sigs.append(sig.hex()); calls.append(ncalls)
        t1 = time.time()
        bad = bytearray(sig); bad[-1] ^= 1
        assert not low.verify(msg, bytes(bad), pk, par)
        assert not my_verify(msg, bytes(bad), pk[0], pk[1], h, d, a, k, lgw, par.m)[0]
        rec = dict(name=name, h=h, d=d, a=a, k=k, lgw=lgw, m=par.m, sig_len=len(sig),
                   verify_thash_calls=calls, msgs=msgs, sigs=sigs,
                   pk_seed=pk[0].hex(), pk_root=pk[1].hex(), sign_seconds=round(t1 - t0, 1))
        ncalls = sum(calls) / len(calls)
        json.dump(rec, open(os.path.join(out, f"{name}.json"), "w"))
        print(name, "sig", len(sig), "thash calls", ncalls, "keygen+sign %.1fs" % (t1 - t0), flush=True)

if __name__ == "__main__":
    main(sys.argv[1:] or list(SETS))
