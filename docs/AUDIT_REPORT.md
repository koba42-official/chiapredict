# XCHPredict Production Readiness Audit

**Date:** 2026-02-10
**Auditor:** OpenClaw automated audit
**Scope:** All scripts, puzzles, frontend, docs, market states, skill config

---

## Executive Summary

XCHPredict is a working proof-of-concept that has successfully completed end-to-end mainnet tests. The core puzzle logic is sound. However, it is **nowhere near production-ready**. The project has critical security gaps, no offer invalidation, no automated redemption flow, a static frontend with zero markets rendered, and several scripts that leak secret keys into memory. The protocol's biggest risk is **locked funds with no recovery path** (v1 puzzles) and **stale offers that can't be cancelled on-chain**.

**Verdict: Alpha/prototype. Not safe for real money beyond dust-level testing.**

---

## A. Script Issues

### create_market_v2.py

**What it does:** Full market creation — mints YES/NO CATs, compiles & curries puzzle, posts Dexie offers, saves state.

**Bugs & Issues:**
1. **Hardcoded paths everywhere:**
   - `PROJECT_DIR = "/Users/alphanerd/Dev/chia-predict"`
   - `RUE_BIN = "/Users/alphanerd/Dev/rue-lang/target/release/rue"`
   - These must be env vars or config-file driven.

2. **No offer cancellation on failure.** If YES offer succeeds but NO offer fails, the market is in a broken state with only one side listed. No rollback logic.

3. **Fee always 0.** On a congested network, transactions will be deprioritized or stuck. No `--fee` CLI option for the inner transactions (CAT issuance, offers).

4. **`offer_price` semantics are confusing.** The arg is "XCH mojos per 1000 tokens" but the help text says "per 1000 tokens (500 = 50%)". The actual math: `xch_amount = offer_qty * offer_price // 1000`. This means 500 mojos per 1000 tokens = 0.5 mojo per token. This is dust-level pricing, not 50% of anything meaningful. The economic model is broken — there's no clear relationship between token price and XCH backing.

5. **`market_id` is just `sha256(question)`.** Two markets with the same question text will collide and overwrite each other's directory. The PROTOCOL.md says it should include timestamp + creator pubkey. **This is a bug.**

6. **No duplicate market detection.** If you run the script twice with the same question, it will mint new CATs but save to the same directory, corrupting state.

7. **FORBIDDEN_FPS only checked at start,** but `login_and_wait` also checks. Redundant but harmless.

8. **`wait_for_cat` polls every 10s for up to 240s.** If the network is slow, this silently proceeds with an unconfirmed NO CAT, which could cause issues.

9. **No atomic creation.** CAT minting, puzzle deployment, and offer creation are separate transactions. If the script crashes mid-way, you have orphaned CATs with no puzzle or offers.

10. **`get_pending_transactions` RPC** — unclear if Sage actually supports this method. If it returns None, the `len(pending.get("transactions", []))` returns 0 and skips the wait. Silent failure.

### resolve_market.py

**What it does:** Oracle resolution — finds coins at puzzle address, signs outcome, submits spend bundle.

**Bugs & Issues:**
1. **Imports `blspy` at runtime** (`from blspy import ...` inside `main()`). If blspy isn't installed, the error is confusing.

2. **Secret key extracted via `sage_rpc("get_secret_key")`** — the master secret key is loaded into Python memory. This is the **entire wallet's master key**, not a derived key. If this script is run on a compromised machine, all funds across all addresses are at risk.

3. **No confirmation prompt.** Running `resolve_market.py markets/X --outcome yes` immediately resolves. A resolved market cannot be un-resolved. Should require `--confirm` flag or interactive prompt.

4. **Uses FireAcademy API** (`kraken.fireacademy.io`) with no API key. This is a free tier endpoint that may rate-limit or disappear.

5. **No fee support.** `push_tx` with no fee.

6. **Receiver defaults to `sync['receive_address']`** — this pulls whatever address Sage gives. If the wallet state is stale, this could be wrong.

7. **State updated to "resolved" even if submission fails.** If `push_tx` returns an error, the state is still written as `phase: "resolved"`. The script should only update state on confirmed success.

8. **Hardcoded FireAcademy URL.** No fallback, no retry.

9. **`compute_coin_id` handles amount=0** but the puzzle requires `my_amount > 0` (AssertMyAmount). Dead code, but not harmful.

