# End-to-End Demo Execution Output (`demo.py`)

**Execution Timestamp:** August 3, 2026  
**Environment:** Python 3.12, Localhost Sockets, LM Studio (`google/gemma-3-4b`)

```text
======================================================================
  ROTM (RESILIENT OFFLINE TRANSACTION MESH) END-TO-END DEMO
======================================================================
Welcome! This demo shows how ROTM allows offline mobile payments while
detecting double-spend fraud and assessing transaction risk locally without internet.

======================================================================
  STEP 1: SETTING UP OFFLINE DIGITAL WALLETS
======================================================================
We create three isolated mobile wallets representing Alice, Bob, and Carol.
[+] Alice's Device Public Key: 962dfe645de444db...
[+] Bob's Device Public Key:   3fe80fc3175b697b...
[+] Carol's Device Public Key: 0a68476fecf9e61d...

======================================================================
  STEP 2: FUNDING ALICE'S WALLET FOR OFFLINE USE
======================================================================
[+] Alice's Starting Offline Balance: Rs 1000.00
[+] Alice's Hard Offline Spend Cap:   Rs 2000.00
Alice can now spend up to Rs 1,000 while completely disconnected from the bank/internet.

======================================================================
  STEP 3: ALICE MAKES A NORMAL RS 150 OFFLINE PAYMENT TO BOB
======================================================================
[+] Transaction Created!
  - Amount:     Rs 150.00
  - Sequence:   Nonce #0
  - Signature:  2c9c527c4a11f107c78a2ec5... (Cryptographically signed by Alice)
[+] Alice's New Balance: Rs 850.00
[+] Alice connects to Bob over socket transport (simulating Bluetooth/WiFi Direct)...
[SUCCESS] Bob received and verified the payment!
  - Bob's Ledger Accepted: 1 transaction(s)
  - On-Device LLM Risk Score: 0.57 (0.0 = Normal, 1.0 = Suspicious)
  - Advisory Reasons: ['New recipient', 'Zero average transaction amount', 'High transaction amount relative to zero average']

======================================================================
  STEP 4: SIMULATING A MALICIOUS DOUBLE-SPEND ATTEMPT
======================================================================
Alice (or a modified malicious wallet app) resets her local nonce/balance counter
and attempts to spend the SAME Rs 150 balance to Carol offline.
[+] Malicious Duplicate Transaction Created!
  - Target Recipient: Carol
  - Amount:           Rs 150.00
  - Reused Nonce:     Nonce #0 (Matches Txn 1!)
  - Signature:        5930b11b0429e88ec42cecd4...
Because Carol is offline and hasn't spoken to Bob yet, Carol's phone accepts it locally.

======================================================================
  STEP 5: DEVICES MEET & SYNC LEDGERS (CONFLICT DETECTION)
======================================================================
Later, Bob and Carol pass each other in physical range (or meet at a market).
Their phones automatically exchange transaction histories over P2P sockets.
[+] Sync Completed between Bob and Carol!
  - Transactions Exchanged: 1
[ALERT] FRAUD DETECTED!
  - Conflicts surfaced on Bob's Ledger:   1
  - Conflicts surfaced on Carol's Ledger: 1
  - Offending Sender:     962dfe645de444db... (Alice)
  - Valid Original Txn:   0539d27cdef6...
  - Rejected Dupe Txn:    e644f7c6698f...
[+] Penalty Applied:
  - Alice's offline spend multiplier is reduced to: 0.50x

======================================================================
  DEMO SUMMARY & KEY TAKEAWAYS
======================================================================
1. Offline payments work instantly using cryptographic signatures and local caps.
2. The local LLM provides non-blocking risk scoring on each device.
3. Double-spend fraud cannot be prevented real-time without central servers, BUT
   is deterministically detected as soon as devices meet and sync ledgers.
4. Malicious actors are immediately identified, rejected, and throttled.
=======================================================================
```
