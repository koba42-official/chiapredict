# Chiapredict

> **A free starting point for CLVM-powered prediction markets on Chia**

![Chiapredict Open Graph](./og-image.png)

## Overview

**Chiapredict** is a static front-end concept/prototype for a Polymarket-style experience on Chia.

This project was built using:
- **Rue** (by **[@rigidity](https://github.com/rigidity)**) for CLVM smart-contract development patterns
- **AI-assisted development** for accelerated implementation and iteration

It is published as a **free starting point** for builders exploring decentralized prediction market UX and CLVM market mechanics.

---

## What this project demonstrates

- Polymarket-inspired interface direction
- Chia-native framing with CAT token market concepts
- Market cards, outcomes, mechanics, and explanatory sections
- Static front-end implementation suitable for rapid experimentation

---

## Tech profile

- **Type:** Static website
- **Primary file:** `index.html`
- **Assets:** `og-image.png`
- **Deployment model:** Nginx static hosting (Traefik-routed in current deployment)

---

## Getting started

### Option 1: Open directly

Open `index.html` in your browser.

### Option 2: Serve locally (recommended)

```bash
cd chiapredict
python3 -m http.server 8080
```

Then visit: `http://localhost:8080`

---

## Intended audience

- Chia ecosystem developers
- CLVM/Rue experimenters
- Teams prototyping decentralized market UX

---

## Security & risk notice

⚠️ **Use at your own risk.**

This repository is provided for educational and prototyping purposes. It does **not** constitute financial, legal, or production-readiness advice. If you extend this toward a real-money application, you are responsible for:

- independent smart-contract audits,
- economic attack modeling,
- oracle/truth-resolution design,
- legal/regulatory review,
- production security controls.

No warranty is provided, express or implied.

---

## Attribution

- CLVM workflow inspiration and implementation direction: **Rue by [@rigidity](https://github.com/rigidity)**
- Build acceleration and iteration support: **AI-assisted development**

---

## License

Please add your preferred license for reuse terms.

---

## Final note

If this saves you a week of prototyping, mission accomplished.

**Happy Dev-ing.** 🚀
