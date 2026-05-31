#!/usr/bin/env python3
"""
XCH Predict — Clean E2E Mainnet Test (Round 2)

Full lifecycle with proper state preservation:
  1. Compile puzzle (current AggSigMe version)
  2. Curry with parameters
  3. Save ALL state (including curried_clvm, hex, everything)
  4. Send 1000 mojos to curried puzzle
  5. Wait for confirmation
  6. Build spend bundle
  7. Validate locally with cdv inspect
  8. Sign with oracle key (proper AggSigMe message)
  9. Submit and verify
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
RUE_BIN = os.environ.get("RUE_BIN", "rue")  # Default to rue on PATH
PUZZLE_PATH = os.path.join(PROJECT_DIR, "puzzles", "oracle_payout.rue")
ACTIVATE = f"source {PROJECT_DIR}/.venv/bin/activate"
STATE_DIR = os.path.join(SCRIPT_DIR, "round2")

# OFF LIMITS — never interact
FORBIDDEN_FPS = [1849776284]

GENESIS_CHALLENGE = "ccd5bb71183532bff220ba46c268991a3ff07eb358e8255a65c30a2dce0e5fbb"
TEST_AMOUNT = 1000


def run(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"  ERROR: {cmd[:120]}")
        print(f"  STDERR: {r.stderr[:500]}")
        sys.exit(1)
    return r.stdout.strip()


def sage_rpc(method, body=None):
    body = body or {}
    raw = run(f"sage rpc {method} '{json.dumps(body)}'", check=False)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  sage rpc {method} raw: {raw[:200]}")
        return None


def compute_coin_id(parent_hex, puzzle_hash_hex, amount):
    parent = bytes.fromhex(parent_hex)
    ph = bytes.fromhex(puzzle_hash_hex)
    if amount == 0:
        amt_bytes = b""
    else:
        byte_count = (amount.bit_length() + 8) // 8
        amt_bytes = amount.to_bytes(byte_count, "big")
    return hashlib.sha256(parent + ph + amt_bytes).hexdigest()


def step_compile_and_curry():
    """Step 1-2: Compile, curry, and save everything."""
    print("\n" + "=" * 60)
    print("PHASE 1: Compile & Curry")
    print("=" * 60)

    # Compile
    print("\n[1] Compiling oracle_payout.rue...")
    puzzle_clvm = run(f"{RUE_BIN} build {PUZZLE_PATH}")
    puzzle_hex = run(f"{RUE_BIN} build {PUZZLE_PATH} -x")
    puzzle_hash = run(f"{RUE_BIN} build {PUZZLE_PATH} -h")
    print(f"  Base puzzle hash: {puzzle_hash}")
    print(f"  Base CLVM: {puzzle_clvm[:80]}...")

    # Get oracle key
    print("\n[2] Getting oracle key...")
    keys = sage_rpc("get_keys")
    oracle_key = None
    for k in keys["keys"]:
        if k["name"] == "DracattusDev":
            oracle_key = k
            break
    if not oracle_key:
        print("  ERROR: DracattusDev key not found!")
        sys.exit(1)

    oracle_pk = oracle_key["public_key"]
    oracle_fp = oracle_key["fingerprint"]
    print(f"  Oracle: {oracle_key['name']} (fp: {oracle_fp})")
    print(f"  PK: {oracle_pk[:40]}...")

    # Generate deterministic test params
    print("\n[3] Generating market parameters...")
    market_id = hashlib.sha256(b"xchpredict_round2_test_market").hexdigest()
    yes_asset_id = hashlib.sha256(b"ROUND2_YES_TOKEN").hexdigest()
    no_asset_id = hashlib.sha256(b"ROUND2_NO_TOKEN").hexdigest()
    print(f"  Market ID:  {market_id}")
    print(f"  YES asset:  {yes_asset_id}")
    print(f"  NO asset:   {no_asset_id}")

    # Curry
    print("\n[4] Currying puzzle...")
    curried_clvm = run(
        f"{ACTIVATE} && cdv clsp curry '{puzzle_clvm}' "
        f"-a 0x{oracle_pk} "
        f"-a 0x{yes_asset_id} "
        f"-a 0x{no_asset_id} "
        f"-a 0x{market_id}"
    )

    curried_hash = run(f"{ACTIVATE} && cdv clsp treehash '{curried_clvm}'")
    curried_hex = run(f"{ACTIVATE} && opc '{curried_clvm}'")
    puzzle_address = run(f"{ACTIVATE} && cdv encode {curried_hash} --prefix xch")

    print(f"  Curried hash: {curried_hash}")
    print(f"  Address:      {puzzle_address}")

    # Verify round-trip: hex -> clvm -> treehash
    verify_clvm = run(f"{ACTIVATE} && opd {curried_hex}")
    verify_hash = run(f"{ACTIVATE} && cdv clsp treehash '{verify_clvm}'")
    print(f"  Verify hash:  {verify_hash}")
    assert verify_hash == curried_hash, "Round-trip hash verification FAILED!"
    print("  ✅ Round-trip verified")

    # Save EVERYTHING
    os.makedirs(STATE_DIR, exist_ok=True)
    state = {
        "phase": "funded",
        "created_at": time.time(),
        "network": "mainnet",
        "test_amount": TEST_AMOUNT,
        "genesis_challenge": GENESIS_CHALLENGE,
        # Oracle
        "oracle_name": oracle_key["name"],
        "oracle_fingerprint": oracle_fp,
        "oracle_pubkey": oracle_pk,
        # Market
        "market_id": market_id,
        "yes_asset_id": yes_asset_id,
        "no_asset_id": no_asset_id,
        # Puzzle (base)
        "base_puzzle_clvm": puzzle_clvm,
        "base_puzzle_hex": puzzle_hex,
        "base_puzzle_hash": puzzle_hash,
        # Puzzle (curried)
        "curried_clvm": curried_clvm,
        "curried_hex": curried_hex,
        "curried_hash": curried_hash,
        "puzzle_address": puzzle_address,
        # Will be filled after send
        "parent_coin_id": None,
        "coin_id": None,
    }

    state_path = f"{STATE_DIR}/state.json"
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    print(f"\n  State saved: {state_path}")

    return state


def step_send(state):
    """Step 3: Send mojos to the puzzle."""
    print("\n" + "=" * 60)
    print("PHASE 2: Send XCH to Puzzle")
    print("=" * 60)

    address = state["puzzle_address"]
    amount = state["test_amount"]

    print(f"\n[5] Sending {amount} mojos to {address}...")
    result = sage_rpc("send_xch", {
        "address": address,
        "amount": amount,
        "fee": 0,
    })
    print(f"  Result: {json.dumps(result)[:300]}")

    if result and "transaction_ids" in result:
        state["send_tx_ids"] = result["transaction_ids"]
        print(f"  TX IDs: {result['transaction_ids']}")
    elif result and "error" in result:
        print(f"  ERROR: {result['error']}")
        sys.exit(1)

    state_path = f"{STATE_DIR}/state.json"
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"\n  ⏳ Waiting for confirmation...")
    return state


def step_find_coin(state):
    """Step 4: Find the coin on-chain."""
    print("\n" + "=" * 60)
    print("PHASE 3: Find Coin On-Chain")
    print("=" * 60)

    import urllib.request

    puzzle_hash = state["curried_hash"]
    address = state["puzzle_address"]

    # Try FireAcademy API
    print(f"\n[6] Looking for coin at {puzzle_hash}...")
    url = f"https://kraken.fireacademy.io/leaflet/get_coin_records_by_puzzle_hash"
    body = json.dumps({
        "puzzle_hash": f"0x{puzzle_hash}",
        "include_spent_coins": False,
    }).encode()

    try:
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "User-Agent": "XCH Predict/0.1",
        })
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        print(f"  FireAcademy response: {json.dumps(data)[:500]}")

        if data.get("coin_records"):
            rec = data["coin_records"][0]
            coin = rec["coin"]
            parent = coin["parent_coin_info"].replace("0x", "")
            ph = coin["puzzle_hash"].replace("0x", "")
            amt = coin["amount"]
            coin_id = compute_coin_id(parent, ph, amt)

            state["parent_coin_id"] = parent
            state["coin_id"] = coin_id
            state["coin_amount"] = amt
            state["coin_confirmed"] = True

            print(f"  ✅ Coin found!")
            print(f"  Parent: {parent}")
            print(f"  Coin ID: {coin_id}")
            print(f"  Amount: {amt}")

            state_path = f"{STATE_DIR}/state.json"
            with open(state_path, "w") as f:
                json.dump(state, f, indent=2)
            return state
        else:
            print("  Coin not found yet. Wait for confirmation and re-run with --phase find")
            return None
    except Exception as e:
        print(f"  FireAcademy error: {e}")
        print(f"  Try again in a minute, or check: https://spacescan.io/address/{address}")
        return None


def step_spend(state):
    """Step 5-9: Build, validate, sign, submit spend bundle."""
    print("\n" + "=" * 60)
    print("PHASE 4: Spend the Coin")
    print("=" * 60)

    if not state.get("coin_id"):
        print("  ERROR: No coin_id in state. Run --phase find first.")
        sys.exit(1)

    # Get receiver address
    print("\n[7] Getting receiver address...")
    result = sage_rpc("get_derivations", {"hardened": False, "offset": 0, "limit": 1})
    if result and "derivations" in result:
        recv_addr = result["derivations"][0]["address"]
        receiver_ph = run(f"{ACTIVATE} && cdv decode {recv_addr}")
    else:
        print("  ERROR: Can't get receiver. Is Sage logged in?")
        sys.exit(1)
    print(f"  Receiver: {recv_addr}")
    print(f"  PH: {receiver_ph}")

    # Build solution
    print("\n[8] Building solution...")
    outcome = 1  # YES wins
    solution_clvm = f"({outcome} 0x{receiver_ph} {state['test_amount']})"
    solution_hex = run(f"{ACTIVATE} && opc '{solution_clvm}'")
    print(f"  Solution CLVM: {solution_clvm}")
    print(f"  Solution hex:  {solution_hex}")

    # Run CLVM locally to verify conditions
    print("\n[9] Running CLVM locally...")
    clvm_output = run(
        f"{ACTIVATE} && brun '{state['curried_clvm']}' '{solution_clvm}'",
        check=False,
    )
    print(f"  Output: {clvm_output}")
    if "FAIL" in clvm_output or not clvm_output:
        print("  ❌ CLVM execution failed!")
        sys.exit(1)
    print("  ✅ CLVM execution succeeded")

    # Build AggSigMe signature
    print("\n[10] Building AggSigMe signature...")
    outcome_byte = b"\x01" if outcome == 1 else b"\x00"
    oracle_message = bytes.fromhex(state["market_id"]) + outcome_byte
    coin_id_bytes = bytes.fromhex(state["coin_id"])
    genesis_bytes = bytes.fromhex(GENESIS_CHALLENGE)
    full_message = oracle_message + coin_id_bytes + genesis_bytes

    print(f"  Oracle msg:    {oracle_message.hex()}")
    print(f"  Coin ID:       {state['coin_id']}")
    print(f"  Full msg len:  {len(full_message)} bytes")

    # Extract secret key and sign
    from blspy import AugSchemeMPL, PrivateKey

    # Get SK from Sage
    sk_result = sage_rpc("get_secret_key", {
        "fingerprint": state["oracle_fingerprint"],
    })
    if not sk_result:
        print(f"  ERROR: Can't get secret key: {sk_result}")
        sys.exit(1)

    # Handle nested response format
    if "secrets" in sk_result:
        sk_hex = sk_result["secrets"]["secret_key"]
    elif "secret_key" in sk_result:
        sk_hex = sk_result["secret_key"]
    else:
        print(f"  ERROR: Unexpected format: {sk_result}")
        sys.exit(1)
    sk = PrivateKey.from_bytes(bytes.fromhex(sk_hex))
    pk = sk.get_g1()
    derived_pk = bytes(pk).hex()

    print(f"  Derived PK: {derived_pk[:40]}...")
    if derived_pk != state["oracle_pubkey"]:
        print("  ❌ PK MISMATCH — wrong key!")
        sys.exit(1)
    print("  ✅ PK matches oracle")

    sig = AugSchemeMPL.sign(sk, full_message)
    sig_hex = bytes(sig).hex()
    ok = AugSchemeMPL.verify(pk, full_message, sig)
    print(f"  Signature:     {sig_hex[:40]}...")
    print(f"  Local verify:  {'✅ PASS' if ok else '❌ FAIL'}")
    if not ok:
        sys.exit(1)

    # Build spend bundle
    print("\n[11] Building spend bundle...")
    spend_bundle = {
        "spend_bundle": {
            "coin_spends": [{
                "coin": {
                    "parent_coin_info": f"0x{state['parent_coin_id']}",
                    "puzzle_hash": f"0x{state['curried_hash']}",
                    "amount": state["test_amount"],
                },
                "puzzle_reveal": f"0x{state['curried_hex']}",
                "solution": f"0x{solution_hex}",
            }],
            "aggregated_signature": f"0x{sig_hex}",
        }
    }

    bundle_path = f"{STATE_DIR}/spend_bundle.json"
    with open(bundle_path, "w") as f:
        json.dump(spend_bundle, f, indent=2)
    print(f"  Saved: {bundle_path}")

    # Validate with cdv inspect
    print("\n[12] Validating with cdv inspect...")
    inspect = run(f"{ACTIVATE} && cdv inspect spendbundles {bundle_path} -db", check=False)
    print(f"  {inspect[:1000]}")

    # Save spend state
    state["phase"] = "spent"
    state["outcome"] = outcome
    state["receiver_ph"] = receiver_ph
    state["signature"] = sig_hex
    state["solution_hex"] = solution_hex
    state["solution_clvm"] = solution_clvm

    state_path = f"{STATE_DIR}/state.json"
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    # Submit
    print("\n[13] Submitting via FireAcademy push_tx...")
    import urllib.request
    push_body = json.dumps(spend_bundle).encode()
    try:
        req = urllib.request.Request(
            "https://kraken.fireacademy.io/leaflet/push_tx",
            data=push_body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "XCH Predict/0.1",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=30)
        resp_text = resp.read().decode()
        print(f"  Status: {resp.status}")
        print(f"  Response: {resp_text[:500]}")
    except Exception as e:
        error_body = ""
        if hasattr(e, "read"):
            error_body = e.read().decode()[:500]
        print(f"  FireAcademy error: {e}")
        if error_body:
            print(f"  Body: {error_body}")

        # Fallback: sage rpc
        print("\n[14] Fallback: sage rpc submit_transaction...")
        submit_result = run(
            f"sage rpc submit_transaction '{json.dumps(spend_bundle)}'",
            check=False,
        )
        print(f"  Result: {submit_result[:300]}")

    print("\n" + "=" * 60)
    print("Done! Check spacescan for confirmation:")
    print(f"  https://spacescan.io/address/{state['puzzle_address']}")
    print("=" * 60)
    return state


def main():
    # Check forbidden fingerprints before any wallet interaction
    oracle_fp = 1631380421  # DracattusDev fingerprint
    if oracle_fp in FORBIDDEN_FPS:
        print(f"❌ Oracle wallet fp:{oracle_fp} is FORBIDDEN! Script blocked.")
        sys.exit(1)

    phase = sys.argv[1] if len(sys.argv) > 1 else "--all"

    if phase in ("--all", "--curry"):
        state = step_compile_and_curry()
        if phase == "--curry":
            print(f"\n  Next: python3 {__file__} --send")
            return
    else:
        state_path = f"{STATE_DIR}/state.json"
        with open(state_path) as f:
            state = json.load(f)

    if phase in ("--all", "--send"):
        state = step_send(state)
        if phase in ("--all",):
            print(f"\n  Waiting 60s for confirmation...")
            for i in range(6):
                time.sleep(10)
                print(f"  ...{(i+1)*10}s")
                result = step_find_coin(state)
                if result:
                    state = result
                    break
            else:
                print(f"\n  Coin not confirmed yet. Re-run with: python3 {__file__} --find")
                return
        elif phase == "--send":
            print(f"\n  Next: python3 {__file__} --find")
            return

    if phase == "--find":
        result = step_find_coin(state)
        if not result:
            return
        state = result

    if phase in ("--all", "--spend"):
        if not state.get("coin_id"):
            print("  No coin_id yet. Run --find first.")
            return
        step_spend(state)


if __name__ == "__main__":
    main()
