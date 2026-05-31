#!/usr/bin/env python3
"""
XCH Predict — Post redemption offers for a resolved market.

After oracle resolution, this posts Dexie offers to buy back winning CATs at 1:1 XCH.
Losing CATs become worthless (no buyback offer).

Usage:
  python3 redeem_market.py markets/<id>

Prerequisites:
  - Market must be resolved (run resolve_market.py first)
  - Resolver wallet must have XCH to back redemption offers
"""

import json
import subprocess
import sys
import time
import urllib.request
import argparse
import os

# Get script directory and project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

# OFF LIMITS — never interact
FORBIDDEN_FPS = [1849776284]


def sage_rpc(method, body):
    try:
        r = subprocess.run(
            ["sage", "rpc", method, json.dumps(body)],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        if not r.stdout.strip():
            return None
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        print(f"WARNING: sage_rpc {method} returned invalid JSON: {r.stdout[:200]}")
        return {"raw": r.stdout.strip()}
    except Exception as e:
        print(f"ERROR: sage_rpc {method} failed: {e}")
        return None


def post_to_dexie(offer_str):
    body = json.dumps({"offer": offer_str}).encode()
    req = urllib.request.Request(
        "https://dexie.space/v1/offers",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "XCH Predict/0.1"},
    )
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser(description="Post redemption offers for resolved market")
    parser.add_argument("market_dir", help="Path to market directory")
    parser.add_argument("--redeem-qty", type=int, default=1000,
                        help="Number of winning CATs to offer to buy back per offer")
    parser.add_argument("--price", type=int, default=1,
                        help="XCH mojos per CAT token (default: 1 = face value)")
    parser.add_argument("--wallet-fp", type=int, default=None,
                        help="Wallet fingerprint to use for redemption (default: oracle wallet)")
    parser.add_argument("--fee", type=int, default=0,
                        help="Fee in mojos for transactions (default: 0)")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    state_path = f"{args.market_dir}/state.json"
    with open(state_path) as f:
        state = json.load(f)
    
    # Check forbidden fingerprints before any wallet interaction
    oracle_fp = state["oracle"]["fingerprint"]
    wallet_fp = args.wallet_fp or oracle_fp
    
    if oracle_fp in FORBIDDEN_FPS or wallet_fp in FORBIDDEN_FPS:
        print(f"❌ Wallet fp:{oracle_fp} or {wallet_fp} is FORBIDDEN! Redemption blocked.")
        sys.exit(1)

    if state.get("phase") != "resolved":
        print(f"❌ Market not resolved (phase: {state.get('phase')})")
        print("   Run resolve_market.py first.")
        sys.exit(1)

    outcome = state["resolution"]["outcome"]
    winning_asset = state["yes_cat"]["asset_id"] if outcome == "YES" else state["no_cat"]["asset_id"]
    losing_asset = state["no_cat"]["asset_id"] if outcome == "YES" else state["yes_cat"]["asset_id"]
    buyback_amount = args.redeem_qty * args.price

    print("=" * 60)
    print(f"XCH Predict — Redemption")
    print(f"  Question: {state['question']}")
    print(f"  Outcome: {outcome}")
    print(f"  Winning CAT: {winning_asset[:16]}...")
    print(f"  Losing CAT:  {losing_asset[:16]}... (worthless)")
    print("=" * 60)
    
    # Confirmation prompt
    if not args.yes:
        print(f"\nYou are about to create a REDEMPTION OFFER:")
        print(f"  Question: {state['question']}")
        print(f"  Winning side: {outcome}")
        print(f"  Buyback amount: {buyback_amount} mojos for {args.redeem_qty} tokens")
        print(f"  This will lock {buyback_amount} mojos XCH in an offer")
        print()
        confirm = input("Type 'yes' to proceed: ").strip().lower()
        if confirm != "yes":
            print("Redemption cancelled.")
            sys.exit(0)

    # Login to wallet
    fp = args.wallet_fp or state["oracle"]["fingerprint"]
    login_result = sage_rpc("login", {"fingerprint": fp})
    if login_result is None or login_result.get("error"):
        print(f"  ❌ Login failed: {login_result}")
        sys.exit(1)
    time.sleep(2)

    sync = sage_rpc("get_sync_status", {})
    if not sync or "balance" not in sync:
        print(f"  ❌ Could not get wallet balance: {sync}")
        sys.exit(1)
        
    print(f"\n  Wallet balance: {sync['balance']} mojos")
    xch_needed = buyback_amount
    total_needed = xch_needed + args.fee  # Include fee in calculation
    if sync["balance"] < total_needed:
        print(f"  ❌ Need {total_needed} mojos ({xch_needed} + {args.fee} fee), only have {sync['balance']}")
        sys.exit(1)

    # Post offer: we REQUEST winning CATs, we OFFER XCH
    print(f"\n[1] Creating redemption offer...")
    print(f"    Buying {args.redeem_qty} winning CATs at {args.price} mojo each")
    print(f"    Total cost: {xch_needed} mojos + {args.fee} fee")

    offer_result = sage_rpc("make_offer", {
        "offered_assets": [{"amount": xch_needed}],  # XCH we're paying
        "requested_assets": [{"asset_id": winning_asset, "amount": args.redeem_qty}],  # CATs we want back
        "fee": args.fee,
    })

    if not offer_result or "offer" not in offer_result:
        print(f"  ❌ Offer creation failed: {offer_result}")
        sys.exit(1)

    # Post to Dexie
    try:
        dexie = post_to_dexie(offer_result["offer"])
        dexie_url = f"https://dexie.space/offers/{dexie.get('id')}"
        print(f"  ✅ Redemption offer live: {dexie_url}")
    except Exception as e:
        print(f"  ❌ Failed to post offer to Dexie: {e}")
        print(f"  Offer created locally but not posted to marketplace")
        dexie_url = "Failed to post to Dexie"

    # Update state
    if "redemption" not in state:
        state["redemption"] = {"offers": []}
    state["redemption"]["offers"].append({
        "dexie_url": dexie_url,
        "offer_id": offer_result.get("offer_id", ""),
        "qty": args.redeem_qty,
        "price_per_token": args.price,
        "xch_total": xch_needed,
        "created_at": time.time(),
    })
    state["phase"] = "redeemable"
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ Redemption Active!")
    print(f"   Winners can trade {args.redeem_qty} {outcome} CATs → {xch_needed} mojos XCH")
    print(f"   Dexie: {dexie_url}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