### redeem_market.py

**What it does:** Posts Dexie offers to buy back winning CATs with XCH.

**Bugs & Issues:**
1. **This is NOT trustless redemption.** The script creates a standard Dexie offer (oracle wallet offers XCH, requests winning CATs). This means:
   - The oracle must have XCH to back redemption
   - Redemption is limited by the offer quantity
   - If the oracle doesn't post offers, winners can't redeem
   - **This completely undermines the "trustless" claim**

2. **The actual trustless redemption should work differently:** Winners should be able to spend the oracle_payout puzzle coins directly by presenting winning tokens. But the puzzle doesn't actually verify token ownership — it just pays out to any `receiver_puzzle_hash` with the oracle's signature. So the "redemption" is actually just the oracle deciding who to pay.

3. **Missing: batch redemption.** Only creates one offer at a time. For 1M token supply, you'd need 1000 offers of 1000 tokens each.

4. **`--price` default is 1 mojo per token.** The relationship between token value and locked XCH is undefined. What makes a token worth 1 mojo?

5. **No offer cancellation logic** when state changes.

### spend_puzzle.py

**What it does:** Earlier version of puzzle spending, uses spacescan API. Largely superseded by resolve_market.py.

**Issues:**
1. **Reads from `tests/mainnet_test_state.json`** — hardcoded test state path.
2. **Uses spacescan API** which returns different formats than expected (multiple URL attempts).
3. **Signing via `sage rpc sign_coin_spends`** but the puzzle needs a manual BLS signature, not Sage's standard signing. This script likely doesn't work correctly for the oracle puzzle.
4. **Dead code / test artifact.** Should be archived or deleted.

### debug_spend.py

**What it does:** Debug tool for manually constructing and submitting spend bundles with hardcoded values.

**Issues:**
1. **ORACLE SECRET KEY HARDCODED IN SOURCE:**
   ```python
   ORACLE_SK = "<REDACTED_SET_VIA_ENV_ONLY>"
   ```
   **THIS IS A CRITICAL SECURITY ISSUE.** If this repo is ever pushed to a public GitHub, the oracle key is compromised. Even in a private repo, this is unacceptable.

2. **All values hardcoded** — parent ID, puzzle hash, amount, receiver. This is a one-shot debug tool, not reusable.

3. **Should be in a `tests/` or `debug/` directory**, not `scripts/`.

### clean_e2e_test.py

**What it does:** Phased E2E test — compile, send, find coin, spend. Better structured than the original e2e test.

**Issues:**
1. **Uses fake asset IDs** (`sha256(b"ROUND2_YES_TOKEN")`). These aren't real CATs, so the puzzle's memo output is meaningless on-chain.
2. **Hardcoded key lookup by name** (`"DracattusDev"`). Fragile.
3. **State directory: `tests/round2/`** — hardcoded.
4. **Good for testing, bad that it's in `scripts/`** — should be in `tests/`.

### e2e_mainnet_test.py

**What it does:** Original E2E test, simpler version. Sends dust to puzzle, prints instructions for manual spending.

**Issues:**
1. **Doesn't complete the spend** — just sends XCH and tells you to run spend_puzzle.py.
2. **`market_id` includes `time.time()`** — non-deterministic, can't reproduce.
3. **Test artifact.** Should be in `tests/`.

---

## B. Frontend Gaps

### frontend/index.html

**What it does:** Beautiful single-page marketing site with market cards, animated background, Dexie price fetching.

**Critical Gaps:**

1. **MARKETS array is empty.** `const MARKETS = [];` — the page renders zero markets. Markets must be manually added to the JS array. There's no API, no backend, no dynamic data source.

2. **No wallet integration.** Users can't:
   - Connect a wallet (Sage, Goby)
   - Create markets
   - Place bets directly
   - View their positions
   - Redeem winnings

3. **No market creation UI.** Everything is CLI-only.

4. **Dexie price fetching is broken for the actual offer format.** The code assumes offers have `asset_id === 'xch'` for XCH entries and `asset_id === market.yesAsset` for tokens. Dexie's actual API format may differ. The CORS-safe fetch with `AbortSignal.timeout(5000)` will silently fail and show a fallback link.

5. **GitHub link goes to `https://github.com`** (generic), not the actual repo.

6. **Hero stats are all hardcoded zeros:** `0 Active Markets`, `0 Tokens Minted`, `$0 Fees`.

