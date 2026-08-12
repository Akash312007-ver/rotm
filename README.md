<div align="center">

# ROTM
### Resilient Offline Transaction Mesh

**Peer-to-peer payments that work with zero internet connectivity.**

[![Build](https://img.shields.io/github/actions/workflow/status/Akash312007-ver/rotm/build.yml?branch=main&label=build)](../../actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Android-3DDC84?logo=android&logoColor=white)](#)
[![Kotlin](https://img.shields.io/badge/Kotlin-7F52FF?logo=kotlin&logoColor=white)](#)
[![Status](https://img.shields.io/badge/status-research%20prototype-orange)](#)

[Overview](#why-this-exists) • [Features](#whats-implemented) • [Architecture](#architecture) • [Build](#building) • [Roadmap](#real-money-integration--future-work)

</div>

---

> **Research prototype.** Wallet balances are simulated unless explicitly connected
> to a real payment provider. This is not a licensed payment app and does not move
> real money on its own. See [Real-Money Integration](#real-money-integration--future-work).

## Why this exists

Most digital payments assume both parties are online. ROTM explores the opposite
case: what if the *payer* has no connectivity at all, but the *payee* (or a nearby
device) does? This mirrors real infrastructure gaps — rural areas, disaster zones,
transit systems, and merchant scenarios where a customer's data is down but the
shop's isn't.

The core insight: you don't need **both** sides online to settle a payment safely.
You need the payer's transaction to be cryptographically valid and non-replayable,
and you need *someone* in the chain with connectivity to finalize it.

RBI's own offline Digital Rupee (e-₹) pilot explores a similar model — this project
takes the same premise and builds a working, testable implementation of it.

---

## What's implemented

| Component | Status | Description |
|---|:---:|---|
| Ed25519 signing/verification | Done | Wallet keypairs, transaction signing (BouncyCastle) |
| Double-spend detection | Done | Nonce + transaction-ID tracking, thread-safe |
| BLE transport | Done | Chunking, CRC32 checksums, reassembly over GATT |
| GATT server/client | Done | Real peer-to-peer transfer over Android BLE |
| Wallet persistence | Done | Android Keystore-backed encrypted storage |
| PIN authentication | Done | App-lock screen before wallet access |
| QR scan-to-pay | Done | Camera-based scanning (ZXing) |
| QR receive | Done | Generate a QR of your own public key |
| Animated wallet UI | Done | Jetpack Compose, bottom nav, live balance |
| Two-device real-hardware test | In progress | Verifying BLE transfer between two physical phones |
| Merchant settlement backend | Planned | Server-side relay for online-merchant scenarios |
| Real bank/UPI integration | Future work | Requires a licensed partner — see roadmap |

---

## Architecture

```
  Payer (offline)  --BLE, signed & chunked-->  Payee (may be online)
                                                        |
                                                        v internet (optional)
                                              Settlement backend
                                              (double-spend check,
                                               real-money settle)
```

**Crypto core** (`Crypto.kt`) — Ed25519 keypair generation, signing, verification.

**Transaction model** (`Transaction.kt`) — deterministic transaction IDs, signed payloads.

**Double-spend guard** (`DoubleSpendGuard.kt`) — tracks seen transaction IDs and
per-sender nonces; thread-safe for concurrent BLE deliveries.

**BLE transport** (`BleTransport.kt`, `GattManagers.kt`) — chunks transactions to fit
BLE MTU limits, checksums each chunk, reassembles on the receiving end. Real GATT
server (peripheral/receiver) and client (central/sender) roles.

**Secure storage** (`WalletStore.kt`) — wallet keys and PIN hash stored via
`EncryptedSharedPreferences`, backed by Android Keystore (AES-256).

**UI** (`WalletScreen.kt`, `AuthScreen.kt`) — Jetpack Compose, animated balance card,
QR scan/generate, PIN lock screen.

---

## Building

**Requirements:** Android Studio (Ladybug or newer), min SDK 26 (Android 8.0).

```bash
git clone https://github.com/Akash312007-ver/rotm.git
cd rotm/android
./gradlew assembleDebug
```

Or open the project directly in Android Studio and run.

> **Testing on real devices:** BLE peripheral advertising and multi-device GATT
> transfer do not work reliably in the Android emulator. Use two physical Android
> phones with Bluetooth enabled.

### Download

Prebuilt APKs are available on the [Releases](../../releases) page — no Android
Studio required, just install directly on an Android 8.0+ phone.

---

## Real-money integration — future work

This prototype intentionally does **not** move real money. Doing so legitimately
requires one of:

- Integration with a licensed payment gateway (Razorpay, Cashfree, Setu, etc.) for
  the online top-up step, with your own KYC/business registration for real funds.
- RBI Prepaid Payment Instrument (PPI) licensing, or UPI TPAP status via a sponsor
  bank, to operate as a payment provider directly.

Neither is a solo/weekend undertaking — they involve regulatory review and (for the
second option) months of process. The offline transfer mechanism in this repo is
provider-agnostic: it could sit underneath a licensed gateway's top-up/settlement
layer without architectural changes to the BLE mesh itself.

---

## Security notes

- Private keys are stored via Android Keystore-backed encryption, never in plaintext.
- Transactions are Ed25519-signed; tampering invalidates the signature.
- Double-spend protection is nonce + transaction-ID based, verified at receipt.
- **Not yet audited.** Treat this as a research prototype, not production-hardened
  cryptographic software, until an independent security review has been done.

---

## Related work

The original Python core (crypto, double-spend detection, BLE-simulated transport,
Flask demo, TLA+ formal verification) that this Android port is based on:
[`github.com/Akash312007-ver/rotm`](https://github.com/Akash312007-ver/rotm)

Includes:
- TLA+ model-checked protocol (187,489 states verified, zero safety violations)
- Local LLM-based fraud scoring (tested against Gemma 3 4B)
- Sybil-resistance mechanisms

---

## Contributing

Issues and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Areas that would
help most right now:

- Two-device BLE range/reliability testing across different phone models
- Security review of the crypto and double-spend implementation
- Payment gateway sandbox integration (top-up flow)
- UI/UX polish and accessibility

---

## License

MIT — see [LICENSE](LICENSE).
