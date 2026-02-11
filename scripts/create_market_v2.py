#!/usr/bin/env python3
"""
ChiaPredict — Create a complete prediction market.

Usage:
  python3 create_market_v2.py "Will BTC hit 100k by March 2026?" --oracle-fp 1631380421
  python3 create_market_v2.py "Question?" --oracle-fp 1631380421 --mint-fp 861103475
  python3 create_market_v2.py "Question?" --oracle-fp 1631380421 --timeout-blocks 100000

Creates:
  1. YES and NO CATs (from --mint-fp wallet, defaults to oracle wallet)
  2. Curried oracle payout puzzle (v2 with timeout support)
  3. Dexie offers for both tokens
  4. Saves complete state to markets/<id>/state.json
"""

import json
import subprocess
import hashlib
import sys
import os
import time
import urllib.request
import argparse

# Get script directory and project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
RUE_BIN = os.environ.get("RUE_BIN", "rue")  # Default to rue on PATH
PUZZLE_V2_PATH = os.path.join(PROJECT_DIR, "puzzles", "oracle_payout_v2.rue")
PUZZLE_V1_PATH = os.path.join(PROJECT_DIR, "puzzles", "oracle_payout.rue")
ACTIVATE = f"source {PROJECT_DIR}/.venv/bin/activate"
GENESIS_CHALLENGE = "ccd5bb71183532bff220ba46c268991a3ff07eb358e8255a65c30a2dce0e5fbb"

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


def get_current_blockchain_height():
    """Get current blockchain height via FireAcademy API or Sage RPC."""
    # Try FireAcademy first
    try:
        req = urllib.request.Request(
            "https://kraken.fireacademy.io/leaflet/get_blockchain_state",
            headers={"Content-Type": "application/json", "User-Agent": "ChiaPredict/0.1"}
        )
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        if data.get("blockchain_state", {}).get("peak", {}).get("height"):
            return data["blockchain_state"]["peak"]["height"]
    except Exception as e:
        print(f"  WARNING: FireAcademy get_blockchain_state failed: {e}")
    
    # Fallback to Sage RPC
    try:
        result = sage_rpc("get_blockchain_state", {})
        if result and result.get("blockchain_state", {}).get("peak", {}).get("height"):
            return result["blockchain_state"]["peak"]["height"]
    except Exception as e:
        print(f"  WARNING: Sage get_blockchain_state failed: {e}")
    
    print("  ERROR: Could not get current blockchain height from any source")
    return None


def login_and_wait(fp, label="wallet"):
    """Login to a wallet and wait for sync."""
    if fp in FORBIDDEN_FPS:
        print(f"  ❌ Wallet fp:{fp} is OFF LIMITS!")
        sys.exit(1)
    print(f"  Logging into {label} (fp:{fp})...")
    sage_rpc("login", {"fingerprint": fp})
    # Wait for sync
    for _ in range(10):
        time.sleep(2)
        sync = sage_rpc("get_sync_status", {})
        if sync and sync.get("total_coins", 0) == sync.get("synced_coins", 0):
            print(f"  ✅ Synced ({sync['balance']} mojos, {sync['synced_coins']} coins)")
            return sync
    print(f"  ⚠️ Sync may be incomplete, proceeding...")
    return sync


def sign_and_submit(coin_spends):
    """Sign coin spends and submit to network."""
    signed = sage_rpc("sign_coin_spends", {"coin_spends": coin_spends, "partial": False})
    if not signed or "spend_bundle" not in signed:
        print(f"  Sign failed: {signed}")
        return None
    result = sage_rpc("submit_transaction", {"spend_bundle": signed["spend_bundle"]})
    return result