7. **Mobile menu toggle** opens nothing — `this.nextElementSibling?.classList.toggle('show')` but there's no `.show` CSS class and no mobile menu element.

8. **No SEO content.** Meta description is good but there's no structured data, no OpenGraph tags for social sharing.

9. **"Next.js" mentioned in README** but frontend is a single static HTML file. Architecture diagram is misleading.

10. **No market detail pages.** Everything is a flat list.

---

## C. Protocol Gaps

### Fundamental Design Issue: Not Actually Trustless

The protocol claims to be "trustless" but has a **critical trust assumption:**

1. **Oracle is fully trusted.** The oracle can:
   - Resolve any outcome they want (correct or not)
   - Never resolve (locking funds forever in v1)
   - Resolve and direct payout to themselves
   - There's no slashing, no multi-sig, no dispute mechanism

2. **Redemption requires oracle cooperation.** The redeem_market.py script has the oracle posting buyback offers. If the oracle disappears, winners can't redeem.

3. **The puzzle pays to any `receiver_puzzle_hash`** — it doesn't verify that the receiver holds winning tokens. Anyone who can construct the spend with the oracle's signature gets the funds. The "token holder redeems" flow is an off-chain social convention, not an on-chain guarantee.

### Missing Protocol States

- **No "cancelled" state.** Markets can't be cancelled before resolution.
- **No "disputed" state.** No mechanism for challenging oracle decisions.
- **No "expired" state** for v1 puzzles (funds locked forever).
- **No "partially redeemed" state.** No tracking of how much has been redeemed.

### Edge Cases Not Handled

1. **Multiple coins at same puzzle address.** resolve_market.py handles this (iterates coins), but what if some spends succeed and others fail? Partial resolution state.

2. **Race condition: oracle resolves while offers are being taken.** If someone takes a Dexie offer for YES tokens after the market resolves to NO, they've bought worthless tokens. No circuit breaker.

3. **Token supply vs locked XCH mismatch.** Nothing enforces that the XCH locked in the puzzle equals the token supply × redemption value. The puzzle accepts any amount of XCH. Tokens could be worth less than expected.

4. **CAT single-issuance TAIL means supply is fixed.** But the protocol doesn't verify total supply against locked XCH. If 1M tokens exist but only 1000 mojos are locked, each token is worth 0.001 mojos.

### Timeout (v2) Issues

1. **Timeout refund goes to `receiver_puzzle_hash`** — anyone can claim after timeout. There's no restriction that only the original funder gets the refund. First-to-spend wins.

2. **`timeout_height` is absolute block height**, not relative. If the current block is 8.3M, a timeout of 100000 means it expired ~8M blocks ago. The create_market_v2.py should compute `current_height + timeout_blocks` but it passes `timeout_blocks` directly as the timeout_height to curry. **This is a bug** — unless the user is expected to pass absolute heights, which the `--timeout-blocks` flag name contradicts.

   Wait — looking more carefully at the curry call:
   ```python
   f"-a {args.timeout_blocks}"
   ```
   And the puzzle uses `AssertHeightAbsolute { height: timeout_height }`. So if you pass `--timeout-blocks 100000`, the puzzle will be claimable by anyone once block 100000 is reached, which happened years ago. **This is a critical bug.** The script should compute `current_block_height + timeout_blocks` and curry that absolute value.

---

## D. Security Concerns

### 1. Secret Key Exposure

- **debug_spend.py** has the oracle secret key hardcoded in plaintext.
- **resolve_market.py** calls `get_secret_key` and loads the master SK into Python memory.
- **clean_e2e_test.py** also calls `get_secret_key`.
- If any of these scripts are run in a logged environment (terminal history, crash dumps), the key is exposed.

### 2. Mom Wallet Protection

- `FORBIDDEN_FPS = [1849776284]` is checked in `create_market_v2.py` only.
- `resolve_market.py` has **no FORBIDDEN_FPS check**. If a market's `state.json` is manually edited to point to mom's fingerprint, resolve would attempt to use it.
- `redeem_market.py` has **no FORBIDDEN_FPS check** either.
- `spend_puzzle.py`, `debug_spend.py`, `clean_e2e_test.py` — **none have protection**.

### 3. Offer Invalidation (Known Issue: Confirmed)

