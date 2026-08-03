# ROTM — Resilient Offline Transaction Mesh

[![ROTM CI - Core & Transport Tests](https://github.com/OWNER/REPOSITORY/actions/workflows/tests.yml/badge.svg)](https://github.com/OWNER/REPOSITORY/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)

An offline-first, cryptographically-signed P2P payment protocol that keeps working when there's no internet, no cell signal, and no central server — with a local, on-device LLM providing fraud-risk signals, fully offline.

Built for scenarios like natural disasters, rural connectivity gaps, and infrastructure attacks (grid/network outages) where digital payments otherwise stop working entirely.

---

## Quick Start / Getting Started

### 1. Installation

```bash
# Clone repository
git clone https://github.com/OWNER/REPOSITORY.git
cd rotm

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the End-to-End Demo

Experience the full offline payment lifecycle, socket transport sync, double-spend detection, and local LLM risk scoring:

```bash
python demo.py
```

### 3. Run Test Suites

```bash
# Run core cryptography & ledger tests
python tests/test_core.py

# Run device-to-device transport tests
python tests/test_transport.py

# Run on-device LLM risk scorer test (requires LM Studio running locally with Gemma 3 4B)
python tests/test_risk_scorer.py
```

### 4. Run Discrete-Event Mesh Simulation

```bash
# Generates discrete-event mesh benchmark data & cap sensitivity sweep
python sync/mesh_simulator.py
```

---

## The Honest Core Problem

Two devices with no network cannot cryptographically prevent double-spending against each other in real time — this is a fundamental constraint, not an engineering gap. **ROTM does not claim to solve this.** Instead it:

1. **Bounds the damage** via a hard per-wallet offline spending cap
2. **Detects conflicts** deterministically the moment two transaction histories merge (devices meet, or connectivity returns)
3. **Scores risk locally** using an on-device LLM (Gemma 3 4B / Phi-4 via LM Studio or Ollama) as an advisory signal, never a gatekeeper
4. **Throttles bad actors** — offline privileges shrink after a detected conflict

---

## Architecture & Project Structure

```text
rotm/
├── core/
│   └── transaction.py      - Ed25519 signing, Wallet, offline spend cap & JSON persistence
├── sync/
│   ├── ledger.py           - Double-spend detection & first-synced-wins reconciliation
│   ├── transport.py        - Framed TCP socket P2P device-to-device transport simulator
│   ├── mesh_simulator.py   - Discrete-event simulation for paper benchmark data
│   └── socket_demo.py      - Standalone socket transport demo
├── detection/
│   └── risk_scorer.py      - Local LLM (LM Studio / Ollama) advisory risk scoring engine
├── tests/
│   ├── test_core.py        - Core crypto, offline caps & wallet persistence tests
│   ├── test_transport.py   - Socket P2P transport & max frame cap tests
│   └── test_risk_scorer.py - Live Gemma 3 4B risk scoring tests
├── results/                - Security code review, test outputs & evaluation summaries
├── docs/                   - Architecture roadmap & protocol rationale
├── demo.py                 - End-to-end human-readable demonstration script
├── requirements.txt        - Python dependencies
├── CONTRIBUTING.md         - Contributor guidelines
└── LICENSE                 - MIT License
```

---

## Status & Progress

- [x] Core Ed25519 signing + wallet + offline cap — tested & working
- [x] Wallet state persistence (`save_state()` / `load_state()`) — tested & working
- [x] Double-spend detection on ledger merge — tested & working
- [x] Framed socket P2P transport simulator with 10MB frame cap — tested & working
- [x] Local LLM risk scoring layer against Gemma 3 4B — verified working
- [x] End-to-end demonstration script (`demo.py`) — verified working
- [x] GitHub Actions CI pipeline — configured
- [ ] Native BLE / Wi-Fi Direct Android & iOS transport wrappers (see [`docs/ROADMAP.md`](docs/ROADMAP.md))
- [ ] Mobile app UI (Flutter/React Native) with embedded GGUF runtime

---

## License & Commercial Use

ROTM is licensed under the open source [MIT License](LICENSE). Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md).