def wait_for_cat(asset_id, label, timeout_s=240):
    """Wait for a CAT to appear with balance in wallet."""
    print(f"  Waiting for {label} CAT confirmation...")
    for i in range(timeout_s // 10):
        time.sleep(10)
        token = sage_rpc("get_token", {"asset_id": asset_id})
        if token and token.get("token") and token["token"].get("balance", 0) > 0:
            print(f"  ✅ {label} CAT confirmed (balance: {token['token']['balance']})")
            return True
        print(f"  ...{(i+1)*10}s")
    return False


def extract_asset_id(result):
    """Extract asset_id from issue_cat response."""
    for inp in result.get("summary", {}).get("inputs", []):
        aid = inp.get("asset", {}).get("asset_id")
        if aid:
            return aid
    return None


def post_to_dexie(offer_str):
    """Post an offer to Dexie."""
    body = json.dumps({"offer": offer_str}).encode()
    req = urllib.request.Request(
        "https://dexie.space/v1/offers",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "ChiaPredict/0.1"},
    )
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())


def create_dexie_offer(asset_id, ticker, offer_qty, offer_price, fee=0):
    """Create and post a Dexie offer for a CAT."""
    print(f"  Creating {ticker} offer ({offer_qty} tokens @ {offer_price} mojos each)...")
    xch_amount = offer_qty * offer_price // 1000
    offer_result = sage_rpc("make_offer", {
        "offered_assets": [{"asset_id": asset_id, "amount": offer_qty}],
        "requested_assets": [{"amount": xch_amount}],
        "fee": fee,
    })
    if not offer_result or "offer" not in offer_result:
        print(f"  ❌ {ticker} offer creation failed: {offer_result}")
        return None
    try:
        dexie = post_to_dexie(offer_result["offer"])
        url = f"https://dexie.space/offers/{dexie.get('id')}"
        print(f"  ✅ {ticker}: {url}")
        return {
            "offer_id": offer_result.get("offer_id", ""),
            "dexie_id": dexie.get("id"),
            "dexie_url": url,
            "offered": f"{offer_qty} {ticker}",
            "requested": f"{xch_amount} mojos XCH",
        }
    except Exception as e:
        print(f"  ❌ {ticker} Dexie post failed: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Create a ChiaPredict market")
    parser.add_argument("question", help="The market question")
    parser.add_argument("--oracle-fp", type=int, default=1631380421, help="Oracle wallet fingerprint")
    parser.add_argument("--mint-fp", type=int, default=None,
                        help="Wallet for minting CATs (default: oracle wallet)")
    parser.add_argument("--supply", type=int, default=1000000, help="Token supply per side")
    parser.add_argument("--offer-qty", type=int, default=1000, help="Tokens to list on Dexie")
    parser.add_argument("--offer-price", type=int, default=500, help="XCH mojos per 1000 tokens (500 = 50%%)")
    parser.add_argument("--timeout-blocks", type=int, default=0,
                        help="Timeout in blocks for refund (0 = no timeout, v1 puzzle)")
    parser.add_argument("--fund-amount", type=int, default=0,
                        help="Mojos to send to puzzle after creation (0 = skip)")
    parser.add_argument("--fee", type=int, default=0,
                        help="Fee in mojos for transactions (default: 0)")
    args = parser.parse_args()

    mint_fp = args.mint_fp or args.oracle_fp
    use_v2 = args.timeout_blocks > 0

    for fp in [args.oracle_fp, mint_fp]:
        if fp in FORBIDDEN_FPS:
            print(f"❌ Wallet fp:{fp} is OFF LIMITS!")
            sys.exit(1)

    # Get oracle key info first to include in market_id
    login_and_wait(args.oracle_fp, "oracle")
    keys = sage_rpc("get_keys", {})
    oracle_key = None
    for k in keys["keys"]:
        if k["fingerprint"] == args.oracle_fp:
            oracle_key = k
            break
    if not oracle_key:
        print(f"  ❌ Oracle key fp:{args.oracle_fp} not found!")
        sys.exit(1)
        
    # Generate market_id as per PROTOCOL.md: sha256(question + timestamp + oracle_pubkey)
    timestamp = str(time.time())
    market_id_input = args.question + timestamp + oracle_key["public_key"]
    market_id = hashlib.sha256(market_id_input.encode()).hexdigest()
    market_dir = os.path.join(PROJECT_DIR, "markets", market_id[:16])
    os.makedirs(market_dir, exist_ok=True)

    print("=" * 60)
    print(f"ChiaPredict — Creating Market")
    print(f"  Question: {args.question}")
    print(f"  Market ID: {market_id[:32]}...")
    print(f"  Puzzle: {'v2 (timeout)' if use_v2 else 'v1 (no timeout)'}")
    if use_v2:
        print(f"  Timeout: {args.timeout_blocks} blocks")
    print("=" * 60)

    print(f"  Oracle: {oracle_key['name']} (fp: {oracle_key['fingerprint']})")

    # Switch to mint wallet if different
    if mint_fp != args.oracle_fp:
        login_and_wait(mint_fp, "mint")
        
    # Step 1: Handle timeout computation for v2 puzzles
    absolute_timeout_height = None
    if use_v2:
        print("\n[1] Computing absolute timeout height...")
        current_height = get_current_blockchain_height()
        if current_height is None:
            print("  ❌ Cannot determine current blockchain height for timeout calculation")
            sys.exit(1)
        absolute_timeout_height = current_height + args.timeout_blocks
        print(f"  Current height: {current_height}")
        print(f"  Timeout blocks: {args.timeout_blocks}")
        print(f"  Absolute timeout height: {absolute_timeout_height}")

    # Step 2: Issue YES CAT
    print(f"\n[2] Issuing YES CAT ({args.supply} supply)...")
    yes_result = sage_rpc("issue_cat", {
        "name": f"CP-YES {args.question[:30]}",
        "ticker": "YES",
        "amount": args.supply,
        "fee": args.fee,
    })
    if not yes_result or "coin_spends" not in yes_result:
        print(f"  ❌ Failed: {yes_result}")
        sys.exit(1)

    yes_asset_id = extract_asset_id(yes_result)
    if not yes_asset_id:
        print("  ❌ Could not extract YES asset_id")
        sys.exit(1)
    print(f"  YES asset: {yes_asset_id}")

    result = sign_and_submit(yes_result["coin_spends"])
    print(f"  Submit: {result}")

    # Must confirm before NO issuance
    if not wait_for_cat(yes_asset_id, "YES"):
        print("  ❌ YES CAT not confirmed. Cannot issue NO (would collide).")
        print("  Re-run after YES confirms in wallet.")
        sys.exit(1)

    # Step 3: Issue NO CAT
    print(f"\n[3] Issuing NO CAT ({args.supply} supply)...")
    no_result = sage_rpc("issue_cat", {
        "name": f"CP-NO {args.question[:30]}",
        "ticker": "NO",
        "amount": args.supply,
        "fee": args.fee,
    })
    if not no_result or "coin_spends" not in no_result:
        print(f"  ❌ Failed: {no_result}")
        sys.exit(1)

    no_asset_id = extract_asset_id(no_result)
    if not no_asset_id:
        print("  ❌ Could not extract NO asset_id")
        sys.exit(1)
    print(f"  NO asset: {no_asset_id}")

    if no_asset_id == yes_asset_id:
        print("  ❌ NO asset_id same as YES! This shouldn't happen.")
        sys.exit(1)

    result = sign_and_submit(no_result["coin_spends"])
    print(f"  Submit: {result}")

    if not wait_for_cat(no_asset_id, "NO", timeout_s=120):
        print("  ⚠️ NO CAT not confirmed yet, proceeding with puzzle...")

    # Step 4: Compile and curry puzzle
    puzzle_version = "v2" if use_v2 else "v1"
    puzzle_path = PUZZLE_V2_PATH if use_v2 else PUZZLE_V1_PATH
    print(f"\n[4] Compiling oracle puzzle ({puzzle_version})...")
    puzzle_clvm = run(f"{RUE_BIN} build {puzzle_path}")

    if use_v2:
        curried_clvm = run(
            f"{ACTIVATE} && cdv clsp curry '{puzzle_clvm}' "
            f"-a 0x{oracle_key['public_key']} "
            f"-a 0x{yes_asset_id} "
            f"-a 0x{no_asset_id} "
            f"-a 0x{market_id} "
            f"-a {absolute_timeout_height}"
        )
    else:
        curried_clvm = run(
            f"{ACTIVATE} && cdv clsp curry '{puzzle_clvm}' "
            f"-a 0x{oracle_key['public_key']} "
            f"-a 0x{yes_asset_id} "
            f"-a 0x{no_asset_id} "
            f"-a 0x{market_id}"
        )

    curried_hash = run(f"{ACTIVATE} && cdv clsp treehash '{curried_clvm}'")
    curried_hex = run(f"{ACTIVATE} && opc '{curried_clvm}'")
    puzzle_address = run(f"{ACTIVATE} && cdv encode {curried_hash} --prefix xch")

    # Verify round-trip
    verify_clvm = run(f"{ACTIVATE} && opd {curried_hex}")
    verify_hash = run(f"{ACTIVATE} && cdv clsp treehash '{verify_clvm}'")
    assert verify_hash == curried_hash, "Round-trip verification failed!"
    print(f"  Puzzle address: {puzzle_address}")
    print(f"  Curried hash: {curried_hash}")

    # Step 5: Fund puzzle (optional)
    if args.fund_amount > 0:
        print(f"\n[5a] Funding puzzle with {args.fund_amount} mojos...")
        fund_result = sage_rpc("send_xch", {
            "address": puzzle_address,
            "amount": args.fund_amount,
            "fee": args.fee,
        })
        if fund_result and "coin_spends" in fund_result:
            sign_and_submit(fund_result["coin_spends"])
            print(f"  ✅ Funded {args.fund_amount} mojos")
        else:
            print(f"  ⚠️ Funding failed: {fund_result}")

    # Step 6: Create Dexie offers
    print(f"\n[6] Creating Dexie offers...")
    offers = {}

    # Wait for all pending txs to clear before creating offers
    print("  Waiting for pending transactions to clear...")
    for i in range(30):  # up to 300s
        pending = sage_rpc("get_pending_transactions", {})
        n = len(pending.get("transactions", [])) if pending else 0
        if n == 0:
            print("  ✅ No pending transactions")
            break
        print(f"  ...{n} pending ({(i+1)*10}s)")
        time.sleep(10)
    else:
        print("  ⚠️ Still pending after 300s, attempting offers anyway...")

    yes_offer = create_dexie_offer(yes_asset_id, "YES", args.offer_qty, args.offer_price, args.fee)
    if yes_offer:
        offers["yes"] = yes_offer

    # Brief pause between offers
    time.sleep(5)

    no_offer = create_dexie_offer(no_asset_id, "NO", args.offer_qty, args.offer_price, args.fee)
    if no_offer:
        offers["no"] = no_offer

    # Step 7: Save state
    state = {
        "question": args.question,
        "market_id": market_id,
        "phase": "active",
        "created_at": time.time(),
        "puzzle_version": puzzle_version,
        "oracle": {
            "name": oracle_key["name"],
            "fingerprint": oracle_key["fingerprint"],
            "pubkey": oracle_key["public_key"],
        },
        "mint_wallet": {"fingerprint": mint_fp},
        "yes_cat": {"asset_id": yes_asset_id, "supply": args.supply},
        "no_cat": {"asset_id": no_asset_id, "supply": args.supply},
        "puzzle": {
            "base_clvm": puzzle_clvm,
            "curried_clvm": curried_clvm,
            "curried_hex": curried_hex,
            "curried_hash": curried_hash,
            "address": puzzle_address,
        },
        "timeout_blocks": args.timeout_blocks,
        "absolute_timeout_height": absolute_timeout_height if use_v2 else None,
        "offers": offers,
        "genesis_challenge": GENESIS_CHALLENGE,
    }

    state_path = f"{market_dir}/state.json"
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ Market Created!")
    print(f"  Question: {args.question}")
    print(f"  YES: {yes_asset_id}")
    print(f"  NO:  {no_asset_id}")
    print(f"  Puzzle ({puzzle_version}): {puzzle_address}")
    print(f"  State: {state_path}")
    for side in ["yes", "no"]:
        if side in offers:
            print(f"  Dexie {side.upper()}: {offers[side]['dexie_url']}")
    print(f"\n  Fund: sage rpc send_xch '{{\"address\": \"{puzzle_address}\", \"amount\": <mojos>, \"fee\": 0}}'")
    print(f"  Resolve: python3 scripts/resolve_market.py {market_dir} --outcome yes|no")
    print(f"  Redeem: python3 scripts/redeem_market.py {market_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
