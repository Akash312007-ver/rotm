# ROTM Android — Self-Review Findings
*First-pass review by the same AI (Claude) that wrote much of this code. Not an independent audit — treat as a starting checklist for a real security review, not a substitute for one.*

---

## Findings, by severity

### 🔴 High — worth fixing before any real-money use

**1. Double-spend ledger is in-memory only, not persisted**
`DoubleSpendGuard` (`Transaction.kt`) stores seen transaction IDs and nonces in a `ConcurrentHashMap` that resets on app restart. A malicious sender could replay a previously-accepted transaction after force-closing and reopening the receiver's app, since the guard would no longer remember it.
**Fix direction:** persist seen tx IDs/nonces to disk (Room DB or a file), not just memory.

**2. BLE GATT write characteristic has no encryption/authentication requirement**
`GattManagers.kt` registers the characteristic with `PERMISSION_WRITE`, not `PERMISSION_WRITE_ENCRYPTED`. Any BLE-capable device in range can connect and write to it — the payload's cryptographic signature protects transaction *integrity*, but the channel itself isn't authenticated, meaning noise/junk/malformed writes from unrelated devices can reach the parser.
**Fix direction:** use `PERMISSION_WRITE_ENCRYPTED` + require bonding, or at minimum harden the parser against arbitrary/malformed input (partially done via CRC32, but worth a fuzz-test pass).

### 🟡 Medium — worth addressing before wider distribution

**3. PIN is hashed with plain SHA-256, no salt, no KDF**
`WalletStore.kt` hashes the PIN with a single SHA-256 pass. For a 4-digit PIN (10,000 possible values), this is trivially brute-forceable if the hash were ever exposed outside the Keystore-encrypted storage. In practice the hash sits inside `EncryptedSharedPreferences`, so an attacker needs device-level compromise first — but defense-in-depth says use a proper KDF (PBKDF2/Argon2) with a per-install salt, not raw SHA-256.

**4. No domain separation in the signed payload**
`Transaction.signingPayload()` builds the signed bytes as a plain pipe-delimited string with no protocol version or context tag. If this signing scheme were ever reused for a different message type in the same app (or a future version), there's a theoretical risk of signature reuse across contexts. Low risk today since only one message type exists, but worth adding a version/domain prefix now while it's cheap.

**5. No session/proximity binding on BLE transfers**
A transaction's cryptographic signature proves *who signed it*, but nothing in the current protocol proves the signer is the one physically present over BLE right now — a malicious device could relay/replay chunks it captured elsewhere. This is a known hard problem in offline P2P systems generally (not unique to this implementation), but worth being explicit about in documentation rather than implying BLE proximity alone is a security boundary.

### 🟢 Low / informational

**6. Private key held in plaintext in memory during signing**
Standard for this style of software wallet (not hardware-backed), but worth noting: `Crypto.KeyPair.privateKeyHex` exists in memory as long as the wallet is loaded. A rooted device with active exploitation could potentially dump process memory. Full protection would require hardware-backed key storage (Android Keystore *key* operations, not just encrypted-at-rest storage) — a larger architectural change.

**7. No rate limiting on PIN attempts**
`AuthScreen.kt` doesn't lock out or delay after repeated wrong PIN entries. Someone with physical access to an unlocked-but-backgrounded phone (or after enough guesses) has no cooldown deterrent.

---

## What's already handled reasonably well

- Ed25519 signing/verification via BouncyCastle — standard, well-vetted library, correct usage pattern (sign over a deterministic payload, verify against sender's declared public key).
- Wallet keys are stored via `EncryptedSharedPreferences` (AES-256-GCM, Keystore-backed master key) — not plaintext SharedPreferences, which is the common beginner mistake this avoids.
- CRC32 checksums on BLE chunks catch transmission corruption before it reaches the transaction parser.
- Nonce + transaction-ID double-spend check is directionally correct, just needs persistence (see Finding 1).

---

## Recommended next steps, in priority order

1. Persist the double-spend ledger (Finding 1) — highest-impact fix, directly enables the "real money" goal safely.
2. Add `PERMISSION_WRITE_ENCRYPTED` + bonding requirement to the GATT characteristic (Finding 2).
3. Replace PIN hashing with PBKDF2 + per-install salt (Finding 3) — small code change, meaningful hardening.
4. Add a version/domain prefix to the signed payload (Finding 4) — cheap now, expensive to retrofit later.
5. Document Finding 5 explicitly in the README/paper as a known limitation, not a solved problem.
6. Add PIN attempt rate-limiting (Finding 7) — small UX addition.

None of these are blockers for continued research/demo use. Findings 1–2 are the ones I'd fix before treating this as anything closer to production, especially before real money is involved.
