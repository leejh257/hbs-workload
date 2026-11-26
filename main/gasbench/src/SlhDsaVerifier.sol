// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title Generic SLH-DSA (SPHINCS+) verifier for n = 16 bytes
/// @notice Follows FIPS 205 (SHA2 instantiation, category 1) with configurable (h, d, a, k, lg w).
///         With keccak = true, every tweakable hash and H_msg uses KECCAK256 instead of the
///         SHA-256 precompile (non-standard variant, used only to measure gas).
///         The verifier implements slh_verify_internal: the message M is verified as given.
contract SlhDsaVerifier {
    uint256 internal constant N = 16;
    uint256 internal constant TOP128 = 0xffffffffffffffffffffffffffffffff00000000000000000000000000000000;

    // ADRS types (FIPS 205, Table 1)
    uint256 internal constant WOTS_HASH = 0;
    uint256 internal constant WOTS_PK = 1;
    uint256 internal constant TREE = 2;
    uint256 internal constant FORS_TREE = 3;
    uint256 internal constant FORS_ROOTS = 4;

    uint256 public immutable H;
    uint256 public immutable D;
    uint256 public immutable HP;
    uint256 public immutable A;
    uint256 public immutable K;
    uint256 public immutable LGW;
    uint256 public immutable W;
    uint256 public immutable LEN1;
    uint256 public immutable LEN2;
    uint256 public immutable LEN;
    uint256 public immutable M;
    uint256 public immutable SIGLEN;
    bool public immutable KECCAK;

    constructor(uint256 h, uint256 d, uint256 a, uint256 k, uint256 lgw, bool keccak) {
        require(h % d == 0, "h/d");
        H = h;
        D = d;
        HP = h / d;
        A = a;
        K = k;
        LGW = lgw;
        W = 1 << lgw;
        uint256 len1 = (8 * N + lgw - 1) / lgw;
        uint256 len2 = _log2(len1 * ((1 << lgw) - 1)) / lgw + 1;
        LEN1 = len1;
        LEN2 = len2;
        LEN = len1 + len2;
        M = (k * a + 7) / 8 + (h - h / d + 7) / 8 + (h / d + 7) / 8;
        SIGLEN = (1 + k * (a + 1) + h + d * (len1 + len2)) * N;
        KECCAK = keccak;
    }

    function _log2(uint256 x) internal pure returns (uint256 r) {
        while (x > 1) {
            x >>= 1;
            r++;
        }
    }

    // ------------------------------------------------------------------
    // Hash buffer layout (memory, starting at `buf`):
    //   SHA-256 mode:  [0,16) PK.seed | [16,64) zeros | [64,86) ADRSc | [86, ...) message
    //   Keccak mode:   [48,64) PK.seed | [64,86) ADRSc | [86, ...) message   (hash starts at 48)
    // ADRSc (22 bytes) = layer(1) | tree(8) | type(1) | w1(4) | w2(4) | w3(4)
    // ------------------------------------------------------------------

    function _adrs(uint256 layer, uint256 tree, uint256 typ, uint256 w1, uint256 w2, uint256 w3)
        internal
        pure
        returns (uint256)
    {
        return (layer << 168) | (tree << 104) | (typ << 96) | (w1 << 64) | (w2 << 32) | w3;
    }

    /// @dev Tweakable hash over the `mlen` message bytes already placed at buf+86.
    function _thash(uint256 buf, uint256 adrs, uint256 mlen) internal view returns (uint256 out) {
        bool kec = KECCAK;
        assembly {
            // write ADRSc: 22 bytes at buf+64 (clobbers buf+86..96, so message must be written after)
            // caller writes message after calling _setAdrs; here ADRS is already in place
            switch kec
            case 0 {
                if iszero(staticcall(gas(), 0x02, buf, add(86, mlen), 0x00, 0x20)) { revert(0, 0) }
                out := and(mload(0x00), TOP128)
            }
            default { out := and(keccak256(add(buf, 48), add(38, mlen)), TOP128) }
        }
    }

    function _setAdrs(uint256 buf, uint256 adrs) internal pure {
        assembly {
            // keep the 10 bytes after ADRSc intact is not needed: message is written afterwards
            mstore(add(buf, 64), shl(80, adrs))
        }
    }

    /// @dev F or H: one or two 16-byte inputs.
    function _f(uint256 buf, uint256 adrs, uint256 x) internal view returns (uint256) {
        _setAdrs(buf, adrs);
        assembly {
            mstore(add(buf, 86), x)
        }
        return _thash(buf, adrs, 16);
    }

    function _h(uint256 buf, uint256 adrs, uint256 l, uint256 r) internal view returns (uint256) {
        _setAdrs(buf, adrs);
        assembly {
            mstore(add(buf, 86), l)
            mstore(add(buf, 102), r)
        }
        return _thash(buf, adrs, 32);
    }

    /// @dev T_l over `cnt` 16-byte values stored contiguously at `src`.
    function _t(uint256 buf, uint256 adrs, uint256 src, uint256 cnt) internal view returns (uint256) {
        _setAdrs(buf, adrs);
        assembly {
            mcopy(add(buf, 86), src, mul(cnt, 16))
        }
        return _thash(buf, adrs, cnt * 16);
    }

    function _sig16(bytes calldata sig, uint256 off) internal pure returns (uint256 v) {
        assembly {
            v := and(calldataload(add(sig.offset, off)), TOP128)
        }
    }

    // ------------------------------------------------------------------
    // H_msg (SHA2, category 1): MGF1-SHA-256(R || PK.seed || SHA-256(R || PK.seed || PK.root || M), m)
    // ------------------------------------------------------------------
    function _hmsg(uint256 r, uint256 seed, uint256 root, bytes calldata msg) internal view returns (uint256 dg) {
        bool kec = KECCAK;
        uint256 m = M;
        assembly {
            let p := mload(0x40)
            mstore(p, r)
            mstore(add(p, 16), seed)
            mstore(add(p, 32), root)
            calldatacopy(add(p, 48), msg.offset, msg.length)
            let inner
            switch kec
            case 0 {
                if iszero(staticcall(gas(), 0x02, p, add(48, msg.length), 0x00, 0x20)) { revert(0, 0) }
                inner := mload(0x00)
            }
            default { inner := keccak256(p, add(48, msg.length)) }
            // seed for MGF1: R || PK.seed || inner (64 bytes), then 4-byte counter
            mstore(p, r)
            mstore(add(p, 16), seed)
            mstore(add(p, 32), inner)
            dg := add(p, 96)
            let blocks := div(add(m, 31), 32)
            for { let c := 0 } lt(c, blocks) { c := add(c, 1) } {
                mstore(add(p, 64), shl(224, c))
                switch kec
                case 0 {
                    if iszero(staticcall(gas(), 0x02, p, 68, add(dg, mul(c, 32)), 0x20)) { revert(0, 0) }
                }
                default { mstore(add(dg, mul(c, 32)), keccak256(p, 68)) }
            }
            mstore(0x40, add(dg, add(mul(blocks, 32), 32)))
        }
    }

    function _bits(uint256 dg, uint256 bitpos, uint256 nbits) internal pure returns (uint256 v) {
        assembly {
            let word := mload(add(dg, shr(3, bitpos)))
            v := and(shr(sub(256, add(and(bitpos, 7), nbits)), word), sub(shl(nbits, 1), 1))
        }
    }

    // ------------------------------------------------------------------
    // verify
    // ------------------------------------------------------------------
    struct Ctx {
        uint256 buf;
        uint256 tmp; // scratch for T inputs
        uint256 treeIdx;
        uint256 leafIdx;
    }

    function verify(bytes calldata msg, bytes calldata sig, bytes32 pkSeed, bytes32 pkRoot)
        external
        view
        returns (bool)
    {
        if (sig.length != SIGLEN) return false;
        uint256 seed = uint256(pkSeed) & TOP128;
        uint256 root = uint256(pkRoot) & TOP128;

        Ctx memory c;
        uint256 maxT = LEN > K ? LEN : K;
        assembly {
            let p := mload(0x40)
            // hash buffer: 86 + 16*maxT + 32
            let b := p
            mstore(b, 0)
            mstore(add(b, 32), 0)
            mstore(add(b, 64), 0)
            p := add(p, add(118, mul(16, maxT)))
            let t := p
            p := add(p, add(32, mul(16, maxT)))
            mstore(0x40, p)
            mstore(c, b)
            mstore(add(c, 32), t)
        }
        // place PK.seed
        {
            uint256 b = c.buf;
            bool kec = KECCAK;
            assembly {
                switch kec
                case 0 { mstore(b, seed) mstore(add(b, 16), 0) mstore(add(b, 32), 0) }
                default { mstore(add(b, 48), seed) }
            }
        }

        uint256 r = _sig16(sig, 0);
        uint256 dg = _hmsg(r, seed, root, msg);

        uint256 mdBytes = (K * A + 7) / 8;
        uint256 treeBits = H - HP;
        uint256 treeBytes = (treeBits + 7) / 8;
        uint256 leafBytes = (HP + 7) / 8;
        {
            uint256 ti = _bits(dg, mdBytes * 8, treeBytes * 8);
            c.treeIdx = treeBits == 0 ? 0 : ti & ((1 << treeBits) - 1);
            uint256 li = _bits(dg, (mdBytes + treeBytes) * 8, leafBytes * 8);
            c.leafIdx = li & ((1 << HP) - 1);
        }

        uint256 node = _forsPk(c, sig, dg);
        node = _hypertree(c, sig, node);
        return node == root;
    }

    function _forsPk(Ctx memory c, bytes calldata sig, uint256 dg) internal view returns (uint256) {
        uint256 off = N; // after R
        uint256 a = A;
        for (uint256 i = 0; i < K; i++) {
            uint256 idx = _bits(dg, i * a, a);
            uint256 tIndex = (i << a) + idx;
            uint256 node =
                _f(c.buf, _adrs(0, c.treeIdx, FORS_TREE, c.leafIdx, 0, tIndex), _sig16(sig, off));
            off += N;
            for (uint256 j = 0; j < a; j++) {
                uint256 auth = _sig16(sig, off);
                off += N;
                if ((idx >> j) & 1 == 0) {
                    tIndex = tIndex >> 1;
                    node = _h(c.buf, _adrs(0, c.treeIdx, FORS_TREE, c.leafIdx, j + 1, tIndex), node, auth);
                } else {
                    tIndex = (tIndex - 1) >> 1;
                    node = _h(c.buf, _adrs(0, c.treeIdx, FORS_TREE, c.leafIdx, j + 1, tIndex), auth, node);
                }
            }
            uint256 t = c.tmp + i * 16;
            assembly {
                mstore(t, node)
            }
        }
        return _t(c.buf, _adrs(0, c.treeIdx, FORS_ROOTS, c.leafIdx, 0, 0), c.tmp, K);
    }

    function _hypertree(Ctx memory c, bytes calldata sig, uint256 node) internal view returns (uint256) {
        uint256 off = (1 + K * (A + 1)) * N;
        uint256 treeIdx = c.treeIdx;
        uint256 leafIdx = c.leafIdx;
        for (uint256 layer = 0; layer < D; layer++) {
            node = _wotsPk(c, sig, off, node, layer, treeIdx, leafIdx);
            off += LEN * N;
            uint256 tIndex = leafIdx;
            for (uint256 k = 0; k < HP; k++) {
                uint256 auth = _sig16(sig, off);
                off += N;
                if ((leafIdx >> k) & 1 == 0) {
                    tIndex = tIndex >> 1;
                    node = _h(c.buf, _adrs(layer, treeIdx, TREE, 0, k + 1, tIndex), node, auth);
                } else {
                    tIndex = (tIndex - 1) >> 1;
                    node = _h(c.buf, _adrs(layer, treeIdx, TREE, 0, k + 1, tIndex), auth, node);
                }
            }
            leafIdx = treeIdx & ((1 << HP) - 1);
            treeIdx = treeIdx >> HP;
        }
        return node;
    }

    function _wotsPk(
        Ctx memory c,
        bytes calldata sig,
        uint256 off,
        uint256 msgNode,
        uint256 layer,
        uint256 treeIdx,
        uint256 leafIdx
    ) internal view returns (uint256) {
        uint256 lgw = LGW;
        uint256 wm1 = W - 1;
        uint256 len1 = LEN1;
        uint256 csum = 0;
        // message digits
        for (uint256 i = 0; i < len1; i++) {
            uint256 digit = (msgNode >> (256 - (i + 1) * lgw)) & wm1;
            csum += wm1 - digit;
            uint256 v = _chain(c, _sig16(sig, off + i * N), digit, wm1 - digit, layer, treeIdx, leafIdx, i);
            uint256 t = c.tmp + i * 16;
            assembly {
                mstore(t, v)
            }
        }
        // checksum digits
        uint256 len2 = LEN2;
        uint256 l2bits = len2 * lgw;
        uint256 lbytes = (l2bits + 7) / 8;
        csum = csum << ((8 - (l2bits % 8)) % 8);
        for (uint256 i = 0; i < len2; i++) {
            uint256 digit = (csum >> (lbytes * 8 - (i + 1) * lgw)) & wm1;
            uint256 v =
                _chain(c, _sig16(sig, off + (len1 + i) * N), digit, wm1 - digit, layer, treeIdx, leafIdx, len1 + i);
            uint256 t = c.tmp + (len1 + i) * 16;
            assembly {
                mstore(t, v)
            }
        }
        return _t(c.buf, _adrs(layer, treeIdx, WOTS_PK, leafIdx, 0, 0), c.tmp, LEN);
    }

    function _chain(
        Ctx memory c,
        uint256 x,
        uint256 start,
        uint256 steps,
        uint256 layer,
        uint256 treeIdx,
        uint256 leafIdx,
        uint256 chainIdx
    ) internal view returns (uint256) {
        uint256 b = c.buf;
        for (uint256 j = start; j < start + steps; j++) {
            x = _f(b, _adrs(layer, treeIdx, WOTS_HASH, leafIdx, chainIdx, j), x);
        }
        return x;
    }
}
