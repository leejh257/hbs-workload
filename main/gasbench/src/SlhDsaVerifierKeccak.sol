// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title Gas-optimized generic SLH-DSA verifier, n = 16 bytes, KECCAK256 variant (non-standard)
/// @notice FIPS 205 algorithm (slh_verify_internal) with configurable (h, d, a, k, lg w).
///         Hash buffer at fixed memory 0x400: PK.seed | zero pad | ADRSc (22 B) at 0x440 | message at 0x456.
///         Every SHA-256 call is replaced by KECCAK256 over PK.seed | ADRSc | message (no padding block). Not FIPS 205.
contract SlhDsaVerifierKeccak {
    uint256 public immutable H;
    uint256 public immutable D;
    uint256 public immutable HP;
    uint256 public immutable A;
    uint256 public immutable K;
    uint256 public immutable LGW;
    uint256 public immutable LEN1;
    uint256 public immutable LEN2;
    uint256 public immutable M;
    uint256 public immutable SIGLEN;

    constructor(uint256 h, uint256 d, uint256 a, uint256 k, uint256 lgw) {
        require(h % d == 0 && lgw >= 1 && lgw <= 8, "params");
        uint256 len1 = (128 + lgw - 1) / lgw;
        uint256 x = len1 * ((1 << lgw) - 1);
        uint256 lg;
        while (x > 1) { x >>= 1; lg++; }
        uint256 len2 = lg / lgw + 1;
        require(len1 + len2 <= 68 || lgw >= 2, "len");
        require(k <= 64 && a <= 24 && h - h / d <= 64, "bounds");
        H = h; D = d; HP = h / d; A = a; K = k; LGW = lgw; LEN1 = len1; LEN2 = len2;
        M = (k * a + 7) / 8 + (h - h / d + 7) / 8 + (h / d + 7) / 8;
        SIGLEN = (1 + k * (a + 1) + h + d * (len1 + len2)) * 16;
    }

    function verify(bytes calldata msg, bytes calldata sig, bytes32 pkSeed, bytes32 pkRoot) external view returns (bool ok) {
        if (sig.length != SIGLEN) return false;
        uint256 p_hp = HP;
        uint256 p_a = A;
        uint256 p_k = K;
        uint256 p_lgw = LGW;
        uint256 p_len1 = LEN1;
        uint256 p_len2 = LEN2;
        uint256 p_h = H;
        uint256 p_d = D;
        uint256 p_m = M;
        assembly {
            function th(mlen) -> out {
                out := and(keccak256(0x430, add(38, mlen)), not(0xffffffffffffffffffffffffffffffff))
            }
            function bits(pos, nb) -> v {
                v := and(shr(sub(256, add(and(pos, 7), nb)), mload(add(0xe60, shr(3, pos)))), sub(shl(nb, 1), 1))
            }
            function chain(x, base, j, end) -> r {
                for {} lt(j, end) { j := add(j, 1) } {
                    mstore(0x440, shl(80, or(base, j)))
                    mstore(0x456, x)
                    x := and(keccak256(0x430, 54), not(0xffffffffffffffffffffffffffffffff))
                }
                r := x
            }
            function auth(off, node, base, idx, height) -> out {
                let ti := idx
                for { let j := 0 } lt(j, height) { j := add(j, 1) } {
                    let bit := and(shr(j, idx), 1)
                    ti := shr(1, sub(ti, bit))
                    mstore(0x440, shl(80, or(or(base, shl(32, add(j, 1))), ti)))
                    switch bit
                    case 0 { mstore(0x456, node) mstore(0x466, calldataload(off)) }
                    default { mstore(0x456, calldataload(off)) mstore(0x466, node) }
                    off := add(off, 16)
                    node := th(32)
                }
                out := node
            }
            function tl(cnt, adrs) -> out {
                mstore(0x440, shl(80, adrs))
                mcopy(0x456, 0x900, shl(4, cnt))
                out := th(shl(4, cnt))
            }
            function wots(off, node, hi, lgw, len1, len2) -> pk {
                let wm1 := sub(shl(lgw, 1), 1)
                let csum := 0
                for { let i := 0 } lt(i, len1) { i := add(i, 1) } {
                    let dgt := and(shr(sub(256, mul(add(i, 1), lgw)), node), wm1)
                    csum := add(csum, sub(wm1, dgt))
                    mstore(add(0x900, shl(4, i)), chain(calldataload(add(off, shl(4, i))), or(hi, shl(32, i)), dgt, wm1))
                }
                let l2b := mul(len2, lgw)
                csum := shl(add(mod(sub(8, mod(l2b, 8)), 8), sub(256, shl(3, shr(3, add(l2b, 7))))), csum)
                for { let i := 0 } lt(i, len2) { i := add(i, 1) } {
                    let ci := add(len1, i)
                    let dgt := and(shr(sub(256, mul(add(i, 1), lgw)), csum), wm1)
                    mstore(add(0x900, shl(4, ci)), chain(calldataload(add(off, shl(4, ci))), or(hi, shl(32, ci)), dgt, wm1))
                }
                pk := tl(add(len1, len2), or(hi, shl(96, 1)))
            }

            let TOP := not(0xffffffffffffffffffffffffffffffff)
            let seed := and(pkSeed, TOP)
            let root := and(pkRoot, TOP)
            // hash buffer
            mstore(0x400, 0) mstore(0x420, 0) mstore(0x440, 0)
            mstore(0x430, seed)
            // H_msg: area at 0xe00 (R | seed | root | M), MGF1 output at 0xe60
            {
                let r := and(calldataload(sig.offset), TOP)
                mstore(0xe00, r) mstore(0xe10, seed) mstore(0xe20, root)
                calldatacopy(0xe30, msg.offset, msg.length)
                let inner := keccak256(0xe00, add(48, msg.length))
                mstore(0xe00, r) mstore(0xe10, seed) mstore(0xe20, inner)
                for { let c := 0 } lt(c, shr(5, add(p_m, 31))) { c := add(c, 1) } {
                    mstore(0xe40, shl(224, c))
                    mstore(add(0xe60, shl(5, c)), keccak256(0xe00, 68))
                }
            }
            let tree
            let leaf
            {
                let mdB := shr(3, add(mul(p_k, p_a), 7))
                let tB := shr(3, add(sub(p_h, p_hp), 7))
                tree := and(bits(shl(3, mdB), shl(3, tB)), sub(shl(sub(p_h, p_hp), 1), 1))
                leaf := and(bits(shl(3, add(mdB, tB)), shl(3, shr(3, add(p_hp, 7)))), sub(shl(p_hp, 1), 1))
            }
            // FORS
            let off := add(sig.offset, 16)
            {
                let base := or(or(shl(104, tree), shl(96, 3)), shl(64, leaf))
                for { let i := 0 } lt(i, p_k) { i := add(i, 1) } {
                    let ti := add(shl(p_a, i), bits(mul(i, p_a), p_a))
                    mstore(0x440, shl(80, or(base, ti)))
                    mstore(0x456, calldataload(off))
                    mstore(add(0x900, shl(4, i)), auth(add(off, 16), th(16), base, ti, p_a))
                    off := add(off, shl(4, add(p_a, 1)))
                }
            }
            let node := tl(p_k, or(or(shl(104, tree), shl(96, 4)), shl(64, leaf)))
            // hypertree
            for { let layer := 0 } lt(layer, p_d) { layer := add(layer, 1) } {
                node := wots(off, node, or(or(shl(168, layer), shl(104, tree)), shl(64, leaf)), p_lgw, p_len1, p_len2)
                off := add(off, shl(4, add(p_len1, p_len2)))
                node := auth(off, node, or(or(shl(168, layer), shl(104, tree)), shl(96, 2)), leaf, p_hp)
                off := add(off, shl(4, p_hp))
                leaf := and(tree, sub(shl(p_hp, 1), 1))
                tree := shr(p_hp, tree)
            }
            ok := eq(node, root)
        }
    }
}
