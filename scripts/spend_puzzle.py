#!/usr/bin/env python3
"""
XCHPredict — Spend the oracle_payout puzzle coin.

This script:
  1. Finds the coin at the curried puzzle hash
  2. Constructs the solution (outcome=1/YES wins)
  3. Signs with oracle key
  4. Submits the spend to the network
"""

import json
import subprocess
import sys
import os
import time

PROJECT_DIR = "/Users/alphanerd/Dev/chia-predict"
RUE_BIN = "/Users/alphanerd/Dev/rue-lang/target/release/rue"
PUZZLE_PATH = f"{PROJECT_DIR}/puzzles/oracle_payout.rue"
VENV = f"{PROJECT_DIR}/.venv/bin"
STATE_FILE = f"{PROJECT_DIR}/tests/mainnet_test_state.json"

def run(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"ERROR: {cmd}")
        print(f"STDERR: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def sage_rpc(method, body=None):
    body = body or {}
    raw = run(f"sage rpc {method} '{json.dumps(body)}'", check=False)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  sage rpc {method} returned: {raw}")
        return None

def main():
    print("=" * 60)
    print("XCHPredict — Spend Oracle Payout Puzzle")
    print("=" * 60)

    # Load state
    with open(STATE_FILE) as f:
        state = json.load(f)

    market_id = state["market_id"]
    oracle_pk = state["oracle_pubkey"]
    yes_asset_id = state["yes_asset_id"]
    no_asset_id = state["no_asset_id"]
    curried_hash = state["curried_hash"]
    puzzle_address = state["puzzle_address"]
    test_amount = state["test_amount"]

    print(f"\n  Market ID: {market_id[:32]}...")
    print(f"  Oracle:    {state['oracle_name']}")
    print(f"  Address:   {puzzle_address}")
    print(f"  Amount:    {test_amount} mojos")

    # Step 1: Find the coin on-chain via spacescan or sage
    print(f"\n[1] Looking for coin at puzzle hash {curried_hash}...")
    
    # Try to find via spacescan API
    import urllib.request
    url = f"https://api.spacescan.io/coin/search/{puzzle_address}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "XCHPredict/0.1"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        print(f"  Spacescan response: {json.dumps(data)[:200]}...")
    except Exception as e:
        print(f"  Spacescan lookup failed: {e}")
        print(f"  Trying alternative...")

    # Also try spacescan puzzle hash endpoint
    url2 = f"https://api2.spacescan.io/1/xch/coins/address/{puzzle_address}"
    try:
        req = urllib.request.Request(url2, headers={"User-Agent": "XCHPredict/0.1"})
        resp = urllib.request.urlopen(req, timeout=10)
        data2 = json.loads(resp.read())
        print(f"  Spacescan v2: {json.dumps(data2)[:300]}...")
    except Exception as e:
        print(f"  Spacescan v2 failed: {e}")

    # Step 2: Compile the puzzle and curry it
    print(f"\n[2] Preparing puzzle and solution...")
    puzzle_clvm = run(f"{RUE_BIN} build {PUZZLE_PATH}")
    
    # Curry the puzzle
    activate = f"source {PROJECT_DIR}/.venv/bin/activate"
    curried = run(
        f"{activate} && cdv clsp curry '{puzzle_clvm}' "
        f"-a 0x{oracle_pk} -a 0x{yes_asset_id} -a 0x{no_asset_id} -a 0x{market_id}"
    )
    print(f"  Curried puzzle: OK")

    # Step 3: Build solution
    # Solution args: outcome (1=YES), receiver_puzzle_hash, my_amount
    # We'll send back to the DracattusDev wallet
    print(f"\n[3] Building solution...")
    
    # Get a receive address from the wallet
    derivations = sage_rpc("get_derivations", {"hardened": False, "offset": 0, "limit": 1})
    if derivations and "derivations" in derivations:
        recv_addr = derivations["derivations"][0]["address"]
        receiver_ph = run(f"{activate} && cdv decode {recv_addr}")
    else:
        print("  ERROR: Can't get receiver puzzle hash. Is Sage wallet logged in?")
        print("  Try: sage rpc login '{\"fingerprint\": 1631380421}'")
        sys.exit(1)
    
    print(f"  Receiver puzzle hash: {receiver_ph}")
    
    # Solution: (outcome receiver_puzzle_hash my_amount)
    # outcome=1 (YES wins), receiver_ph, 1000 mojos
    outcome = 1
    solution_clvm = f"({outcome} 0x{receiver_ph} {test_amount})"
    print(f"  Solution: {solution_clvm}")

    # Step 4: Build the coin spend
    print(f"\n[4] Building coin spend...")
    
    # We need: parent_coin_id, puzzle_hash, amount to identify the coin
    # Then: puzzle_reveal (curried clvm) + solution
    # Then sign with oracle key and submit
    
    # Convert curried puzzle to hex for the spend
    curried_hex = run(f"{activate} && opc '{curried}'")
    solution_hex = run(f"{activate} && opc '{solution_clvm}'")
    print(f"  Puzzle hex: {curried_hex[:40]}...")
    print(f"  Solution hex: {solution_hex[:40]}...")

    # Save spend data
    spend_data = {
        "curried_clvm": curried,
        "curried_hex": curried_hex,
        "solution_clvm": solution_clvm,
        "solution_hex": solution_hex,
        "outcome": outcome,
        "receiver_puzzle_hash": receiver_ph,
        "oracle_fingerprint": state["oracle_fingerprint"],
    }
    
    spend_path = f"{PROJECT_DIR}/tests/spend_data.json"
    with open(spend_path, "w") as f:
        json.dump(spend_data, f, indent=2)

    print(f"\n  Spend data saved: {spend_path}")
    
    # Step 5: Find the coin and submit
    print(f"\n[5] To complete the spend, we need the coin's parent ID.")
    print(f"    Check: https://spacescan.io/address/{puzzle_address}")
    print(f"    Or wait for Sage to detect it.")
    print(f"\n    Once we have parent_coin_id, the spend bundle can be")
    print(f"    signed with sage rpc sign_coin_spends and submitted")
    print(f"    with sage rpc submit_transaction.")

    # Try to get coin info from spacescan
    print(f"\n[6] Checking spacescan for coin...")
    url3 = f"https://api2.spacescan.io/1/xch/coin/address/{puzzle_address}"
    try:
        req = urllib.request.Request(url3, headers={"User-Agent": "XCHPredict/0.1"})
        resp = urllib.request.urlopen(req, timeout=10)
        coin_data = json.loads(resp.read())
        print(f"  Result: {json.dumps(coin_data)[:500]}")
        
        if coin_data.get("data") and len(coin_data["data"]) > 0:
            coin = coin_data["data"][0]
            parent_id = coin.get("parent_coin_info") or coin.get("parent_id")
            coin_id = coin.get("coin_id") or coin.get("id")
            print(f"\n  ✅ Found coin!")
            print(f"     Coin ID: {coin_id}")
            print(f"     Parent:  {parent_id}")
            
            # Build and sign spend bundle
            print(f"\n[7] Building spend bundle...")
            coin_spend = {
                "coin_spends": [{
                    "coin": {
                        "parent_coin_info": parent_id,
                        "puzzle_hash": curried_hash,
                        "amount": test_amount,
                    },
                    "puzzle_reveal": curried_hex,
                    "solution": solution_hex,
                }]
            }
            
            print(f"  Signing with oracle key...")
            sign_result = sage_rpc("sign_coin_spends", {
                "coin_spends": coin_spend["coin_spends"],
                "partial": False,
            })
            print(f"  Sign result: {json.dumps(sign_result)[:200]}")
            
            if sign_result and "spend_bundle" in sign_result:
                print(f"\n[8] Submitting transaction...")
                submit_result = sage_rpc("submit_transaction", {
                    "spend_bundle": sign_result["spend_bundle"]
                })
                print(f"  Submit result: {json.dumps(submit_result)[:200]}")
                print(f"\n  🎉 Transaction submitted! Check spacescan for confirmation.")
            else:
                print(f"\n  ⚠️ Signing failed or unexpected format.")
                print(f"  Spend bundle saved for manual submission.")
                
            bundle_path = f"{PROJECT_DIR}/tests/spend_bundle.json"
            with open(bundle_path, "w") as f:
                json.dump(coin_spend, f, indent=2)
            print(f"  Saved: {bundle_path}")
        else:
            print(f"\n  Coin not found yet — may need more confirmations.")
            print(f"  Check: https://spacescan.io/address/{puzzle_address}")
            print(f"  Re-run this script once the coin appears.")
    except Exception as e:
        print(f"  Spacescan check failed: {e}")
        print(f"  Check manually: https://spacescan.io/address/{puzzle_address}")

if __name__ == "__main__":
    main()
