# Security & Architectural Code Review

**Project:** ROTM — Resilient Offline Transaction Mesh  
**Date:** August 3, 2026  
**Audited Modules:** `core/transaction.py`, `sync/ledger.py`, `sync/transport.py`, `detection/risk_scorer.py`, `sync/mesh_simulator.py`

---

## Executive Summary

The ROTM codebase exhibits clean separation of concerns, strong cryptographic foundations (Ed25519 signatures via PyNaCl), integer currency arithmetic (`paise` to prevent floating-point errors), and realistic threat bounding (offline spending caps and advisory LLM scoring). However, several edge cases, transport vulnerabilities, and protocol gaps were identified that must be addressed before production deployment on mobile hardware.

---

## 1. Cryptographic & Core Ledger (`core/transaction.py`)

### 🔴 High Severity / Critical
1. **Lack of Domain Separator / Chain Identifier in Transaction Payload**
   - **Issue:** `Transaction.signing_payload()` serializes `sender_pub`, `recipient_pub`, `amount`, `nonce`, and `timestamp`, but lacks a `chain_id` or protocol domain tag (e.g., `ROTM-v1-mainnet`).
   - **Impact:** A valid offline transaction signed on a testnet or mesh environment could be replayed verbatim on mainnet or across different ROTM deployments.
   - **Fix:** Add `domain_separator: "ROTM-v1"` into `signing_payload()`.

2. **Ephemeral Nonce & State Persistence**
   - **Issue:** `Wallet` tracks `nonce` and `balance_paise` strictly in memory. If an offline mobile app crashes or restarts, its state is lost and nonces reset to `0`.
   - **Impact:** Post-crash transactions from a legitimate user will reuse nonces, causing them to be flagged and penalized as malicious double-spends.
   - **Fix Status:** ✅ **Fixed**: Implemented `save_state(filepath)` / `load_state(filepath)` methods on `Wallet` to persist key seed, nonces, balances, and outbox to local state files (`wallet_state.json`).

### 🟡 Medium Severity
3. **Float Timestamp Serialization Non-Determinism**
   - **Issue:** `self.timestamp` is stored as a Python `float` (`time.time()`).
   - **Impact:** Cross-platform implementations (e.g., Python vs. Rust vs. Swift/Kotlin) serialize floating-point numbers differently in `json.dumps()` (e.g. trailing zeros or precision differences), causing valid signatures to fail cross-verification.
   - **Fix:** Use standard integer millisecond UNIX timestamps (`int(time.time() * 1000)`).

---

## 2. Sync & Reconciliation Engine (`sync/ledger.py`)

### 🟡 Medium Severity
1. **Clock-Drift & Timestamp Spoofing Vulnerability in `merge()`**
   - **Issue:** `Ledger.merge()` sorts peer transactions by `accepted_at` timestamp.
   - **Impact:** Because offline phones have un-synchronized clocks, a malicious client could backdate its local `accepted_at` timestamp to force its double-spend transaction to be processed first in the "first-synced-wins" reconciliation policy.
   - **Fix:** Use deterministic vector clocks or strict ledger sequence counters rather than wall-clock timestamps for entry ordering.

2. **Unbounded Memory Growth**
   - **Issue:** `entries`, `conflicts`, and `rejected_ids` grow monotonically in memory.
   - **Impact:** On resource-constrained mobile devices running long-term, memory consumption will eventually crash the background process.
   - **Fix:** Implement sliding window persistence or persistent local database storage for historical ledger entries.

---

## 3. Network Transport Layer (`sync/transport.py`)

### 🔴 High Severity
1. **Unbounded Frame Length Allocation (Denial of Service)**
   - **Issue:** `recv_framed_message()` reads a 4-byte big-endian integer header (`payload_len`) and attempts to read up to `payload_len` bytes into memory.
   - **Impact:** A malicious socket peer can send a 4-byte header specifying `payload_len = 2,147,483,647` (2 GB), triggering immediate memory exhaustion and crashing the listener node.
   - **Fix:** Enforce a hard maximum frame size check (e.g., `MAX_FRAME_SIZE = 1_048_576` bytes / 1 MB) before allocating buffer memory.

2. **Lack of Transport Encryption & Mutual Authentication**
   - **Issue:** Socket transport transmits raw JSON over TCP.
   - **Impact:** Wi-Fi Direct or Bluetooth streams without transport security (TLS or Noise Protocol) are vulnerable to passive packet sniffing and active Man-in-the-Middle (MitM) transaction injection.
   - **Fix:** Implement Noise Protocol Framework (e.g. `Noise_XX`) or TLS 1.3 over sockets for transport encryption and peer identity verification.

---

## 4. On-Device LLM Risk Scorer (`detection/risk_scorer.py`)

### 🟡 Medium Severity
1. **Inference Timeout Flakiness on Mobile Hardware**
   - **Issue:** `LocalLLMRiskScorer` uses a default timeout of `3.0s`.
   - **Impact:** On mobile processors (NPU/CPU), inference for Gemma 3 4B may exceed 3.0s under load, causing fallback to heuristic scoring even when the server is healthy.
   - **Fix:** Make timeout dynamic based on target device tier and model parameter size (e.g., 5-10s for 4B models on mobile).

2. **Prompt Injection Risk**
   - **Issue:** Raw transaction fields (e.g. public keys or metadata) are interpolated directly into prompt text.
   - **Impact:** Though current fields are hex strings, future metadata additions (e.g. transaction memos) could inject prompt instructions that manipulate the model's risk score.
   - **Fix:** Sanitize and escape all user-controllable text inputs prior to prompt construction.

---

## Summary Table of Issues

| Module | Issue Description | Severity | Recommended Remediation |
| :--- | :--- | :--- | :--- |
| `core/transaction.py` | Missing domain separator in payload | 🔴 High | Add `"domain_separator": "ROTM-v1"` to payload dict |
| `core/transaction.py` | Ephemeral nonce & state persistence across restarts | 🔴 High | ✅ **Fixed**: Added `save_state()` / `load_state()` JSON persistence |
| `core/transaction.py` | Float timestamp precision non-determinism | 🟡 Medium | Use integer millisecond timestamps |
| `sync/transport.py` | Unbounded frame size in socket reader | 🔴 High | ✅ **Fixed**: Added `MAX_FRAME_SIZE = 10MB` cap |
| `sync/transport.py` | Plaintext TCP transport without encryption | 🔴 High | Wrap sockets with Noise Protocol or TLS |
| `sync/ledger.py` | Timestamp sorting vulnerable to clock drift | 🟡 Medium | Use vector clocks or logical sequence numbers |
| `detection/risk_scorer.py` | 3.0s timeout too aggressive for mobile NPUs | 🟡 Medium | Adjust default timeout to 5–10s |
