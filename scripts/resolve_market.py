#!/usr/bin/env python3
"""
XCH Predict — Resolve a prediction market.

Usage:
  python3 resolve_market.py markets/<id> --outcome yes
  python3 resolve_market.py markets/<id> --outcome no
"""

import json
import subprocess
import hashlib
import sys
import os
import urllib.request
import time

# Get script directory and project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
ACTIVATE = f"source {PROJECT_DIR}/.venv/bin/activate"

# OFF LIMITS — never interact
FORBIDDEN_FPS = [1849776284]


def run(cmd, check=True):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env={**os.environ, "PYTHONUNBUFFERED": "1"})
        if check and r.returncode != 0:
            print(f"ERROR: {cmd[:100]}")
            print(f"STDERR: {r.stderr[:300]}")
            sys.exit(1)
        return r.stdout.strip()
    except Exception as e:
        print(f"ERROR running command: {e}")
        if check:
            sys.exit(1)
        return ""


def sage_rpc(method, body):
    try:
        raw = run(f"sage rpc {method} '{json.dumps(body)}'", check=False)
        if not raw:
            return None
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"WARNING: sage_rpc {method} returned invalid JSON: {raw[:200]}")
        return {"raw": raw}
    except Exception as e:
        print(f"ERROR: sage_rpc {method} failed: {e}")
        return None


def compute_coin_id(parent_hex, puzzle_hash_hex, amount):
    parent = bytes.fromhex(parent_hex)
    ph = bytes.fromhex(puzzle_hash_hex)
    if amount == 0:
        return hashlib.sha256(parent + ph + b"").hexdigest()
    byte_count = (amount.bit_length() + 8) // 8
    amt_bytes = amount.to_bytes(byte_count, "big")
    return hashlib.sha256(parent + ph + amt_bytes).hexdigest()


def wait_for_coin_spent(coin_id, timeout_seconds=120):
    """Poll get_coin_record_by_name until coin shows as spent."""
    print(f"  Waiting for coin {coin_id[:16]}... to be spent (timeout: {timeout_seconds}s)")
    
    for i in range(timeout_seconds // 10):
        try:
            # Try FireAcademy first
            url = "https://kraken.fireacademy.io/leaflet/get_coin_record_by_name"
            body = json.dumps({"name": f"0x{coin_id}"}).encode()
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json", "User-Agent": "XCH Predict/0.1"
            })
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            
            if data.get("coin_record") and data["coin_record"].get("spent"):
                print(f"  ✅ Coin confirmed spent at height {data['coin_record']['spent_block_index']}")
                return True
                
        except Exception as e:
            print(f"  WARNING: FireAcademy check failed: {e}")
            
            # Fallback to Sage RPC
            try:
                result = sage_rpc("get_coin_record_by_name", {"name": f"0x{coin_id}"})
                if result and result.get("coin_record", {}).get("spent"):
                    print(f"  ✅ Coin confirmed spent (Sage)")
                    return True
            except Exception:
                pass
        
        print(f"  ...{(i+1)*10}s")
        time.sleep(10)
    
    print(f"  ⚠️ Coin not confirmed spent after {timeout_seconds}s")
    return False


