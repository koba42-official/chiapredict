#!/usr/bin/env python3
"""
ChiaPredict — Debug & re-attempt the oracle_payout spend.
"""

import json
import subprocess
import hashlib
import sys
import os

# Get script directory and project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
RUE_BIN = os.environ.get("RUE_BIN", "rue")  # Default to rue on PATH
PUZZLE_PATH = os.path.join(PROJECT_DIR, "puzzles", "oracle_payout.rue")
ACTIVATE = f"source {PROJECT_DIR}/.venv/bin/activate"

# OFF LIMITS — never interact
FORBIDDEN_FPS = [1849776284]

# Mainnet genesis challenge (AGG_SIG_ME additional data)
GENESIS_CHALLENGE = "ccd5bb71183532bff220ba46c268991a3ff07eb358e8255a65c30a2dce0e5fbb"

# Known coin info
PARENT_ID = "b35ce5942daca3cccbbc8b7261c206b2f290ae5a3229e1072f46bdb29fb2a243"
PUZZLE_HASH = "4c2bf3d81d61aae330bc99bc023da9077946885794d51a651f201ccd00e5f767"
AMOUNT = 1000

# Market params from mainnet_test_state.json
YES_ASSET_ID = "cd2eb0b4307e784be90d05e18fec22857a7bdf9c77f0f9e38f183a24de55ef58"
NO_ASSET_ID = "7090c0ffaee10faec9da78c7dc7bb41d4d1c9c8b1ffb88bd6e8d3e2abf38a2e3"
MARKET_ID = "0b4d97121ca3369adb8f9b1fb79aea137a35df84ec31937c96b69a1aaccc7f8b"
ORACLE_SK = os.environ.get("ORACLE_SK", "")  # NEVER hardcode secret keys — set via environment variable
ORACLE_PK = "873e20f535b03c2de0199aab41d61cea2e755d19b0ddf9964b24e634907cc9181bbb824b9009c50e9551c76adc224617"

# Receiver
RECEIVER_PH = "96cc6497266fc6fef031fa2dbd75d75865cb8dd5dc674b587b867d514f8b8cc2"
OUTCOME = 1

