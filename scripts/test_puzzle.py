#!/usr/bin/env python3
"""
XCHPredict — Test the oracle_payout puzzle on testnet.

Prerequisites:
  - Sage wallet running on testnet11 with TXCH balance
  - rue-cli built at /Users/alphanerd/Dev/rue-lang/target/release/rue
  - clvm_tools_rs installed (cargo install clvm_tools_rs)

This script:
  1. Compiles the oracle_payout.rue puzzle
  2. Generates an oracle keypair
  3. Creates a market (curries the puzzle with parameters)
  4. Locks TXCH into the curried puzzle
  5. Resolves the market (signs outcome)
  6. Spends the puzzle coin (claims payout)
"""

import json
import subprocess
import hashlib
import sys
import os

# Paths
RUE_BIN = "/Users/alphanerd/Dev/rue-lang/target/release/rue"
PUZZLE_PATH = "/Users/alphanerd/Dev/chia-predict/puzzles/oracle_payout.rue"
PROJECT_DIR = "/Users/alphanerd/Dev/chia-predict"

def run(cmd, check=True):
    """Run a shell command and return stdout."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"ERROR: {cmd}")
        print(f"STDERR: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def sage_rpc(method, body=None):
    """Call sage rpc and return parsed JSON."""
    body = body or {}
    result = run(f"sage rpc {method} '{json.dumps(body)}'")
    return json.loads(result)

def compile_puzzle():
    """Compile the Rue puzzle and return hex."""
    hex_output = run(f"{RUE_BIN} build {PUZZLE_PATH} -x")
    hash_output = run(f"{RUE_BIN} build {PUZZLE_PATH} -h")
    clvm_output = run(f"{RUE_BIN} build {PUZZLE_PATH}")
    return {
        "hex": hex_output,
        "hash": hash_output,
        "clvm": clvm_output,
    }

def main():
    print("=" * 60)
    print("XCHPredict — Oracle Payout Puzzle Test")
    print("=" * 60)

    # Step 1: Compile puzzle
    print("\n[1/6] Compiling oracle_payout.rue...")
    puzzle = compile_puzzle()
    print(f"  CLVM: {puzzle['clvm'][:80]}...")
    print(f"  Hex:  {puzzle['hex'][:80]}...")
    print(f"  Hash: {puzzle['hash']}")

    # Step 2: Check network
    print("\n[2/6] Checking network...")
    network = sage_rpc("get_network")
    net_name = network.get("network", {}).get("name", "unknown")
    print(f"  Network: {net_name}")
    if net_name != "testnet11":
        print("  ⚠️  WARNING: Not on testnet11! Switch with:")
        print("     sage rpc set_network '{\"network_id\": \"testnet11\"}'")
        print("  Then restart Sage and re-run this script.")
        sys.exit(1)

    # Step 3: Check sync status
    print("\n[3/6] Checking sync status...")
    sync = sage_rpc("get_sync_status")
    print(f"  Synced: {sync}")

    # Step 4: Get balance
    print("\n[4/6] Checking TXCH balance...")
    coins = sage_rpc("get_xch_coins")
    total = sum(c.get("amount", 0) for c in coins.get("coins", []))
    print(f"  Balance: {total} mojos ({total / 1e12:.6f} TXCH)")
    if total < 100000:
        print("  ⚠️  Need TXCH! Get from faucet: https://testnet11-faucet.chia.net/")
        sys.exit(1)

    # Step 5: Generate test market parameters
    print("\n[5/6] Generating market parameters...")
    
    # For testing, we use the wallet's own key as oracle
    keys = sage_rpc("get_keys")
    if not keys.get("keys"):
        print("  ERROR: No keys found")
        sys.exit(1)
    
    oracle_pubkey = keys["keys"][0]["public_key"]
    print(f"  Oracle pubkey: {oracle_pubkey[:20]}...")

    # Generate market ID
    market_id = hashlib.sha256(b"test_market_001").hexdigest()
    print(f"  Market ID: {market_id[:20]}...")

    # Generate fake YES/NO asset IDs (for testing)
    yes_asset_id = hashlib.sha256(b"yes_token").hexdigest()
    no_asset_id = hashlib.sha256(b"no_token").hexdigest()
    print(f"  YES asset: {yes_asset_id[:20]}...")
    print(f"  NO asset:  {no_asset_id[:20]}...")

    # Save test parameters
    params = {
        "oracle_pubkey": oracle_pubkey,
        "market_id": market_id,
        "yes_asset_id": yes_asset_id,
        "no_asset_id": no_asset_id,
        "puzzle_hash": puzzle["hash"],
        "puzzle_hex": puzzle["hex"],
    }
    
    params_path = os.path.join(PROJECT_DIR, "tests", "test_params.json")
    with open(params_path, "w") as f:
        json.dump(params, f, indent=2)
    print(f"\n  Saved to: {params_path}")

    print("\n[6/6] Next steps:")
    print("  To create a coin locked with this puzzle, we need to:")
    print("  a) Curry the puzzle with oracle_pubkey, yes/no asset IDs, market_id")
    print("  b) Calculate the curried puzzle hash")
    print("  c) Send TXCH to that puzzle hash")
    print("  d) Then spend it by providing outcome + signature")
    print()
    print("  This requires clvm_tools_rs for currying. Run:")
    print("    cargo install clvm_tools_rs")
    print()
    print("  Full E2E test coming in test_e2e.py")

    print("\n" + "=" * 60)
    print("Puzzle compilation: ✅ PASS")
    print("=" * 60)

if __name__ == "__main__":
    main()
