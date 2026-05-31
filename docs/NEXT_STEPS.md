# XCHPredict — Next Steps

## Phase 1: Minimum Viable Market (2-3 weeks)

### 1.1 CAT Minting for YES/NO Tokens
- Use `sage rpc issue_cat` to mint paired YES and NO tokens
- Standard single-issuance TAIL (no custom TAIL needed)
- Each market gets unique YES and NO asset IDs
- Supply: 1 YES + 1 NO = 1 XCH backing

### 1.2 Atomic Market Creation
Script that does in one flow:
1. Generate market_id from question + timestamp + oracle key
2. Issue YES CATs (N tokens)
3. Issue NO CATs (N tokens)
4. Lock N × redemption_value XCH into oracle_payout puzzle coins
5. Save market state to local DB

### 1.3 Offer-Based Trading
- Create initial offers: YES at 0.5 XCH, NO at 0.5 XCH
- Post to Dexie via their API
- Users can take/create offers with any XCH wallet
- Monitor order book via Dexie API

### 1.4 Resolution + Redemption
- Oracle signs outcome → push spend bundle for each payout coin
- Batch resolution: one signature resolves all coins in a market
- Script to sweep all payout coins back to winners

### 1.5 OpenClaw Skill
```
"Create a market: Will XCH hit $50 by April?"
"Resolve market abc123: YES"  
"What markets are open?"
"Buy 5 YES tokens on market abc123"
```

## Phase 2: Web Frontend (2-3 weeks)

### 2.1 Market Browser
- List all open/resolved markets
- Show current YES/NO prices from Dexie order book
- Display market details, volume, time remaining

### 2.2 Trading UI
- Sage WalletConnect integration
- One-click buy YES/NO at market price
- Limit orders via offer creation
- Portfolio view (my positions)

### 2.3 Market Creation UI
- Form: question, resolution date, initial liquidity
- Preview of costs (XCH to lock + CAT minting)
- One-click deploy

### 2.4 Deployment
- Docker container on home server (alongside LCARS)
- Custom domain (predict.dracattus.com?)

## Phase 3: Advanced Features (1-2 months)

### 3.1 Timeout/Refund Mechanism
- Add `AssertHeightRelative` condition to puzzle
- If oracle doesn't resolve by deadline, funds return to creator
- Requires new puzzle version (oracle_payout_v2.rue)

### 3.2 Automated Market Making Bot
- OpenClaw skill that runs continuously
- Posts offers on both sides of every market
- Adjusts spread based on volume and time to resolution
- Rebalances inventory across markets

### 3.3 Multi-Sig Oracle
- M-of-N resolution (e.g., 3-of-5 community members)
- Aggregated BLS signatures
- Dispute period before finalization

### 3.4 Market Categories
- Sports, crypto prices, world events, community
- Tagging and search
- Featured/trending markets

## Phase 4: Ecosystem (3-6 months)

### 4.1 SDK / API
- npm package for market creation/resolution
- Python SDK
- REST API for market data

### 4.2 Community Oracle Network
- Staking mechanism for oracle reputation
- Slashing for incorrect resolution
- Reward for timely/accurate resolution

### 4.3 Cross-Market Composability
- Parlay bets (multiple outcomes)
- Conditional markets
- Market-linked CATs as collateral

## Priority Order

1. **CAT minting + market creation script** — makes it real
2. **Dexie integration** — enables trading
3. **OpenClaw skill** — makes it usable
4. **Web frontend** — makes it accessible
5. **Market making bot** — makes it liquid
6. **Timeout mechanism** — makes it safe
7. **Multi-sig oracle** — makes it trustless