def cancel_offers_for_market(state):
    """Cancel any active offers for this market using Sage cancel_offers RPC."""
    try:
        offers_to_cancel = []
        
        # Collect offer IDs from state
        for side in ["yes", "no"]:
            if side in state.get("offers", {}):
                offer_id = state["offers"][side].get("offer_id")
                if offer_id:
                    offers_to_cancel.append(offer_id)
        
        if not offers_to_cancel:
            print("  No offers to cancel")
            return
        
        print(f"  Cancelling {len(offers_to_cancel)} offers...")
        
        # Use Sage cancel_offers for on-chain cancellation
        result = sage_rpc("cancel_offers", {"offer_ids": offers_to_cancel})
        if result and not result.get("error"):
            print(f"  ✅ Successfully cancelled {len(offers_to_cancel)} offers on-chain")
        else:
            print(f"  ⚠️ cancel_offers failed: {result}")
            
            # Fallback to delete_offer (local only)
            print("  Falling back to local delete_offer...")
            for offer_id in offers_to_cancel:
                sage_rpc("delete_offer", {"offer_id": offer_id})
            
    except Exception as e:
        print(f"  WARNING: Offer cancellation failed: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Resolve a XCH Predict market")
    parser.add_argument("market_dir", help="Path to market directory")
    parser.add_argument("--outcome", choices=["yes", "no"], required=True)
    parser.add_argument("--receiver", help="Receiver XCH address (default: oracle wallet)")
    parser.add_argument("--fee", type=int, default=0, help="Fee in mojos for transaction (default: 0)")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()
    
    # Check forbidden fingerprints before any wallet interaction
    state_path = f"{args.market_dir}/state.json"
    with open(state_path) as f:
        state = json.load(f)
    
    oracle_fp = state["oracle"]["fingerprint"]
    if oracle_fp in FORBIDDEN_FPS:
        print(f"❌ Oracle wallet fp:{oracle_fp} is FORBIDDEN! Resolution blocked.")
        sys.exit(1)

    outcome = 1 if args.outcome == "yes" else 0
    curried_hash = state["puzzle"]["curried_hash"]
    genesis = state["genesis_challenge"]
    puzzle_address = state["puzzle"]["address"]

    print("=" * 60)
    print(f"Resolving: {state['question']}")
    print(f"Outcome: {'YES' if outcome else 'NO'}")
    print(f"Puzzle Address: {puzzle_address}")
    print("=" * 60)
    
    # Confirmation prompt
    if not args.yes:
        print(f"\nYou are about to RESOLVE this market:")
        print(f"  Question: {state['question']}")
        print(f"  Outcome: {'YES' if outcome else 'NO'}")
        print(f"  Puzzle Address: {puzzle_address}")
        print(f"  This action cannot be undone!")
        print()
        confirm = input("Type 'yes' to proceed: ").strip().lower()
        if confirm != "yes":
            print("Resolution cancelled.")
            sys.exit(0)

    # Find unspent coins at puzzle address
    print("\n[1] Finding coins at puzzle address...")
    url = "https://kraken.fireacademy.io/leaflet/get_coin_records_by_puzzle_hash"
    body = json.dumps({"puzzle_hash": f"0x{curried_hash}", "include_spent_coins": False}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "User-Agent": "XCH Predict/0.1"
    })
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read())
    coins = data.get("coin_records", [])

    if not coins:
        print("  No unspent coins found!")
        sys.exit(1)

    print(f"  Found {len(coins)} unspent coin(s)")

    # Get receiver address
    if args.receiver:
        receiver_ph = run(f"{ACTIVATE} && cdv decode {args.receiver}")
    else:
        sage_rpc("login", {"fingerprint": state["oracle"]["fingerprint"]})
        sync = sage_rpc("get_sync_status", {})
        receiver_ph = run(f"{ACTIVATE} && cdv decode {sync['receive_address']}")
    print(f"  Receiver PH: {receiver_ph}")

    # Get oracle secret key
    print("\n[2] Getting oracle key...")
    sk_result = sage_rpc("get_secret_key", {"fingerprint": state["oracle"]["fingerprint"]})
    if not sk_result or "secrets" not in sk_result:
        print(f"  ❌ Failed to get secret key: {sk_result}")
        sys.exit(1)
    sk_hex = sk_result["secrets"]["secret_key"]

    try:
        from blspy import AugSchemeMPL, PrivateKey
    except ImportError:
        print("  ❌ blspy not installed. Run: pip install blspy")
        sys.exit(1)

    sk = PrivateKey.from_bytes(bytes.fromhex(sk_hex))
    pk = sk.get_g1()
    assert bytes(pk).hex() == state["oracle"]["pubkey"], "PK mismatch!"
    print("  ✅ Oracle key verified")

    # Spend each coin
    for rec in coins:
        coin = rec["coin"]
        parent = coin["parent_coin_info"].replace("0x", "")
        ph = coin["puzzle_hash"].replace("0x", "")
        amount = coin["amount"]
        coin_id = compute_coin_id(parent, ph, amount)

        print(f"\n[3] Spending coin {coin_id[:16]}... ({amount / 1e12:.6f} XCH)")

        # Build solution — v2 puzzles need (mode outcome receiver_ph amount), v1 needs (outcome receiver_ph amount)
        is_v2 = state.get("puzzle_version") == "v2" or state.get("timeout_blocks", 0) > 0
        if is_v2:
            solution_clvm = f"(0 {outcome} 0x{receiver_ph} {amount})"
        else:
            solution_clvm = f"({outcome} 0x{receiver_ph} {amount})"
        solution_hex = run(f"{ACTIVATE} && opc '{solution_clvm}'")

        # Verify CLVM execution
        clvm_out = run(
            f"{ACTIVATE} && brun '{state['puzzle']['curried_clvm']}' '{solution_clvm}'",
            check=False,
        )
        if "FAIL" in clvm_out or not clvm_out:
            print(f"  ❌ CLVM failed: {clvm_out}")
            continue
        print("  ✅ CLVM OK")

        # Sign
        outcome_byte = b"\x01" if outcome == 1 else b"\x00"
        oracle_msg = bytes.fromhex(state["market_id"]) + outcome_byte
        full_msg = oracle_msg + bytes.fromhex(coin_id) + bytes.fromhex(genesis)
        sig = AugSchemeMPL.sign(sk, full_msg)
        assert AugSchemeMPL.verify(pk, full_msg, sig), "Signature verification failed!"
        print("  ✅ Signature verified")

        # Build spend bundle
        spend_bundle = {
            "spend_bundle": {
                "coin_spends": [{
                    "coin": {
                        "parent_coin_info": f"0x{parent}",
                        "puzzle_hash": f"0x{ph}",
                        "amount": amount,
                    },
                    "puzzle_reveal": f"0x{state['puzzle']['curried_hex']}",
                    "solution": f"0x{solution_hex}",
                }],
                "aggregated_signature": f"0x{bytes(sig).hex()}",
            }
        }

        # Validate
        bundle_path = f"{args.market_dir}/resolve_bundle.json"
        with open(bundle_path, "w") as f:
            json.dump(spend_bundle, f, indent=2)
        inspect = run(f"{ACTIVATE} && cdv inspect spendbundles {bundle_path} -db", check=False)
        print(f"  Inspect: {inspect[:200]}")

        # Submit
        print("  Submitting...")
        push_body = json.dumps(spend_bundle).encode()
        req = urllib.request.Request(
            "https://kraken.fireacademy.io/leaflet/push_tx",
            data=push_body,
            headers={"Content-Type": "application/json", "User-Agent": "XCH Predict/0.1"},
            method="POST",
        )
        
        submission_successful = False
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            result = resp.read().decode()
            print(f"  Result: {result}")
            if resp.status == 200:
                submission_successful = True
        except Exception as e:
            error_body = e.read().decode()[:300] if hasattr(e, "read") else ""
            print(f"  Error: {e} {error_body}")
        
        # If submission failed, don't proceed
        if not submission_successful:
            print(f"  ❌ Transaction submission failed for coin {coin_id[:16]}...")
            continue
        
        # Wait for confirmation before considering this coin resolved
        if not wait_for_coin_spent(coin_id, timeout_seconds=120):
            print(f"  ❌ Coin {coin_id[:16]}... not confirmed spent within timeout")
            continue
            
        print(f"  ✅ Coin {coin_id[:16]}... successfully resolved")

    # Verify at least one coin was spent by re-checking
    try:
        verify_body = json.dumps({"puzzle_hash": f"0x{curried_hash}", "include_spent_coins": False}).encode()
        verify_req = urllib.request.Request(
            "https://kraken.fireacademy.io/leaflet/get_coin_records_by_puzzle_hash",
            data=verify_body, headers={"Content-Type": "application/json", "User-Agent": "XCH Predict/0.1"}
        )
        verify_resp = urllib.request.urlopen(verify_req, timeout=30)
        remaining = len(json.loads(verify_resp.read()).get("coin_records", []))
        coins_spent = len(coins) - remaining
        if coins_spent == 0:
            print("\n❌ No coins were successfully spent. Market NOT resolved.")
            sys.exit(1)
        print(f"\n  ✅ {coins_spent} coin(s) spent successfully")
    except Exception as e:
        print(f"\n  ⚠️ Could not verify coin status: {e} — proceeding based on submission results")

    # Cancel active offers after successful resolution
    print("\n[4] Cancelling active offers...")
    cancel_offers_for_market(state)

    # Update state only after confirmed success
    state["phase"] = "resolved"
    state["resolution"] = {
        "outcome": "YES" if outcome else "NO",
        "resolved_at": time.time(),
        "receiver_ph": receiver_ph,
    }
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ Market Resolved: {'YES' if outcome else 'NO'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
