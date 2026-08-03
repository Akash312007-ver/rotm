"""
ROTM Test Suite.

Run with: python -m pytest tests/ -v
Or standalone: python tests/test_core.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.transaction import Wallet, Transaction, InsufficientOfflineBalance, OfflineCapExceeded
from sync.ledger import Ledger


def test_signature_valid_and_tamper_detected():
    alice = Wallet()
    alice.fund(100_000)  # Rs 1000
    bob = Wallet()

    txn = alice.create_transaction(bob.pubkey_hex, 5_000)
    assert Wallet.verify_transaction(txn), "Valid signature should verify"

    tampered = Transaction(**{**txn.to_dict(), "amount": 50_000})
    assert not Wallet.verify_transaction(tampered), "Tampered amount must fail verification"
    print("[PASS] test_signature_valid_and_tamper_detected")


def test_offline_cap_enforced():
    alice = Wallet(offline_cap_paise=10_000)
    alice.fund(1_000_000)  # plenty of balance, cap is the binding constraint
    bob = Wallet()

    alice.create_transaction(bob.pubkey_hex, 8_000)
    try:
        alice.create_transaction(bob.pubkey_hex, 5_000)  # would total 13,000 > 10,000 cap
        assert False, "Should have raised OfflineCapExceeded"
    except OfflineCapExceeded:
        pass
    print("[PASS] test_offline_cap_enforced")


def test_insufficient_balance_rejected():
    alice = Wallet()
    alice.fund(1_000)
    bob = Wallet()
    try:
        alice.create_transaction(bob.pubkey_hex, 5_000)
        assert False, "Should have raised InsufficientOfflineBalance"
    except InsufficientOfflineBalance:
        pass
    print("[PASS] test_insufficient_balance_rejected")


def test_double_spend_detected_on_ledger_merge():
    """The core research claim: simulate Alice double-spending offline to two
    different recipients, then merging both transaction histories into a
    ledger, and confirm the conflict is detected and one txn rejected."""
    alice = Wallet(offline_cap_paise=1_000_000)
    alice.fund(50_000)  # Rs 500
    bob = Wallet()
    carol = Wallet()

    # Alice spends her entire Rs 500 balance to Bob...
    txn_to_bob = alice.create_transaction(bob.pubkey_hex, 50_000)

    # ...then manually resets her local nonce/balance to simulate a
    # compromised/malicious client trying to double-spend to Carol.
    alice.balance_paise = 50_000
    alice.nonce = 0  # reusing the same nonce, as a naive double-spend would
    txn_to_carol = alice.create_transaction(carol.pubkey_hex, 50_000)

    ledger_a = Ledger()
    ledger_a.set_known_balance(alice.pubkey_hex, 50_000)
    ledger_b = Ledger()
    ledger_b.set_known_balance(alice.pubkey_hex, 50_000)

    accepted1, conflict1 = ledger_a.submit(txn_to_bob)
    assert accepted1 and conflict1 is None

    accepted2, conflict2 = ledger_b.submit(txn_to_carol)
    assert accepted2 and conflict2 is None  # each ledger alone sees only ONE txn -- looks fine locally

    # Now simulate the two devices meeting (e.g. both come back online, or
    # relay through a common mesh node) and merging their views.
    new_conflicts = ledger_a.merge(ledger_b)
    assert len(new_conflicts) == 1, "Merging should surface exactly one conflict"
    assert new_conflicts[0].sender_pub == alice.pubkey_hex
    assert ledger_a.conflict_rate() > 0
    print(f"[PASS] test_double_spend_detected_on_ledger_merge "
          f"(conflict_rate={ledger_a.conflict_rate():.2f}, "
          f"hops_to_detect={new_conflicts[0].hops_to_detect})")


def test_throttle_applied_after_conflict():
    alice = Wallet(offline_cap_paise=1_000_000)
    alice.fund(50_000)
    bob = Wallet()
    carol = Wallet()

    txn1 = alice.create_transaction(bob.pubkey_hex, 50_000)
    alice.balance_paise = 50_000
    alice.nonce = 0
    txn2 = alice.create_transaction(carol.pubkey_hex, 50_000)

    ledger = Ledger()
    ledger.set_known_balance(alice.pubkey_hex, 50_000)
    ledger.submit(txn1)
    ledger.submit(txn2)  # same nonce -> conflict

    assert ledger.throttle.get(alice.pubkey_hex, 1.0) < 1.0, "Sender should be throttled after conflict"
    print(f"[PASS] test_throttle_applied_after_conflict (throttle={ledger.throttle[alice.pubkey_hex]:.2f})")


def test_wallet_state_persistence():
    import tempfile
    state_file = os.path.join(tempfile.gettempdir(), "test_wallet_state.json")
    if os.path.exists(state_file):
        os.remove(state_file)

    try:
        alice1 = Wallet()
        alice1.fund(100_000) # Rs 1000
        bob = Wallet()

        t1 = alice1.create_transaction(bob.pubkey_hex, 10_000)
        assert t1.nonce == 0
        assert alice1.nonce == 1

        alice1.save_state(state_file)

        # Simulate app restart: create a new Wallet instance and load state
        alice2 = Wallet.from_state_file(state_file)
        assert alice2.pubkey_hex == alice1.pubkey_hex
        assert alice2.nonce == 1
        assert alice2.balance_paise == 90_000
        assert alice2.offline_spent_paise == 10_000

        t2 = alice2.create_transaction(bob.pubkey_hex, 5_000)
        assert t2.nonce == 1
        assert alice2.nonce == 2
        assert t2.sender_pub == alice1.pubkey_hex
        assert Wallet.verify_transaction(t2)

        print("[PASS] test_wallet_state_persistence")
    finally:
        if os.path.exists(state_file):
            os.remove(state_file)


if __name__ == "__main__":
    test_signature_valid_and_tamper_detected()
    test_offline_cap_enforced()
    test_insufficient_balance_rejected()
    test_double_spend_detected_on_ledger_merge()
    test_throttle_applied_after_conflict()
    test_wallet_state_persistence()
    print("\nAll tests passed.")
