// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {SlhDsaVerifier} from "../src/SlhDsaVerifier.sol";
import {SlhDsaVerifierSha} from "../src/SlhDsaVerifierSha.sol";
import {SlhDsaVerifierKeccak} from "../src/SlhDsaVerifierKeccak.sol";

interface IV { function verify(bytes calldata, bytes calldata, bytes32, bytes32) external view returns (bool); }

interface Vm {
    function readFile(string calldata) external view returns (string memory);
    function parseJsonUint(string calldata, string calldata) external pure returns (uint256);
    function parseJsonBytes(string calldata, string calldata) external pure returns (bytes memory);
    function parseJsonBytes32(string calldata, string calldata) external pure returns (bytes32);
    function parseJsonUintArray(string calldata, string calldata) external pure returns (uint256[] memory);
    function writeLine(string calldata, string calldata) external;
    function writeFile(string calldata, string calldata) external;
    function toString(uint256) external pure returns (string memory);
    function envOr(string calldata, string calldata) external view returns (string memory);
}

contract GasTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    function _run(string memory name, bool keccak) internal { _run2(name, keccak, false); _run2(name, keccak, true); }

    function _run2(string memory name, bool keccak, bool opt) internal {
        string memory j = vm.readFile(string.concat("vectors/", name, ".json"));
        uint256 h = vm.parseJsonUint(j, ".h"); uint256 d = vm.parseJsonUint(j, ".d"); uint256 a = vm.parseJsonUint(j, ".a");
        uint256 k = vm.parseJsonUint(j, ".k"); uint256 lgw = vm.parseJsonUint(j, ".lgw");
        IV v = !opt ? IV(address(new SlhDsaVerifier(h, d, a, k, lgw, keccak))) : (keccak ? IV(address(new SlhDsaVerifierKeccak(h, d, a, k, lgw))) : IV(address(new SlhDsaVerifierSha(h, d, a, k, lgw))));
        bytes32 seed = bytes32(vm.parseJsonBytes(j, ".pk_seed"));
        bytes32 root = bytes32(vm.parseJsonBytes(j, ".pk_root"));
        uint256[] memory calls = vm.parseJsonUintArray(j, ".verify_thash_calls");
        string memory out = string.concat("results/", name, keccak ? "_keccak" : "_sha256", opt ? "_opt" : "_ref", ".csv");
        vm.writeFile(out, "i,thash_calls,exec_gas,valid\n");
        for (uint256 i = 0; i < calls.length; i++) {
            bytes memory msg = vm.parseJsonBytes(j, string.concat(".msgs[", vm.toString(i), "]"));
            bytes memory sig = vm.parseJsonBytes(j, string.concat(".sigs[", vm.toString(i), "]"));
            uint256 g0 = gasleft();
            bool ok = v.verify(msg, sig, seed, root);
            uint256 used = g0 - gasleft();
            if (!keccak) require(ok, "valid signature rejected");
            if (i == 0 && !keccak) {
                sig[sig.length - 1] ^= 0x01;
                require(!v.verify(msg, sig, seed, root), "forged signature accepted");
            }
            vm.writeLine(out, string.concat(vm.toString(i), ",", vm.toString(calls[i]), ",", vm.toString(used), ",", ok ? "1" : "0"));
        }
    }

    function test_eth_ordinary() public { _run("eth_ordinary", false); _run("eth_ordinary", true); }
    function test_eth_high() public { _run("eth_high", false); _run("eth_high", true); }
    function test_eth_extreme() public { _run("eth_extreme", false); _run("eth_extreme", true); }
    function test_slh_dsa_128f() public { _run("slh_dsa_128f", false); _run("slh_dsa_128f", true); }
    function test_slh_dsa_128s() public { _run("slh_dsa_128s", false); _run("slh_dsa_128s", true); }
}