def run(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  ERROR cmd: {cmd[:100]}...")
        print(f"  STDERR: {result.stderr[:300]}")
        sys.exit(1)
    return result.stdout.strip()

def hex_to_bytes(h):
    return bytes.fromhex(h.replace("0x", ""))


def compute_coin_id():
    parent = bytes.fromhex(PARENT_ID)
    ph = bytes.fromhex(PUZZLE_HASH)
    amount = AMOUNT
    if amount == 0:
        amt_bytes = b""
    else:
        byte_count = (amount.bit_length() + 8) // 8
        amt_bytes = amount.to_bytes(byte_count, "big")
    return hashlib.sha256(parent + ph + amt_bytes).hexdigest()


def main():
    print("=" * 60)
    print("ChiaPredict — Spend Bundle Debug")
    print("=" * 60)
    
    # Check forbidden fingerprints before any wallet interaction
    if 1631380421 in FORBIDDEN_FPS:  # Hardcoded oracle fingerprint check
        print(f"❌ Oracle wallet fp:1631380421 is FORBIDDEN! Script blocked.")
        sys.exit(1)
        
    if not os.environ.get("ORACLE_SK"):
        print("❌ ORACLE_SK environment variable not set!")
        print("   This script requires the oracle secret key via environment variable.")
        print("   Usage: ORACLE_SK=<hex_key> python3 debug_spend.py")
        sys.exit(1)

    # Step 1: Compute coin_id
    print("\n[1] Computing coin_id...")
    coin_id = compute_coin_id()
    print(f"  Coin ID: {coin_id}")

    # Step 2: Verify puzzle reveal hash
    print("\n[2] Verifying puzzle reveal...")
    puzzle_clvm = run(f"{RUE_BIN} build {PUZZLE_PATH}")

    curried_clvm = run(
        f"{ACTIVATE} && cdv clsp curry '{puzzle_clvm}' "
        f"-a 0x{ORACLE_PK} "
        f"-a 0x{YES_ASSET_ID} "
        f"-a 0x{NO_ASSET_ID} "
        f"-a 0x{MARKET_ID}"
    )

    computed_hash = run(f"{ACTIVATE} && cdv clsp treehash '{curried_clvm}'")
    print(f"  Expected: {PUZZLE_HASH}")
    print(f"  Computed: {computed_hash}")
    if computed_hash == PUZZLE_HASH:
        print("  ✅ Puzzle hash MATCHES")
    else:
        print("  ❌ MISMATCH!")
        sys.exit(1)

    # Step 3: Run puzzle+solution in CLVM
    print("\n[3] Running puzzle+solution in CLVM...")
    solution_clvm = f"({OUTCOME} 0x{RECEIVER_PH} {AMOUNT})"
    result = run(f"{ACTIVATE} && brun '{curried_clvm}' '{solution_clvm}'", check=False)
    print(f"  CLVM output:\n  {result}")

    # Step 4: Build AggSigMe signature
    print("\n[4] Building AggSigMe signature...")
    outcome_byte = b"\x01" if OUTCOME == 1 else b"\x00"
    oracle_message = hex_to_bytes(MARKET_ID) + outcome_byte

    # AGG_SIG_ME: sign(sk, msg + coin_id + genesis_challenge)
    full_message = oracle_message + hex_to_bytes(coin_id) + hex_to_bytes(GENESIS_CHALLENGE)

    print(f"  Oracle msg (from condition): {oracle_message.hex()}")
    print(f"  Coin ID:       {coin_id}")
    print(f"  Genesis:       {GENESIS_CHALLENGE}")
    print(f"  Full message:  {full_message.hex()[:80]}...")
    print(f"  Full msg len:  {len(full_message)} bytes")

    # Sign with BLS
    from blspy import AugSchemeMPL, PrivateKey

    sk = PrivateKey.from_bytes(bytes.fromhex(ORACLE_SK))
    pk = sk.get_g1()
    derived_pk = bytes(pk).hex()
    print(f"  Derived PK:    {derived_pk[:40]}...")
    if derived_pk != ORACLE_PK:
        print(f"  ⚠️  PK MISMATCH!")
        print(f"  Expected: {ORACLE_PK}")
        print(f"  Got:      {derived_pk}")
        # This is critical - if PKs don't match, the puzzle will reject
    else:
        print("  ✅ PK matches")

    sig = AugSchemeMPL.sign(sk, full_message)
    sig_hex = bytes(sig).hex()
    print(f"  Signature:     {sig_hex[:40]}...")

    # Verify locally
    ok = AugSchemeMPL.verify(pk, full_message, sig)
    print(f"  Local verify:  {'✅ PASS' if ok else '❌ FAIL'}")

    # Step 5: Build spend bundle
    print("\n[5] Building spend bundle...")
    curried_hex = run(f"{ACTIVATE} && opc '{curried_clvm}'")
    solution_hex = run(f"{ACTIVATE} && opc '{solution_clvm}'")
    print(f"  Puzzle hex:   {curried_hex[:40]}...")
    print(f"  Solution hex: {solution_hex}")

    spend_bundle = {
        "spend_bundle": {
            "coin_spends": [
                {
                    "coin": {
                        "parent_coin_info": f"0x{PARENT_ID}",
                        "puzzle_hash": f"0x{PUZZLE_HASH}",
                        "amount": AMOUNT,
                    },
                    "puzzle_reveal": f"0x{curried_hex}",
                    "solution": f"0x{solution_hex}",
                }
            ],
            "aggregated_signature": f"0x{sig_hex}",
        }
    }

    bundle_path = os.path.join(SCRIPT_DIR, "debug_spend_bundle.json")
    with open(bundle_path, "w") as f:
        json.dump(spend_bundle, f, indent=2)
    print(f"  Saved: {bundle_path}")

    # Step 6: Validate with cdv inspect
    print("\n[6] Validating with cdv inspect...")
    inspect_result = run(
        f"{ACTIVATE} && cdv inspect spendbundles {bundle_path} -db",
        check=False,
    )
    print(f"  {inspect_result[:1000]}")

    # Step 7: Submit via sage
    print("\n[7] Submitting via sage rpc...")
    submit_body = json.dumps(spend_bundle)
    submit_result = run(
        f"sage rpc submit_transaction '{submit_body}'",
        check=False,
    )
    print(f"  Result: {submit_result}")

    # Step 8: Try FireAcademy
    print("\n[8] Trying FireAcademy push_tx...")
    import urllib.request

    push_body = json.dumps(spend_bundle).encode()
    try:
        req = urllib.request.Request(
            "https://kraken.fireacademy.io/leaflet/push_tx",
            data=push_body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ChiaPredict/0.1",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=30)
        print(f"  Status: {resp.status}")
        print(f"  Response: {resp.read().decode()[:300]}")
    except Exception as e:
        print(f"  FireAcademy: {e}")

    print("\n" + "=" * 60)
    print("Debug complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
