#!/usr/bin/env python3
"""
ChiaPredict — Resolve a prediction market.

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

PROJECT_DIR = "/Users/alphanerd/Dev/chia-predict"
ACTIVATE = f"source {PROJECT_DIR}/.venv/bin/activate"


def run(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"ERROR: {cmd[:100]}")
        print(f"STDERR: {r.stderr[:300]}")
        sys.exit(1)
    return r.stdout.strip()


def sage_rpc(method, body):
    raw = run(f"sage rpc {method} '{json.dumps(body)}'", check=False)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def compute_coin_id(parent_hex, puzzle_hash_hex, amount):
    parent = bytes.fromhex(parent_hex)
    ph = bytes.fromhex(puzzle_hash_hex)
    if amount == 0:
        return hashlib.sha256(parent + ph + b"").hexdigest()
    byte_count = (amount.bit_length() + 8) // 8
    amt_bytes = amount.to_bytes(byte_count, "big")
    return hashlib.sha256(parent + ph + amt_bytes).hexdigest()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Resolve a ChiaPredict market")
    parser.add_argument("market_dir", help="Path to market directory")
    parser.add_argument("--outcome", choices=["yes", "no"], required=True)
    parser.add_argument("--receiver", help="Receiver XCH address (default: oracle wallet)")
    args = parser.parse_args()

    state_path = f"{args.market_dir}/state.json"
    with open(state_path) as f:
        state = json.load(f)

    outcome = 1 if args.outcome == "yes" else 0
    curried_hash = state["puzzle"]["curried_hash"]
    genesis = state["genesis_challenge"]

    print("=" * 60)
    print(f"Resolving: {state['question']}")
    print(f"Outcome: {'YES' if outcome else 'NO'}")
    print("=" * 60)

    # Find unspent coins at puzzle address
    print("\n[1] Finding coins at puzzle address...")
    url = "https://kraken.fireacademy.io/leaflet/get_coin_records_by_puzzle_hash"
    body = json.dumps({"puzzle_hash": f"0x{curried_hash}", "include_spent_coins": False}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "User-Agent": "ChiaPredict/0.1"
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
    sk_hex = sk_result["secrets"]["secret_key"]

    from blspy import AugSchemeMPL, PrivateKey

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

        # Build solution
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
            headers={"Content-Type": "application/json", "User-Agent": "ChiaPredict/0.1"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            result = resp.read().decode()
            print(f"  Result: {result}")
        except Exception as e:
            error_body = e.read().decode()[:300] if hasattr(e, "read") else ""
            print(f"  Error: {e} {error_body}")

    # Update state
    state["phase"] = "resolved"
    state["resolution"] = {
        "outcome": "YES" if outcome else "NO",
        "resolved_at": __import__("time").time(),
        "receiver_ph": receiver_ph,
    }
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ Market Resolved: {'YES' if outcome else 'NO'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
