"""Shared cost model and FORS / PORS+FP security in SHA-256 compressions.

Sizes, signing, verification and key-generation costs come from the
Blockstream SPHINCS-Parameters model (tests/model.py). Security of the
few-time layer averages over the number of signatures that reuse one
few-time key, with a Poisson approximation of Bin(q, 2^-h).
"""
import math
import paths  # noqa: F401  (sets up sys.path)
import model as M
from functools import lru_cache
STD = M.spx_metrics(63, 7, 14, 12, 16)   # SLH-DSA-SHA2-128s baseline
SWN = M.SWN
def _logpois(lam, r):
    return -lam + r*math.log(lam) - math.lgamma(r+1)
def _sum(h, q_log2, pf):
    lam = 2.0**(q_log2-h); s=0.0
    lo=max(1,int(lam-30*math.sqrt(lam+1)-30)); hi=int(lam+30*math.sqrt(lam+1)+60)
    for r in range(lo,hi):
        lp=_logpois(lam,r); v=pf(r)
        if v>0: s+=math.exp(lp+math.log(v))
    return s
@lru_cache(None)
def sec_fors(h,a,k,q):
    t=2.0**a
    p=_sum(h,q,lambda r: (-math.expm1(r*math.log1p(-1/t)))**k)
    return min(128.0, -math.log2(p)) if p>0 else 128.0
@lru_cache(None)
def sec_pors(h,a,k,q):
    t=k*2**a
    def pf(r):
        m=min(r*k,t)
        if m<k: return 0.0
        return math.exp(math.lgamma(m+1)-math.lgamma(m-k+1)-math.lgamma(t+1)+math.lgamma(t-k+1))
    p=_sum(h,q,pf)
    return min(128.0, -math.log2(p)) if p>0 else 128.0
@lru_cache(None)
def mink(fam,h,a,q):
    f = sec_fors if fam=='fors' else sec_pors
    for k in range(2,60):
        if f(h,a,k,q) >= 127.999: return k
    return None