- **`delete_offer` vs `cancel_offers`:** The Sage wallet's `delete_offer` only removes the offer locally. The offer file is still valid on Dexie and can be taken by anyone. To on-chain invalidate, you must spend one of the coins in the offer, which `cancel_offers` (if it exists) should do.
- **Current scripts never cancel offers.** When a market is resolved, old trading offers remain live on Dexie. Someone could buy worthless tokens from a stale offer after resolution.
- **BAD_AGGREGATE_SIGNATURE from stale offers:** If coins used in an offer get spent (e.g., during resolution), the offer becomes invalid and any attempt to take it will fail with BAD_AGGREGATE_SIGNATURE. This is actually a safety mechanism, but it means stale offers pollute Dexie.

### 4. Sage Coin Locking (Known Issue: Confirmed)

- When Sage creates an offer, it "locks" the coins involved. If another transaction tries to use the same coins, it will fail.
- The script waits for pending transactions to clear before creating offers (good), but if the script crashes between creating YES and NO offers, the YES offer coins are locked and the wallet state may be inconsistent.
- No cleanup/recovery mechanism for locked coins.

### 5. Single Point of Failure

- One oracle key controls all markets.
- One wallet (`DracattusDev`, fp:1631380421) is used for everything.
- No key rotation, no backup oracle, no multi-sig.

### 6. State File Integrity

- State is saved as plain JSON with no checksums, no encryption.
- If state.json is corrupted or tampered with, resolution could send funds to wrong address.
- No backup of state files.

### 7. API Dependencies

- FireAcademy (`kraken.fireacademy.io`) — free tier, no SLA, could disappear.
- Dexie (`dexie.space/v1/offers`) — single DEX dependency.
- Spacescan — used in some scripts for coin lookup.
- No fallback for any of these.

---

## E. Market State Issues

### Market `a140ffcf9d403d60` (XCH $50)

- **Different oracle pubkey** than all other markets: `873e20f5c3df5e3be45...` vs `873e20f535b03c2de01...`. Same fingerprint (1631380421) but different pubkey. This suggests it was created during a different session or with a different derivation. **Resolution will fail** if the wrong key is used.
- **YES and NO CATs minted from different wallets** (YES from 1631380421, NO from 861103475). Not inherently broken but unusual.
- **Missing `puzzle_version` field** in state. Will default to v1 behavior.
- **Missing `name` field** in oracle config.
- **NO offer has empty `offer_id`**: `"offer_id": ""`. Something went wrong during offer creation.

### Market `336c36c5cb17066c` (Moncton temperature)

- **Missing `puzzle_version` field.**
- **Missing `timeout_blocks` field.**
- **Only YES offer posted**, no NO offer. Incomplete market.
- **Missing `mint_wallet` field.**
- **v1 puzzle (no timeout) for a weather question** that has a clear expiry date. If it's never resolved, funds are locked forever.

### Market `6f1fd0121504f874` (ETH flips BTC)

- **Resolved as YES** — but ETH has not flipped BTC. This was likely a test resolution, but the state says "resolved" with no indication it was a test.
- **Only YES offer ever posted.** No NO side trading existed.
- **No redemption data.** Phase is "resolved" but no `redemption` field. Winners can't redeem.

### Market `a528edb12acc9054` (Self-referential test)

- Resolved as YES. Only YES offer posted. Test market, looks OK.

### Market `03c04bf46309930f` (Test resolve YES)

- Active, both offers posted. Supply only 1000 (tiny). Minted from different wallet (861103475) than oracle.

### Market `5949264ef9471137` (BTC 150k)

- **v2 puzzle with `timeout_blocks: 100000`.** As discussed in Protocol Gaps, this means the timeout_height is block 100,000 — **already passed years ago**. Anyone can claim the funds RIGHT NOW by submitting a timeout refund spend. **Critical bug if any XCH is locked in this puzzle.**

---

## F. Production Checklist

Ordered by priority (blocking → important → nice-to-have):

### 🔴 CRITICAL (Blocking)

1. **Remove hardcoded secret key from debug_spend.py** — delete or redact immediately
2. **Fix timeout_blocks bug in create_market_v2.py** — must compute `current_height + timeout_blocks` for v2 puzzles
3. **Check market `5949264ef9471137`** — if funded, the XCH is claimable by anyone via timeout refund right now
4. **Add FORBIDDEN_FPS checks to ALL scripts** (resolve, redeem, spend_puzzle, debug_spend, test scripts)
5. **Implement offer cancellation on market resolution** — spend the coins to invalidate Dexie offers
6. **Don't update state to "resolved" unless tx is confirmed** — resolve_market.py writes state before knowing if push_tx succeeded

