#!/usr/bin/env python3
"""
XCHPredict — Market command handlers for OpenClaw integration.
Called by the OpenClaw skill to execute market operations.

Commands:
  list                          List all markets
  status <market_dir>           Show market status with on-chain data
  create <question> [options]   Create a new market
  resolve <market_dir> <yes|no> Resolve a market
  fund <market_dir>             Show funding address
"""

import json
import subprocess
import hashlib
import sys
import os
import time
import urllib.request
import argparse

PROJECT_DIR = "/Users/alphanerd/Dev/chia-predict"
MARKETS_DIR = f"{PROJECT_DIR}/markets"
ACTIVATE = f"source {PROJECT_DIR}/.venv/bin/activate"
RUE_BIN = "/Users/alphanerd/Dev/rue-lang/target/release/rue"
PUZZLE_PATH = f"{PROJECT_DIR}/puzzles/oracle_payout.rue"
GENESIS_CHALLENGE = "ccd5bb71183532bff220ba46c268991a3ff07eb358e8255a65c30a2dce0e5fbb"
DEXIE_API = "https://dexie.space/v1/offers"
FIRE_API = "https://kraken.fireacademy.io/leaflet"


def run(cmd, check=True):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and r.returncode != 0:
        return None
    return r.stdout.strip()


def sage_rpc(method, body):
    raw = run(f"sage rpc {method} '{json.dumps(body)}'", check=False)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except:
        return None


def fire_api(endpoint, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"{FIRE_API}/{endpoint}", data=data,
        headers={"Content-Type": "application/json", "User-Agent": "XCHPredict/0.1"})
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())


def dexie_search(asset_id):
    url = f"https://dexie.space/v1/offers?offered={asset_id}&page=1&page_size=5"
    req = urllib.request.Request(url, headers={"User-Agent": "XCHPredict/0.1"})
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())


def cmd_list():
    """List all markets."""
    if not os.path.exists(MARKETS_DIR):
        print(json.dumps({"markets": [], "message": "No markets found."}))
        return

    markets = []
    for d in sorted(os.listdir(MARKETS_DIR)):
        state_path = f"{MARKETS_DIR}/{d}/state.json"
        if os.path.exists(state_path):
            with open(state_path) as f:
                s = json.load(f)
            markets.append({
                "id": d,
                "question": s.get("question", "Unknown"),
                "phase": s.get("phase", "unknown"),
                "yes_asset": s.get("yes_cat", {}).get("asset_id", ""),
                "no_asset": s.get("no_cat", {}).get("asset_id", ""),
                "address": s.get("puzzle", {}).get("address", ""),
                "resolution": s.get("resolution", {}).get("outcome", None),
            })

    print(json.dumps({"markets": markets}, indent=2))


def cmd_status(market_dir):
    """Show detailed market status."""
    state_path = f"{market_dir}/state.json"
    if not os.path.exists(state_path):
        state_path = f"{MARKETS_DIR}/{market_dir}/state.json"
    with open(state_path) as f:
        s = json.load(f)

    result = {
        "question": s["question"],
        "market_id": s["market_id"][:32],
        "phase": s.get("phase"),
        "oracle": s.get("oracle", {}).get("name"),
        "puzzle_address": s.get("puzzle", {}).get("address"),
        "yes": {"asset_id": s.get("yes_cat", {}).get("asset_id"), "supply": s.get("yes_cat", {}).get("supply")},
        "no": {"asset_id": s.get("no_cat", {}).get("asset_id"), "supply": s.get("no_cat", {}).get("supply")},
    }

    # Check on-chain balance
    try:
        ph = s["puzzle"]["curried_hash"]
        data = fire_api("get_coin_records_by_puzzle_hash",
            {"puzzle_hash": f"0x{ph}", "include_spent_coins": False})
        coins = data.get("coin_records", [])
        total = sum(c["coin"]["amount"] for c in coins)
        result["locked_xch"] = total
        result["locked_xch_display"] = f"{total / 1e12:.6f} XCH"
        result["unspent_coins"] = len(coins)
    except:
        result["locked_xch"] = 0
        result["unspent_coins"] = 0

    # Check Dexie offers
    dexie = {}
    for side, asset_id in [("yes", s.get("yes_cat", {}).get("asset_id")),
                            ("no", s.get("no_cat", {}).get("asset_id"))]:
        if asset_id:
            try:
                d = dexie_search(asset_id)
                offers = d.get("offers", [])
                active = [o for o in offers if o["status"] == 0]
                dexie[side] = {
                    "active_offers": len(active),
                    "urls": [f"https://dexie.space/offers/{o['id']}" for o in active[:3]],
                }
            except:
                dexie[side] = {"active_offers": 0, "urls": []}
    result["dexie"] = dexie

    if s.get("resolution"):
        result["resolution"] = s["resolution"]

    result["spacescan"] = f"https://spacescan.io/address/{s['puzzle']['address']}"

    print(json.dumps(result, indent=2))


def cmd_fund(market_dir):
    """Show funding info for a market."""
    state_path = f"{market_dir}/state.json"
    if not os.path.exists(state_path):
        state_path = f"{MARKETS_DIR}/{market_dir}/state.json"
    with open(state_path) as f:
        s = json.load(f)

    print(json.dumps({
        "question": s["question"],
        "address": s["puzzle"]["address"],
        "message": f"Send XCH to this address to fund the market. The funds will be locked until the oracle resolves the outcome.",
        "spacescan": f"https://spacescan.io/address/{s['puzzle']['address']}",
    }, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XCHPredict market commands")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list")

    p_status = sub.add_parser("status")
    p_status.add_argument("market_dir")

    p_fund = sub.add_parser("fund")
    p_fund.add_argument("market_dir")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list()
    elif args.command == "status":
        cmd_status(args.market_dir)
    elif args.command == "fund":
        cmd_fund(args.market_dir)
    else:
        parser.print_help()
