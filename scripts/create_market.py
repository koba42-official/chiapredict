#!/usr/bin/env python3
"""
XCH Predict — Create a prediction market.

Usage:
  python3 create_market.py --question "Will BTC hit 100k by April?" --amount 1000000

This script:
  1. Compiles the oracle_payout puzzle
  2. Issues YES and NO CATs (standard single-issuance)
  3. Curries the puzzle with market parameters
  4. Locks XCH into curried puzzle coins
  5. Creates initial offers on Dexie
"""

import json
import subprocess
import hashlib
import sys
import os
import time
import argparse

RUE_BIN = "/Users/alphanerd/Dev/rue-lang/target/release/rue"
PUZZLE_PATH = "/Users/alphanerd/Dev/chia-predict/puzzles/oracle_payout.rue"
MARKETS_DIR = "/Users/alphanerd/Dev/chia-predict/markets"

def run(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"ERROR: {cmd}\nSTDERR: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def sage_rpc(method, body=None):
    body = body or {}
    result = run(f"sage rpc {method} '{json.dumps(body)}'")
    return json.loads(result)

def create_market(question, amount_mojos, oracle_fingerprint=None):
    """Create a new prediction market."""
    
    print(f"\n🎯 Creating market: \"{question}\"")
    print(f"   Locked amount: {amount_mojos} mojos ({amount_mojos / 1e12:.6f} XCH)")
    
    # Get oracle key (default: first key in wallet)
    keys = sage_rpc("get_keys")
    if oracle_fingerprint:
        oracle_key = next(
            (k for k in keys["keys"] if k["fingerprint"] == oracle_fingerprint), 
            None
        )
        if not oracle_key:
            print(f"ERROR: Fingerprint {oracle_fingerprint} not found")
            sys.exit(1)
    else:
        oracle_key = keys["keys"][0]
    
    oracle_pubkey = oracle_key["public_key"]
    print(f"   Oracle: {oracle_key['name']} ({oracle_pubkey[:16]}...)")
    
    # Generate unique market ID
    market_seed = f"{question}:{time.time()}:{oracle_pubkey}"
    market_id = hashlib.sha256(market_seed.encode()).hexdigest()
    
    # Step 1: Issue YES CAT
    print("\n📝 Step 1: Issuing YES CAT...")
    yes_result = sage_rpc("issue_cat", {
        "amount": amount_mojos // 1000,  # CAT amount (1 CAT = 1000 mojos)
        "name": f"YES: {question[:30]}",
        "ticker": "YES",
        "fee": 0,
    })
    print(f"   YES CAT issued. TX: {json.dumps(yes_result)[:100]}...")
    
    # Step 2: Issue NO CAT
    print("\n📝 Step 2: Issuing NO CAT...")
    no_result = sage_rpc("issue_cat", {
        "amount": amount_mojos // 1000,
        "name": f"NO: {question[:30]}",
        "ticker": "NO",
        "fee": 0,
    })
    print(f"   NO CAT issued. TX: {json.dumps(no_result)[:100]}...")
    
    # Step 3: Compile and curry puzzle
    print("\n📝 Step 3: Compiling puzzle...")
    puzzle_hex = run(f"{RUE_BIN} build {PUZZLE_PATH} -x")
    puzzle_hash = run(f"{RUE_BIN} build {PUZZLE_PATH} -h")
    print(f"   Puzzle hash: {puzzle_hash}")
    
    # Save market data
    os.makedirs(MARKETS_DIR, exist_ok=True)
    market_data = {
        "market_id": market_id,
        "question": question,
        "oracle_pubkey": oracle_pubkey,
        "oracle_name": oracle_key["name"],
        "oracle_fingerprint": oracle_key["fingerprint"],
        "amount_mojos": amount_mojos,
        "puzzle_hash": puzzle_hash,
        "puzzle_hex": puzzle_hex,
        "status": "pending_confirmation",
        "created_at": time.time(),
        "yes_cat": yes_result,
        "no_cat": no_result,
    }
    
    market_file = os.path.join(MARKETS_DIR, f"{market_id[:16]}.json")
    with open(market_file, "w") as f:
        json.dump(market_data, f, indent=2)
    
    print(f"\n✅ Market created!")
    print(f"   Market ID: {market_id}")
    print(f"   Saved to: {market_file}")
    print(f"\n⏳ Next steps:")
    print(f"   1. Wait for CAT issuance to confirm")
    print(f"   2. Lock XCH into oracle_payout puzzle")
    print(f"   3. Create initial YES/NO offers on Dexie")
    
    return market_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a XCH Predict market")
    parser.add_argument("--question", required=True, help="Market question")
    parser.add_argument("--amount", type=int, default=1000000000, help="Amount in mojos (default: 1 XCH)")
    parser.add_argument("--oracle-fingerprint", type=int, help="Oracle key fingerprint")
    args = parser.parse_args()
    
    create_market(args.question, args.amount, args.oracle_fingerprint)
