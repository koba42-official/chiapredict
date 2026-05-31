# XCHPredict Protocol Specification

## Overview

XCHPredict enables trustless binary prediction markets on the XCH blockchain. Markets resolve to YES or NO, with token holders of the winning outcome redeeming XCH.

## Actors

- **Creator**: Creates the market, locks XCH, mints tokens
- **Oracle**: Signs the outcome when the event resolves (initially = creator)
- **Traders**: Buy/sell YES and NO tokens via offers
- **Winners**: Redeem winning tokens for XCH

## Market Lifecycle

### 1. Market Creation

Creator performs the following atomic sequence:

```
a) Generate unique market_id (sha256 of question + timestamp + creator pubkey)
b) Mint N YES CATs (standard single-issuance TAIL)
c) Mint N NO CATs (standard single-issuance TAIL)  
d) Lock N × redemption_value XCH into oracle_payout puzzle coins
e) List initial YES/NO offers on Dexie
```

The oracle_payout puzzle is curried with:
- `oracle_pubkey` — who can resolve
- `yes_asset_id` — the YES CAT's asset ID
- `no_asset_id` — the NO CAT's asset ID
- `market_id` — unique market identifier

**Token Economics:**
- Each YES + NO pair is backed by 1 unit of locked XCH
- If 100 pairs exist, 100 XCH is locked
- YES + NO always sum to the locked amount

### 2. Trading

Standard XCH offer flow:
- Traders create offers: "I'll give 0.3 XCH for 1 YES token"
- Offers posted to Dexie for aggregation
- Any wallet can take offers (Sage, Goby, etc.)
- Offers are atomic — no counterparty risk during trade

Market price of YES ≈ probability market assigns to YES outcome.

### 3. Resolution

When the event outcome is known:

```
a) Oracle signs message: sha256(market_id + outcome_byte)
b) outcome_byte: 0x01 for YES, 0x00 for NO
c) Signature published (on-chain memo, off-chain channel, or both)
```

One signature resolves all payout coins for the entire market.

### 4. Redemption

Winning token holders redeem by spending oracle_payout coins:

```
a) Provide: oracle signature, outcome, receiver puzzle hash, amount
b) Puzzle verifies: signature matches oracle_pubkey + market_id + outcome
c) XCH released to receiver_puzzle_hash
```

**Losing tokens:** Become worthless. No redemption path. Can be melted for 1000 mojo dust.

## Security Considerations

### Oracle Trust
- Phase 1: Single trusted oracle (market creator)
- Phase 2: Multi-sig oracle (M-of-N community members)
- Phase 3: Decentralized oracle with staking/slashing

### Replay Prevention
- `market_id` is unique per market, curried into puzzle
- `AggSigPuzzle` binds signature to puzzle hash (not reusable across puzzles)

### Timeout / Abandonment
- If oracle never resolves, funds are locked forever
- Mitigation: Add timeout condition (AssertHeightRelative) that returns funds to creator
- This is a Phase 2 enhancement

### Front-running
- XCH has no public mempool — offers are either taken or not
- No MEV / sandwich attack vector
- Significant advantage over EVM prediction markets

## Data Model

### Market
```json
{
  "market_id": "bytes32",
  "question": "string",
  "creator": "puzzle_hash",
  "oracle_pubkey": "public_key",
  "yes_asset_id": "bytes32",
  "no_asset_id": "bytes32",
  "total_supply": "int",
  "resolution_height": "int (optional deadline)",
  "status": "open | resolved_yes | resolved_no",
  "created_at": "timestamp"
}
```

### Payout Coin
```json
{
  "coin_id": "bytes32",
  "puzzle_hash": "bytes32 (oracle_payout curried hash)",
  "amount": "int (mojos)",
  "market_id": "bytes32"
}
```

## Fee Structure (Future)

- Market creation: small XCH fee to prevent spam
- Trading: standard XCH transaction fees only
- Resolution: oracle pays fee to spend resolution tx
- Redemption: winner pays fee to claim

## Dexie Integration

YES/NO CATs appear as standard CATs on Dexie. No special integration needed.
Dexie API used for:
- Listing order books
- Posting offers
- Price discovery
- Market making bots
