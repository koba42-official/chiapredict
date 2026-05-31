# XCH Predict — Prediction Markets on XCH

![XCH Predict Logo](docs/assets/xchpredict-logo.jpg)

Trustless prediction markets built on the XCH blockchain using Rue smart contracts, CAT tokens, and Dexie DEX.

**Status: Phase 1 Complete — Full E2E lifecycle proven on mainnet ✅**

🌐 **Live**: [xchpredict.dracattus.com](https://xchpredict.dracattus.com)
📦 **Source**: [git.dracattus.com/dracattus/chia-predict](https://git.dracattus.com/dracattus/chia-predict)

---

## How It Works

1. **Create** — Market creator defines a question, mints YES/NO CAT tokens, locks XCH in a Rue puzzle
2. **Trade** — YES/NO tokens listed on [Dexie](https://dexie.space) for peer-to-peer trading
3. **Resolve** — Oracle signs the outcome using BLS signatures; puzzle validates and releases funds
4. **Redeem** — Winners exchange tokens for XCH via Dexie buyback offers

## What's Been Proven on Mainnet

- ✅ Rue puzzle compilation, currying, and deployment
- ✅ BLS AggSigMe oracle signing and validation
- ✅ YES/NO CAT minting (standard single-issuance TAIL)
- ✅ Dexie offer creation, listing, and acceptance
- ✅ Oracle resolution spend (puzzle → XCH to receiver)
- ✅ v2 timeout puzzle (AssertHeightAbsolute refund path)
- ✅ Market creation automation (end-to-end script)
- ✅ Offer cancellation (on-chain invalidation)
- ✅ Multi-wallet minting (oracle ≠ minter)

## Architecture

```
┌─────────────────────────────────────────────┐
│           Frontend (Static HTML)             │
│   Market viewer, economics, how-it-works     │
├─────────────────────────────────────────────┤
│           Python CLI Scripts                 │
│   create_market · resolve · redeem           │
├──────────┬──────────┬───────────────────────┤
│ Sage     │ Dexie    │ FireAcademy /          │
│ Wallet   │ DEX API  │ Spacescan APIs         │
├──────────┴──────────┴───────────────────────┤
│              XCH Blockchain                  │
│  ┌────────────┐  ┌──────────┐  ┌─────────┐ │
│  │ Oracle      │  │ YES/NO   │  │ Offer   │ │
│  │ Payout      │  │ CATs     │  │ Files   │ │
│  │ Puzzle (Rue)│  │ (std)    │  │ (native)│ │
│  └────────────┘  └──────────┘  └─────────┘ │
└─────────────────────────────────────────────┘
```

## Project Structure

```
chia-predict/
├── puzzles/
│   ├── oracle_payout.rue       # v1 puzzle — oracle resolution only
│   └── oracle_payout_v2.rue    # v2 puzzle — oracle resolution + timeout refund
├── scripts/
│   ├── create_market_v2.py     # Full market creation (mint, compile, fund, offer)
│   ├── resolve_market.py       # Oracle resolution with on-chain confirmation
│   └── redeem_market.py        # Post buyback offers for winners
├── tests/
│   ├── clean_e2e_test.py       # Clean E2E test (compile → fund → spend)
│   ├── debug_spend.py          # Manual spend bundle debugging
│   └── e2e_mainnet_test.py     # Original mainnet test
├── markets/                    # Market state (one dir per market)
│   └── {market_id}/state.json  # Full state: CATs, puzzle, offers, resolution
├── frontend/
│   └── index.html              # Production frontend (deployed)
├── docs/
│   ├── PROTOCOL.md             # Protocol specification
│   ├── AUDIT_REPORT.md         # Production readiness audit
│   └── SCRIPT_CHANGES.md       # Script hardening changelog
└── .venv/                      # Python 3.12 + chia-dev-tools + blspy
```

## Puzzles

### v1 — Oracle Payout (`oracle_payout.rue`)
- Curried params: `oracle_pubkey`, `yes_asset_id`, `no_asset_id`, `market_id`
- Solution: `outcome` (0=NO, 1=YES), `receiver_puzzle_hash`, `my_amount`
- Oracle signs via **AggSigMe** (opcode 50) with outcome byte appended
- Outputs: AssertMyAmount + CreateCoin to receiver with CAT memo

### v2 — Oracle Payout with Timeout (`oracle_payout_v2.rue`)
- Additional curried param: `timeout_height` (absolute block height)
- Solution adds `mode` param: 0=oracle resolution, 1=timeout refund
- Timeout path uses `AssertHeightAbsolute` — anyone can claim after timeout
- 3/3 tests passing

## Scripts

All scripts are production-hardened with:
- **FORBIDDEN_FPS** guard (wallet `1849776284` is protected in every script)
- **Confirmation prompts** for destructive actions (`--yes` to skip)
- **Fee support** (`--fee` flag, default 0)
- **On-chain state confirmation** (state updated only after tx confirms)
- **Offer cancellation** on resolution (spends coins to invalidate Dexie offers)
- **Relative paths** (no hardcoded user directories)

### Create a Market
```bash
RUE_BIN=/path/to/rue python3 scripts/create_market_v2.py \
  "Will XCH reach $50 by June 2026?" \
  --oracle-fp 1631380421 \
  --mint-fp 861103475 \
  --supply 1000000 \
  --offer-qty 100000 \
  --offer-price 550 \
  --fund-amount 100000 \
  --timeout-blocks 100000 \
  --fee 0
```

### Resolve a Market
```bash
python3 scripts/resolve_market.py markets/{market_id} --outcome yes --yes
```

### Post Buyback Offers
```bash
python3 scripts/redeem_market.py markets/{market_id} --qty 100000 --price 1000 --yes
```

## Economics

XCH Predict uses a **spread-based revenue model**:

- YES + NO tokens priced so the pair costs more than the payout (e.g., 55 + 55 = 110 for 100 payout)
- The difference is the house edge (10-20% typical)
- No market creation fees (Phase 1)
- No resolution fees (Phase 1)
- Full transparency: all transactions verifiable on-chain

See the [Economics section](https://xchpredict.dracattus.com/#economics) on the website for detailed examples.

## Trust Model (Honest Assessment)

**Phase 1 (Current):** Single trusted oracle. The oracle can resolve any outcome and could theoretically delay resolution. The oracle **cannot** steal locked funds or change market terms post-creation. v2 puzzles include timeout refunds if the oracle disappears.

**Phase 2 (Planned):** Multi-signature oracle with M-of-N threshold. Community review and whitepaper.

**Phase 3 (Vision):** Decentralized oracle network with staking and slashing.

## Tech Stack

- **Smart Contracts:** [Rue](https://github.com/xch-dev/rue) → CLVM
- **Tokens:** Standard XCH CATs (single-issuance TAIL)
- **Trading:** XCH native offer files + [Dexie](https://dexie.space) aggregation
- **Wallet:** [Sage](https://github.com/xch-dev/sage) (CLI v0.12.2 + GUI)
- **Signing:** BLS signatures via blspy 2.0.3
- **Frontend:** Static HTML (dark theme, responsive, Dexie API integration)
- **Backend:** Python 3.12 scripts + chia-dev-tools 1.2.15
- **Broadcasting:** FireAcademy RPC (`kraken.fireacademy.io`)

## Development Setup

```bash
# 1. Build Rue compiler
git clone https://github.com/xch-dev/rue.git
cd rue && cargo build --release

# 2. Python environment (requires 3.12 — chia_rs won't build on 3.14)
python3.12 -m venv .venv
source .venv/bin/activate
pip install chia-dev-tools blspy

# 3. Install Sage CLI (must match GUI version)
cargo install sage-cli --git https://github.com/xch-dev/sage.git --tag v0.12.2

# 4. Set Rue binary path
export RUE_BIN=/path/to/rue-lang/target/release/rue

# 5. Compile and test puzzles
$RUE_BIN build puzzles/oracle_payout_v2.rue
$RUE_BIN test puzzles/oracle_payout_v2.rue
```

## Roadmap

- [x] Oracle payout puzzle v1 (Rue, AggSigMe)
- [x] Oracle payout puzzle v2 (timeout/refund via AssertHeightAbsolute)
- [x] Mainnet E2E test (compile → fund → sign → spend → confirmed)
- [x] CAT minting automation (YES/NO per market)
- [x] Market creation script (mint + compile + fund + list on Dexie)
- [x] Market resolution script (oracle sign + spend + state update)
- [x] Redemption script (Dexie buyback offers)
- [x] Dexie offer integration (live trading)
- [x] Production frontend (market viewer + economics + how-it-works)
- [x] Production audit + script hardening
- [x] OpenClaw skill for market management
- [ ] E2E buyer lifecycle test (buy → resolve → redeem)
- [ ] Whitepaper
- [ ] Multi-sig oracle (Phase 2)
- [ ] WalletConnect integration
- [ ] Market creation UI
- [ ] Leaderboard + user profiles
- [ ] Decentralized oracle (Phase 3)

## Active Markets

Visit [xchpredict.dracattus.com](https://xchpredict.dracattus.com) to see live markets with Dexie trading links.

## Legal

XCH Predict is open-source protocol tooling, not a centralized exchange:
- XCH-native only (no fiat on/off ramp)
- Peer-to-peer offer-based trading via Dexie (no central order book)
- No custody of user funds at any point
- All market state verifiable on-chain via Spacescan

## License

MIT
