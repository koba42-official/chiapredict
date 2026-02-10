# ChiaPredict — Prediction Markets on Chia

Trustless prediction markets built on the Chia blockchain using Rue puzzles, CATs, and Dexie offers.

**Status: Oracle payout puzzle tested on mainnet ✅ (2026-02-10)**

## Architecture

```
┌─────────────────────────────────────────────┐
│              OpenClaw CLI / Chat             │
│         (create, bet, resolve, redeem)       │
├─────────────────────────────────────────────┤
│              Web Frontend (Next.js)          │
│      (market browser, order books, wallet)   │
├──────────┬──────────┬───────────────────────┤
│ Sage     │ Dexie    │  Spacescan            │
│ Wallet   │ DEX API  │  Explorer API         │
├──────────┴──────────┴───────────────────────┤
│              Chia Blockchain                  │
│  ┌────────────┐  ┌──────────┐  ┌─────────┐ │
│  │ Oracle      │  │ YES/NO   │  │ Offer   │ │
│  │ Payout      │  │ CATs     │  │ Files   │ │
│  │ Puzzle (Rue)│  │ (std)    │  │ (native)│ │
│  └────────────┘  └──────────┘  └─────────┘ │
└─────────────────────────────────────────────┘
```

## Proven on Mainnet

The oracle payout puzzle has been tested end-to-end on Chia mainnet:

1. **Compiled** Rue puzzle → CLVM bytecode
2. **Curried** with oracle pubkey, market ID, YES/NO asset IDs
3. **Locked** 1000 mojos into custom puzzle (block 8,296,978)
4. **Oracle signed** outcome (YES wins) using BLS AggSigMe
5. **Spent** puzzle, mojos returned to wallet (block 8,297,293)

## Market Lifecycle

1. **Create** — Creator locks XCH, mints YES/NO CATs (standard single-issuance)
2. **Trade** — YES/NO tokens trade via Chia offers on Dexie
3. **Resolve** — Oracle signs outcome (YES or NO wins)
4. **Redeem** — Winning token holders spend oracle payout puzzle, receive XCH

## Project Structure

```
chia-predict/
├── puzzles/
│   └── oracle_payout.rue    # Core puzzle (AggSigMe, mainnet-tested)
├── scripts/
│   ├── e2e_mainnet_test.py  # End-to-end test script
│   ├── create_market.py     # Market creation automation
│   └── spend_puzzle.py      # Puzzle spending script
├── tests/
│   ├── mainnet_v2_state.json   # Successful mainnet test state
│   └── submit_body_aggsigme.json # Working spend bundle
├── frontend/                # Next.js app (planned)
├── docs/
│   └── PROTOCOL.md          # Full protocol specification
└── .venv/                   # Python 3.12 + chia-dev-tools
```

## Tech Stack

- **Puzzles:** [Rue](https://rue-lang.com) (compiles to CLVM)
- **Tokens:** Standard CATs (single-issuance TAIL)
- **Trading:** Chia offer files + Dexie aggregation
- **Wallet:** Sage Wallet (CLI + WalletConnect)
- **Frontend:** Next.js + React (planned)
- **Automation:** OpenClaw skills (planned)
- **Explorer:** Spacescan API + FireAcademy RPC

## Key Technical Notes

- Use **AggSigMe** (opcode 50), not AggSigPuzzle (44) — additional data handling is simpler and proven
- Push transactions via `https://kraken.fireacademy.io/leaflet/push_tx` for reliable broadcasting
- Rue must be built from git (`github.com/xch-dev/rue`), not `cargo install rue-cli`
- Python venv requires 3.12 (chia_rs won't build on 3.14)

## Development

```bash
# Build Rue compiler
cd /path/to/rue-lang && cargo build --release

# Set up Python environment
python3.12 -m venv .venv
source .venv/bin/activate
pip install chia-dev-tools

# Compile puzzle
rue build puzzles/oracle_payout.rue

# Run tests
rue test puzzles/oracle_payout.rue
```

## Roadmap

- [x] Oracle payout puzzle (Rue)
- [x] Mainnet E2E test
- [ ] CAT minting (YES/NO tokens per market)
- [ ] Market creation script (lock XCH + mint CATs atomically)
- [ ] Dexie offer integration (list YES/NO pairs)
- [ ] OpenClaw skill for market management
- [ ] Market making bot
- [ ] Web frontend (market browser + wallet connect)
- [ ] Timeout/refund mechanism (if oracle never resolves)
- [ ] Multi-sig oracle support

## Legal

Designed as open-source protocol tooling, not an exchange:
- XCH-native only (no fiat on/off ramp)
- P2P offer-based trading (no central matching engine)
- Users create and resolve markets directly
- No custody of funds at any point
