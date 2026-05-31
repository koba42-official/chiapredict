# XCH Predict: Proof of Concept Report

**Trustless Prediction Markets on the XCH Blockchain**

Date: February 10, 2026
Author: DracattusDev
Network: XCH Mainnet

---

## Executive Summary

XCH Predict is the first prediction market infrastructure built on the XCH blockchain. On February 10, 2026, we successfully demonstrated the complete lifecycle of a prediction market on XCH mainnet: custom puzzle deployment, CAT token issuance, decentralized exchange listing, market funding, oracle resolution, and payout — all using a single custom Rue puzzle and native XCH primitives.

This document provides a technical summary of the proof of concept, on-chain evidence for every transaction, and links for independent verification.

---

## Architecture

XCH Predict uses four XCH-native components:

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Oracle Puzzle** | Rue → CLVM (AggSigMe) | Locks XCH until oracle signs the outcome |
| **YES/NO Tokens** | XCH Asset Tokens (CATs) | Tradeable shares representing each outcome |
| **Trading** | Dexie DEX (native offers) | Orderbook for buying/selling outcome tokens |
| **Resolution** | BLS signatures (AugSchemeMPL) | Oracle signs outcome, unlocking the locked XCH |

The oracle puzzle (`oracle_payout.rue`) enforces three conditions:
1. **AggSigMe** — Oracle must sign `market_id + outcome_byte`, bound to the specific coin
2. **AssertMyAmount** — Prevents amount manipulation
3. **CreateCoin** — Pays out to the specified receiver with the winning asset ID as memo

---

## Milestone 1: Oracle Puzzle Validation

**Objective:** Deploy a custom Rue puzzle to mainnet and successfully spend it with an oracle signature.

### Round 1 (Failed)
- Compiled `oracle_payout.rue`, curried with test parameters, sent 1000 mojos to the puzzle address
- **Failure:** The puzzle source was modified after coin creation (AggSigPuzzle → AggSigMe), and the original curried CLVM was not saved. The puzzle reveal could not be reconstructed, making the coin unspendable.
- **Lesson:** Always persist the curried CLVM at coin creation time.
- **Loss:** 1000 mojos (dust) at address `xch1fs4l8kqavx4wxv9unx7qy0dfqau5dzzhjn235eglyqwv6q897ans6uns6s`

### Round 2 (Success ✅)
- Compiled current puzzle (AggSigMe, opcode 50), curried, verified hash round-trip
- Saved complete state including `curried_clvm` and `curried_hex`
- Sent 1000 mojos via Sage wallet to the puzzle address
- Built spend bundle, validated locally with `cdv inspect spendbundles -db`
- Signed with BLS AugSchemeMPL: `message = oracle_msg + coin_id + genesis_challenge`
- Submitted via FireAcademy `push_tx` → **SUCCESS**

| Field | Value |
|-------|-------|
| Puzzle Hash | `80f2930520e4054d2a1cae7e54d2a9f22bf4bc5a0f9e339ae16c735c2a7d6379` |
| Address | `xch1srefxpfqusz562su4el9f54f7g4lf0z6p70r8xhpd3e4c2navdus6hfk6s` |
| Coin ID | `94e673e6008ebf678c29a931c52136e0ec708132c0583cee9c166572d8c14527` |
| Spend Height | 8,297,365 |
| Oracle | DracattusDev (fp: 1631380421) |
| Outcome | YES (1) |

