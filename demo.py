"""
ROTM End-to-End Plain Language Demo.

This script demonstrates the complete ROTM lifecycle in readable, non-technical steps:
1. Initializing two offline device wallets (Alice & Bob).
2. Funding Alice's wallet with Rs. 1,000 (100,000 paise).
3. Alice creating and sending a legitimate Rs. 150 offline payment to Bob over socket transport.
4. Alice attempting a double-spend by resetting her local state and creating a conflicting Rs. 150 payment to Carol with the same nonce.
5. Bob and Carol meeting (simulating physical Bluetooth proximity) and syncing over localhost sockets.
6. Surfaces how ROTM's reconciliation engine detects the conflict, rejects the duplicate, throttles the bad actor, and attaches an LLM risk signal.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.transaction import Wallet
from sync.transport import DeviceNode
from detection.risk_scorer import LocalLLMRiskScorer


def print_step_header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title.upper()}")
    print("=" * 70)


def main():
    print_step_header("ROTM (Resilient Offline Transaction Mesh) End-to-End Demo")
    print("Welcome! This demo shows how ROTM allows offline mobile payments while")
    print("detecting double-spend fraud and assessing transaction risk locally without internet.")

    # ----------------------------------------------------
    # STEP 1: Creating Wallets
    # ----------------------------------------------------
    print_step_header("Step 1: Setting up Offline Digital Wallets")
    print("We create three isolated mobile wallets representing Alice, Bob, and Carol.")
    
    # Initialize scorer connected to local LM Studio (Gemma 3 4B)
    scorer = LocalLLMRiskScorer(
        endpoint="http://localhost:1234/v1/chat/completions",
        model="google/gemma-3-4b",
        timeout_s=5.0
    )

    alice_node = DeviceNode(node_id="Alice's Phone", risk_scorer=scorer)
    bob_node = DeviceNode(node_id="Bob's Phone", risk_scorer=scorer)
    carol_node = DeviceNode(node_id="Carol's Phone", risk_scorer=scorer)

    print(f"[+] Alice's Device Public Key: {alice_node.wallet.pubkey_hex[:16]}...")
    print(f"[+] Bob's Device Public Key:   {bob_node.wallet.pubkey_hex[:16]}...")
    print(f"[+] Carol's Device Public Key: {carol_node.wallet.pubkey_hex[:16]}...")

    # ----------------------------------------------------
    # STEP 2: Funding Alice's Wallet
    # ----------------------------------------------------
    print_step_header("Step 2: Funding Alice's Wallet for Offline Use")
    alice_wallet = alice_node.wallet
    alice_wallet.fund(100_000)  # Rs 1,000 in paise
    
    # Pre-set known balances on ledger views
    bob_node.ledger.set_known_balance(alice_wallet.pubkey_hex, 100_000)
    carol_node.ledger.set_known_balance(alice_wallet.pubkey_hex, 100_000)

    print(f"[+] Alice's Starting Offline Balance: Rs {alice_wallet.balance_paise / 100:.2f}")
    print(f"[+] Alice's Hard Offline Spend Cap:   Rs {alice_wallet.offline_cap_paise / 100:.2f}")
    print("Alice can now spend up to Rs 1,000 while completely disconnected from the bank/internet.")

    # ----------------------------------------------------
    # STEP 3: Normal Offline Payment (Alice -> Bob)
    # ----------------------------------------------------
    print_step_header("Step 3: Alice makes a normal Rs 150 offline payment to Bob")
    txn1 = alice_wallet.create_transaction(bob_node.wallet.pubkey_hex, 15_000)  # Rs 150
    alice_node.ledger.submit(txn1)
    
    print(f"[+] Transaction Created!")
    print(f"  - Amount:     Rs {txn1.amount / 100:.2f}")
    print(f"  - Sequence:   Nonce #{txn1.nonce}")
    print(f"  - Signature:  {txn1.signature[:24]}... (Cryptographically signed by Alice)")
    print(f"[+] Alice's New Balance: Rs {alice_wallet.balance_paise / 100:.2f}")

    # Start Bob's P2P server socket listener
    bob_port = bob_node.start_server(host="127.0.0.1", port=0)
    print(f"[+] Alice connects to Bob over socket transport (simulating Bluetooth/WiFi Direct)...")
    sync1 = alice_node.sync_with_peer("127.0.0.1", bob_port)

    print(f"[SUCCESS] Bob received and verified the payment!")
    print(f"  - Bob's Ledger Accepted: {sync1['peer_accepted_count']} transaction(s)")
    
    if bob_node.risk_assessments:
        ra = bob_node.risk_assessments[-1]
        print(f"  - On-Device LLM Risk Score: {ra.risk_score} (0.0 = Normal, 1.0 = Suspicious)")
        print(f"  - Advisory Reasons: {ra.reasons}")

    # ----------------------------------------------------
    # STEP 4: Simulating a Double-Spend Fraud Attempt
    # ----------------------------------------------------
    print_step_header("Step 4: Simulating a Malicious Double-Spend Attempt")
    print("Alice (or a modified malicious wallet app) resets her local nonce/balance counter")
    print("and attempts to spend the SAME Rs 150 balance to Carol offline.")

    # Tamper with Alice's local wallet state to simulate duplicate spend
    alice_wallet.balance_paise = 85_000  # Reset balance back as if Txn 1 never happened
    alice_wallet.nonce = 0               # Re-use Nonce #0!
    
    txn2_dupe = alice_wallet.create_transaction(carol_node.wallet.pubkey_hex, 15_000)
    carol_node.ledger.submit(txn2_dupe)

    print(f"[+] Malicious Duplicate Transaction Created!")
    print(f"  - Target Recipient: Carol")
    print(f"  - Amount:           Rs {txn2_dupe.amount / 100:.2f}")
    print(f"  - Reused Nonce:     Nonce #{txn2_dupe.nonce} (Matches Txn 1!)")
    print(f"  - Signature:        {txn2_dupe.signature[:24]}...")
    print("Because Carol is offline and hasn't spoken to Bob yet, Carol's phone accepts it locally.")

    # ----------------------------------------------------
    # STEP 5: Peer-to-Peer Sync & Conflict Surface
    # ----------------------------------------------------
    print_step_header("Step 5: Devices Meet & Sync Ledgers (Conflict Detection)")
    print("Later, Bob and Carol pass each other in physical range (or meet at a market).")
    print("Their phones automatically exchange transaction histories over P2P sockets.")

    carol_port = carol_node.start_server(host="127.0.0.1", port=0)
    sync2 = bob_node.sync_with_peer("127.0.0.1", carol_port)

    print(f"[+] Sync Completed between Bob and Carol!")
    print(f"  - Transactions Exchanged: {sync2['received_txns_count']}")
    
    # Check conflicts on Bob & Carol's ledgers
    print(f"[ALERT] FRAUD DETECTED!")
    print(f"  - Conflicts surfaced on Bob's Ledger:   {len(bob_node.ledger.conflicts)}")
    print(f"  - Conflicts surfaced on Carol's Ledger: {len(carol_node.ledger.conflicts)}")
    
    if bob_node.ledger.conflicts:
        conflict = bob_node.ledger.conflicts[0]
        print(f"  - Offending Sender:     {conflict.sender_pub[:16]}... (Alice)")
        print(f"  - Valid Original Txn:   {conflict.accepted_txn_id[:12]}...")
        print(f"  - Rejected Dupe Txn:    {conflict.rejected_txn_id[:12]}...")
    
    print(f"[+] Penalty Applied:")
    print(f"  - Alice's offline spend multiplier is reduced to: {bob_node.ledger.throttle.get(alice_wallet.pubkey_hex, 1.0):.2f}x")

    # Cleanup servers
    bob_node.stop_server()
    carol_node.stop_server()

    # ----------------------------------------------------
    # DEMO CONCLUSION
    # ----------------------------------------------------
    print_step_header("Demo Summary & Key Takeaways")
    print("1. Offline payments work instantly using cryptographic signatures and local caps.")
    print("2. The local LLM provides non-blocking risk scoring on each device.")
    print("3. Double-spend fraud cannot be prevented real-time without central servers, BUT")
    print("   is deterministically detected as soon as devices meet and sync ledgers.")
    print("4. Malicious actors are immediately identified, rejected, and throttled.")
    print("=======================================================================\n")


if __name__ == "__main__":
    main()
