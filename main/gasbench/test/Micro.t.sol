// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract Bench {
    // n F-style calls: 102-byte input (64-byte seed block + 22-byte ADRS + 16-byte value)
    function shaF(uint256 n) external view returns (uint256 x) {
        assembly {
            let buf := mload(0x40)
            for { let j := 0 } lt(j, n) { j := add(j, 1) } {
                mstore(add(buf, 64), shl(80, j))
                mstore(add(buf, 86), x)
                if iszero(staticcall(gas(), 0x02, buf, 102, 0x00, 0x20)) { revert(0, 0) }
                x := and(mload(0x00), 0xffffffffffffffffffffffffffffffff00000000000000000000000000000000)
            }
        }
    }
    function kecF(uint256 n) external pure returns (uint256 x) {
        assembly {
            let buf := mload(0x40)
            for { let j := 0 } lt(j, n) { j := add(j, 1) } {
                mstore(add(buf, 64), shl(80, j))
                mstore(add(buf, 86), x)
                x := and(keccak256(add(buf, 48), 54), 0xffffffffffffffffffffffffffffffff00000000000000000000000000000000)
            }
        }
    }
    function empty(uint256 n) external pure returns (uint256 x) {
        assembly {
            let buf := mload(0x40)
            for { let j := 0 } lt(j, n) { j := add(j, 1) } {
                mstore(add(buf, 64), shl(80, j))
                mstore(add(buf, 86), x)
                x := add(x, 1)
            }
        }
    }
}

contract MicroTest {
    function _g(function (uint256) external view returns (uint256) f, uint256 n) internal view returns (uint256) {
        uint256 g0 = gasleft(); f(n); return g0 - gasleft();
    }
    event Log(string, uint256);
    function test_micro() public {
        Bench b = new Bench();
        b.shaF(1); // warm the account
        uint256 s = (_g(b.shaF, 1001) - _g(b.shaF, 1)) / 1000;
        uint256 k = (_g(b.kecF, 1001) - _g(b.kecF, 1)) / 1000;
        uint256 e = (_g(b.empty, 1001) - _g(b.empty, 1)) / 1000;
        emit Log("sha256 per F call", s);
        emit Log("keccak per F call", k);
        emit Log("loop overhead only", e);
    }
}