**Verify:** [spacescan.io/address/xch1srefxpfqusz562su4el9f54f7g4lf0z6p70r8xhpd3e4c2navdus6hfk6s](https://spacescan.io/address/xch1srefxpfqusz562su4el9f54f7g4lf0z6p70r8xhpd3e4c2navdus6hfk6s)

### Stress Test: 120 XCH Recovery
During testing, 120 XCH was accidentally sent to the Round 2 puzzle address. The oracle resolution mechanism was used to recover the full amount, demonstrating the puzzle works correctly at scale.

| Field | Value |
|-------|-------|
| Coin ID | `4635baa3de6f2865094928d856450aac9446f457f07fb3f23145583b74aa362f` |
| Amount | 120,000,000,000,000 mojos (120 XCH) |
| Spend Height | 8,297,579 |
| Recovery | Full — returned to origin wallet |

**Verify:** [spacescan.io/coin/0x4635baa3de6f2865094928d856450aac9446f457f07fb3f23145583b74aa362f](https://spacescan.io/coin/0x4635baa3de6f2865094928d856450aac9446f457f07fb3f23145583b74aa362f)

---

## Milestone 2: CAT Issuance

**Objective:** Mint YES and NO tokens as XCH Asset Tokens for two markets.

### Market Infrastructure Tokens (Round 2 Test)

| Token | Asset ID | Supply | Dexie |
|-------|----------|--------|-------|
| XCH Predict YES | `188d646318b48fdb7290819a5977a4d45913e5a4dd19cf78b9237630b5cb3232` | 1,000,000 | [Offer](https://dexie.space/offers/CigwAme4oXF8hwcyN9KRu9EVi3Pxvciw95BCzNC56XR) |
| XCH Predict NO | `bc9c5480a4d0d5220989c8ce5001b7747074dda522423a454d7e05a546bbc8e1` | 1,000,000 | [Offer](https://dexie.space/offers/PKTqBnMS6xuskbejx5bS5Xrs6sn2pLepXuKkB78H3zA) |

### "Will ETH flip BTC market cap by 2027?" Market Tokens

| Token | Asset ID | Supply | Dexie |
|-------|----------|--------|-------|
| YES | `19c5da823b815bdc1da91518922dec6fd41f88d7d5aad8d53fd429ce9d42db80` | 100,000 | [Offer](https://dexie.space/offers/4GNR5FHQqfkPJCumJGHG5LSYHjUdz3zqCASLmzat9X8A) |
| NO | `17e4ca5cb8c5df36faf2de120ebef79295dff415ebd118d60f257284d9e93685` | 100,000 | [Offer](https://dexie.space/offers/J2K1FTcem6mPHH5aYqHB3V7PQnzS4sAXwp4huAaCv8Hr) |

**Verify YES:** [spacescan.io/cat/19c5da823b815bdc1da91518922dec6fd41f88d7d5aad8d53fd429ce9d42db80](https://spacescan.io/cat/19c5da823b815bdc1da91518922dec6fd41f88d7d5aad8d53fd429ce9d42db80)
**Verify NO:** [spacescan.io/cat/17e4ca5cb8c5df36faf2de120ebef79295dff415ebd118d60f257284d9e93685](https://spacescan.io/cat/17e4ca5cb8c5df36faf2de120ebef79295dff415ebd118d60f257284d9e93685)

---

## Milestone 3: Full Market Lifecycle

**Objective:** Create a market, fund the oracle puzzle, list tokens for trading on Dexie, and resolve the market — all on mainnet.

### Market: "Will ETH flip BTC market cap by 2027?"

**Creation:**
- Market ID: `6f1fd0121504f874c5f3e54907b3968c8dd2e4e24ca6b19eaa0e2804e2e2b82b`
- Oracle puzzle compiled from `oracle_payout.rue`, curried with oracle key + YES/NO asset IDs + market ID
- Puzzle hash verified round-trip (serialize → deserialize → treehash matches)
- YES and NO CATs minted via Sage wallet RPC
- Both tokens listed on Dexie DEX

| Field | Value |
|-------|-------|
| Puzzle Hash | `950ded196d664ff1270fb84df3bd23e2397974a53df9e2fb048adb2f9de9cd2c` |
| Puzzle Address | `xch1j5x76xtdve8lzfc0hpxl80fruguhja998hu797cy3tdjl80fe5kq782uu7` |

**Funding:**
- 1000 mojos sent to puzzle address via Sage RPC
- Confirmed at block height 8,297,692

**Resolution:**
- Outcome: **YES**
- CLVM execution verified locally (correct conditions emitted)
- BLS signature verified locally before submission
- Spend bundle validated with `cdv inspect spendbundles -db`
- Submitted to FireAcademy `push_tx` → `{"status": "SUCCESS", "success": true}`
- Payout delivered to oracle wallet

**Verify:** [spacescan.io/address/xch1j5x76xtdve8lzfc0hpxl80fruguhja998hu797cy3tdjl80fe5kq782uu7](https://spacescan.io/address/xch1j5x76xtdve8lzfc0hpxl80fruguhja998hu797cy3tdjl80fe5kq782uu7)

---

## Tools & Scripts

| Script | Purpose |
|--------|---------|
| `puzzles/oracle_payout.rue` | Oracle payout puzzle (Rue source) |
| `scripts/create_market_v2.py` | One-command market creation (CATs + puzzle + Dexie) |
| `scripts/resolve_market.py` | One-command market resolution (sign + validate + submit) |
| `scripts/clean_e2e_test.py` | Step-by-step E2E test harness |

---

## Technical Lessons

1. **Always save curried CLVM.** The Rue compiler output can change between versions. If you don't save the exact curried CLVM at coin creation time, the coin becomes unspendable.

2. **Use AggSigMe (opcode 50), not AggSigPuzzle (44).** AggSigMe binds the signature to the specific coin (message includes coin_id + genesis_challenge), preventing replay attacks across coins.

3. **Validate before submitting.** `cdv inspect spendbundles -db` catches errors locally. Transactions that fail on-chain are silently dropped with no error message.

4. **Sage CLI version must match the GUI app.** A version mismatch causes "error decoding response body" on every RPC call. Install from the same git tag as the app version.

5. **FireAcademy `push_tx` is reliable.** `https://kraken.fireacademy.io/leaflet/push_tx` returns clear success/failure. Sage's `submit_transaction` returns `{}` for both success and failure.

---

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| Oracle Puzzle | ✅ Complete | Custom Rue puzzle, mainnet validated |
| CAT Issuance | ✅ Complete | YES/NO token minting via Sage |
| Dexie Trading | ✅ Complete | Offers listed and tradeable |
| Market Resolution | ✅ Complete | Oracle-signed payout on mainnet |
| OpenClaw Skill | ✅ Complete | Chat-based market management |
| Timeout/Refund | 🔲 Planned | AssertHeightRelative for abandoned markets |
| Trustless Resolution | 🔲 Planned | Custom Chialisp for multi-oracle consensus |
| Frontend | 🔲 Planned | Next.js market browser with WalletConnect |
| Public Launch | 🔲 Planned | Open-source release + community review |

---

## Conclusion

XCH Predict demonstrates that prediction markets are viable on the XCH blockchain using native primitives: Rue puzzles for trustless escrow, CATs for outcome tokens, and Dexie for decentralized trading. The complete lifecycle — from market creation to resolution — has been validated on mainnet with real transactions.

The protocol uses a single custom puzzle, standard CAT issuance, and existing DEX infrastructure. No modifications to the XCH protocol are required. The entire system can be operated from the command line or via OpenClaw chat commands.

All transactions referenced in this document can be independently verified on [spacescan.io](https://spacescan.io).

---

*XCH Predict is open-source protocol tooling. It is not a platform, exchange, or financial service.*
