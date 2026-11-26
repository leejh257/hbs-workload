"""Send real verification transactions to a local Prague chain (anvil) and record receipt gas."""
import json, subprocess, os, sys, csv
RPC = "http://127.0.0.1:8545"
PK = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
ENV = dict(os.environ, PATH=os.path.expanduser("~/.foundry/bin") + ":" + os.environ["PATH"])

def sh(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True, env=ENV).stdout.strip()

def deploy(contract, args):
    art = json.load(open(f"out/{contract}.sol/{contract}.json"))
    code = art["bytecode"]["object"]
    enc = sh("cast", "abi-encode", "constructor(uint256,uint256,uint256,uint256,uint256)", *map(str, args))
    out = sh("cast", "send", "--rpc-url", RPC, "--private-key", PK, "--json", "--create", code + enc[2:])
    return json.loads(out)["contractAddress"]

def tokens(data):
    b = bytes.fromhex(data[2:])
    z = b.count(0)
    return z + 4 * (len(b) - z), len(b)

rows = []
for name in sys.argv[1:]:
    v = json.load(open(f"vectors/{name}.json"))
    args = (v["h"], v["d"], v["a"], v["k"], v["lgw"])
    for contract in ("SlhDsaVerifierSha", "SlhDsaVerifierKeccak"):
        addr = deploy(contract, args)
        for i, (m, s) in enumerate(zip(v["msgs"], v["sigs"])):
            data = sh("cast", "calldata", "verify(bytes,bytes,bytes32,bytes32)", "0x" + m, "0x" + s,
                      "0x" + v["pk_seed"] + "00" * 16, "0x" + v["pk_root"] + "00" * 16)
            ok = sh("cast", "call", "--rpc-url", RPC, addr, data)
            rc = json.loads(sh("cast", "send", "--rpc-url", RPC, "--private-key", PK, "--json", addr, data))
            gas = int(rc["gasUsed"], 16)
            tok, nbytes = tokens(data)
            std_exec = gas - 21000 - 4 * tok  # valid when the standard cost exceeds the floor
            floor = 21000 + 10 * tok
            rows.append(dict(set=name, impl=contract, i=i, valid=int(ok[-1] == "1"), calldata_bytes=nbytes,
                             tokens=tok, gas_used=gas, floor=floor, floor_binds=int(gas == floor),
                             exec_gas=std_exec, thash_calls=v["verify_thash_calls"][i]))
        print(name, contract, "done", flush=True)
os.makedirs("results", exist_ok=True)
with open("results/onchain.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
