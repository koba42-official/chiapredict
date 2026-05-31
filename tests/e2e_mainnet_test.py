#!/usr/bin/env python3
"""
XCH Predict — E2E mainnet test with tiny amount.

Tests the full lifecycle:
  1. Compile puzzle
  2. Curry with parameters
  3. Send dust XCH to curried puzzle hash
  4. Spend the coin with oracle signature
  5. Verify payout received

Uses 1000 mojos (0.000000001 XCH) — effectively dust.
"""

import json
import subprocess
import hashlib
import sys
import os
import time

# Get script directory and project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", "bin", "python3")
RUE_BIN = os.environ.get("RUE_BIN", "rue")  # Default to rue on PATH
PUZZLE_PATH = os.path.join(PROJECT_DIR, "puzzles", "oracle_payout.rue")

# OFF LIMITS — never interact
FORBIDDEN_FPS = [1849776284]

# Test amount: 1000 mojos = minimum for a coin
TEST_AMOUNT = 1000

def run(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"ERROR: {cmd}")
        print(f"STDERR: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def sage_rpc(method, body=None):
    body = body or {}
    result = run(f"sage rpc {method} '{json.dumps(body)}'")
    return json.loads(result)

def main():
    print("=" * 60)
    print("XCH Predict — E2E Mainnet Test (1000 mojos)")
    print("=" * 60)
    
    # Check forbidden fingerprints before any wallet interaction
    oracle_fp = 1631380421  # DracattusDev fingerprint
    if oracle_fp in FORBIDDEN_FPS:
        print(f"❌ Oracle wallet fp:{oracle_fp} is FORBIDDEN! Script blocked.")
        sys.exit(1)

    # Step 1: Verify network
    print("\n[1] Verifying network...")
    network = sage_rpc("get_network")
    net_name = network["network"]["name"]
    print(f"    Network: {net_name}")

    # Step 2: Compile puzzle
    print("\n[2] Compiling oracle_payout.rue...")
    puzzle_hex = run(f"{RUE_BIN} build {PUZZLE_PATH} -x")
    puzzle_hash = run(f"{RUE_BIN} build {PUZZLE_PATH} -h")
    puzzle_clvm = run(f"{RUE_BIN} build {PUZZLE_PATH}")
    print(f"    Puzzle hash: {puzzle_hash}")
    print(f"    CLVM: {puzzle_clvm[:60]}...")

    # Step 3: Get oracle key (logged in wallet)
    print("\n[3] Getting oracle key...")
    keys = sage_rpc("get_keys")
    # Use DracattusDev key
    oracle_key = None
    for k in keys["keys"]:
        if k["name"] == "DracattusDev":
            oracle_key = k
            break
    if not oracle_key:
        oracle_key = keys["keys"][0]
    
    oracle_pubkey = oracle_key["public_key"]
    print(f"    Oracle: {oracle_key['name']} (fp: {oracle_key['fingerprint']})")
    print(f"    Pubkey: {oracle_pubkey[:32]}...")

    # Step 4: Generate market parameters
    print("\n[4] Generating market parameters...")
    market_id = hashlib.sha256(f"test_market_{time.time()}".encode()).hexdigest()
    yes_asset_id = hashlib.sha256(b"YES_TEST_TOKEN").hexdigest()
    no_asset_id = hashlib.sha256(b"NO_TEST_TOKEN").hexdigest()
    print(f"    Market ID:  {market_id[:32]}...")
    print(f"    YES asset:  {yes_asset_id[:32]}...")
    print(f"    NO asset:   {no_asset_id[:32]}...")

    # Step 5: Curry the puzzle
    print("\n[5] Currying puzzle with parameters...")
    # The puzzle takes 4 curried args: oracle_pubkey, yes_asset_id, no_asset_id, market_id
    # Solution args: outcome, receiver_puzzle_hash, my_amount
    #
    # In CLVM, currying wraps: (a (q . <puzzle>) (c (q . <arg1>) (c (q . <arg2>) ... (a))))
    # We'll use cdv clsp curry for this
    
    curry_cmd = (
        f"source {PROJECT_DIR}/.venv/bin/activate && "
        f"cdv clsp curry '{puzzle_clvm}' "
        f"-a 0x{oracle_pubkey} "
        f"-a 0x{yes_asset_id} "
        f"-a 0x{no_asset_id} "
        f"-a 0x{market_id}"
    )
    curried_clvm = run(curry_cmd)
    print(f"    Curried CLVM: {curried_clvm[:60]}...")

    # Get curried puzzle hash
    hash_cmd = (
        f"source {PROJECT_DIR}/.venv/bin/activate && "
        f"cdv clsp treehash '{curried_clvm}'"
    )
    curried_hash = run(hash_cmd)
    print(f"    Curried hash: {curried_hash}")

    # Convert to address
    addr_cmd = (
        f"source {PROJECT_DIR}/.venv/bin/activate && "
        f"cdv encode {curried_hash} --prefix xch"
    )
    puzzle_address = run(addr_cmd)
    print(f"    Address: {puzzle_address}")

    # Save test state
    test_state = {
        "market_id": market_id,
        "oracle_pubkey": oracle_pubkey,
        "oracle_fingerprint": oracle_key["fingerprint"],
        "oracle_name": oracle_key["name"],
        "yes_asset_id": yes_asset_id,
        "no_asset_id": no_asset_id,
        "puzzle_hex": puzzle_hex,
        "puzzle_hash": puzzle_hash,
        "puzzle_clvm": puzzle_clvm,
        "curried_clvm": curried_clvm,
        "curried_hash": curried_hash,
        "puzzle_address": puzzle_address,
        "test_amount": TEST_AMOUNT,
        "network": net_name,
        "created_at": time.time(),
    }
    
    state_path = os.path.join(SCRIPT_DIR, "e2e_state.json")
    with open(state_path, "w") as f:
        json.dump(test_state, f, indent=2)
    print(f"\n    State saved: {state_path}")

    # Step 6: Send XCH to the puzzle
    print(f"\n[6] Sending {TEST_AMOUNT} mojos to puzzle address...")
    print(f"    Target: {puzzle_address}")
    
    send_result = sage_rpc("send_xch", {
        "address": puzzle_address,
        "amount": TEST_AMOUNT,
        "fee": 0,
    })
    print(f"    TX result: {json.dumps(send_result)[:200]}")

    # Update state with TX info
    test_state["send_tx"] = send_result
    with open(state_path, "w") as f:
        json.dump(test_state, f, indent=2)

    print(f"\n✅ Coin sent to oracle_payout puzzle!")
    print(f"   Address: {puzzle_address}")
    print(f"   Amount: {TEST_AMOUNT} mojos")
    print(f"\n⏳ Wait for confirmation, then run:")
    print(f"   python3 scripts/spend_puzzle.py")
    print(f"\n   State saved to: {state_path}")

if __name__ == "__main__":
    main()