### 🟠 HIGH (Before any real money)

7. **Fix market_id generation** — include timestamp + creator pubkey to prevent collisions (as PROTOCOL.md specifies)
8. **Externalize all hardcoded paths** — use env vars, config file, or `__file__`-relative paths
9. **Add confirmation prompts** for destructive actions (resolve, fund)
10. **Implement proper secret key handling** — derive signing keys rather than extracting master SK; use secure memory; zero after use
11. **Add fee support** to all transaction-creating scripts
12. **Design actual trustless redemption** — the current model requires oracle to post buyback offers, which is trust-based. Real trustless = puzzle verifies token burn
13. **Add retry logic and fallback APIs** for FireAcademy, Dexie
14. **Verify oracle pubkey consistency** — market `a140ffcf` has a different pubkey, needs investigation

### 🟡 MEDIUM (Before public beta)

15. **Build actual backend/API** for frontend — markets should be loaded from chain state or a database, not hardcoded JS
16. **Implement wallet connection** in frontend (WalletConnect, Goby, Sage)
17. **Add market creation UI**
18. **Implement multi-sig oracle support** (Phase 2 in protocol spec)
19. **Add state file backups** — at minimum, git-commit state changes
20. **Move test scripts to `tests/` directory**
21. **Add proper logging** instead of print statements
22. **Implement market expiry/deadline** as a first-class concept
23. **Cancel stale Dexie offers** when creating new ones or resolving
24. **Add `--dry-run` flag** to all scripts

### 🟢 LOW (Production polish)

25. **Add market discovery** — list markets from on-chain data, not local state files
26. **Implement market making bot** for maintaining liquidity
27. **Add dispute resolution mechanism**
28. **OpenGraph meta tags** for social sharing
29. **Progressive web app** support
30. **Rate limiting and abuse prevention** for market creation
31. **Fix mobile menu** in frontend
32. **Update README** — architecture diagram says "Next.js" but frontend is static HTML
33. **Add monitoring/alerting** for funded puzzles
34. **Legal disclaimer** on frontend

---

## G. Summary Table

| Component | Status | Risk Level |
|-----------|--------|------------|
| oracle_payout.rue (v1) | ✅ Working, tested on mainnet | 🟡 No timeout = funds locked if oracle disappears |
| oracle_payout_v2.rue | ✅ Logic correct | 🔴 Timeout currying bug makes it exploitable |
| create_market_v2.py | ⚠️ Functional but fragile | 🟠 No atomicity, hardcoded paths, collision risk |
| resolve_market.py | ⚠️ Works for happy path | 🔴 No forbidden wallet check, state written prematurely |
| redeem_market.py | ❌ Not trustless | 🔴 Fundamentally trust-based design |
| spend_puzzle.py | 🗑️ Superseded | 🟡 Should be archived |
| debug_spend.py | 🗑️ Contains secret key | 🔴 **Secret key in source code** |
| clean_e2e_test.py | ✅ Good test | 🟡 Should be in tests/ |
| e2e_mainnet_test.py | ✅ Good test | 🟡 Should be in tests/ |
| frontend/index.html | ⚠️ Pretty but empty | 🟠 Zero functionality, zero markets |
| Market states | ⚠️ Mixed quality | 🔴 One market may be exploitable via timeout |

---

## H. Conclusion

The project demonstrates genuine understanding of XCH CLVM, BLS signatures, CATs, and offer mechanics. The core puzzle works. But the gap between "working prototype" and "production prediction market" is enormous.

The three most urgent items:
1. **Secret key in debug_spend.py** — remove NOW
2. **Timeout bug** — check if market `5949264e` is funded; if so, funds are at immediate risk
3. **Redemption design** — the entire economic model needs rethinking; the current approach is trust-based, not trustless

The project needs a fundamental architectural decision: is this a centralized prediction market run by a trusted oracle (fine, but don't call it trustless), or a truly trustless protocol (requires token-burn verification in the puzzle, multi-sig oracles, and on-chain dispute resolution)?

Be honest about what this is: a clever prototype. Ship it as that, iterate toward trustless.
