"""
Tests for Sybil-resistance mechanisms (docs/PROTOCOL.md Section 8):
1. Relay diversity tracking with k=3 threshold
2. Relay reputation decay for peers that withhold transactions
3. Bounded trust amplification capping any single relay at 20% influence
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.transaction import Wallet
from sync.ledger import Ledger, RelayReputation


def test_relay_reputation_basic():
    rep = RelayReputation()
    assert rep.score == 1.0
    rep.penalize(0.3)
    assert abs(rep.score - 0.7) < 1e-9
    rep.reward(0.1)
    assert abs(rep.score - 0.8) < 1e-9
    print("[PASS] test_relay_reputation_basic")


def test_reputation_bounds():
    rep = RelayReputation(score=0.1)
    rep.penalize(0.5)
    assert rep.score == 0.0, "Reputation should not go below 0"
    rep2 = RelayReputation(score=0.95)
    rep2.reward(0.5)
    assert rep2.score == 1.0, "Reputation should not exceed 1.0"
    print("[PASS] test_reputation_bounds")


def test_relay_diversity_threshold():
    ledger = Ledger()
    alice = Wallet()
    alice.fund(500_000)
    bob = Wallet()

    txn = alice.create_transaction(bob.pubkey_hex, 10_000)

    assert not ledger.check_relay_diversity(txn.txn_id), "Should not meet threshold with 0 relays"

    ledger.submit(txn, relay_pub="relay1")
    assert not ledger.check_relay_diversity(txn.txn_id), "Should not meet threshold with 1 relay"

    ledger.submit(txn, relay_pub="relay2")
    assert not ledger.check_relay_diversity(txn.txn_id), "Should not meet threshold with 2 relays"

    ledger.submit(txn, relay_pub="relay3")
    assert ledger.check_relay_diversity(txn.txn_id), "Should meet threshold with 3 relays"
    print("[PASS] test_relay_diversity_threshold")


def test_diversity_warning_generated():
    ledger = Ledger()
    alice = Wallet()
    alice.fund(500_000)
    bob = Wallet()
    txn = alice.create_transaction(bob.pubkey_hex, 10_000)

    ledger.submit(txn, relay_pub="relay1")
    warning = ledger.get_diversity_warning(txn.txn_id)
    assert warning is not None
    assert "Limited sync diversity" in warning
    print("[PASS] test_diversity_warning_generated")


def test_reputation_penalized_on_conflict():
    ledger = Ledger()
    alice = Wallet(offline_cap_paise=1_000_000)
    alice.fund(50_000)
    bob = Wallet()
    carol = Wallet()

    ledger.set_known_balance(alice.pubkey_hex, 50_000)

    txn1 = alice.create_transaction(bob.pubkey_hex, 50_000)
    ledger.submit(txn1, relay_pub="honest_relay")

    # Simulate a double-spend delivered by a malicious relay
    alice.balance_paise = 50_000
    alice.nonce = 0
    txn2 = alice.create_transaction(carol.pubkey_hex, 50_000)
    ledger.register_relay("malicious_relay")
    before = ledger.relay_reputations["malicious_relay"].score
    ledger.submit(txn2, relay_pub="malicious_relay")
    after = ledger.relay_reputations["malicious_relay"].score

    assert after < before, "Relay delivering a conflicting transaction should be penalized"
    print(f"[PASS] test_reputation_penalized_on_conflict (before={before}, after={after})")


def test_trust_weight_capped():
    ledger = Ledger()
    ledger.register_relay("very_trusted_relay")
    ledger.relay_reputations["very_trusted_relay"].score = 1.0

    weight = ledger.get_trust_weight("very_trusted_relay")
    assert weight <= Ledger.TRUST_AMPLIFICATION_CAP
    assert weight == 0.20
    print(f"[PASS] test_trust_weight_capped (weight={weight})")


def test_unknown_relay_zero_trust():
    ledger = Ledger()
    assert ledger.get_trust_weight("never_seen_relay") == 0.0
    print("[PASS] test_unknown_relay_zero_trust")


def test_sybil_resistance_stats():
    ledger = Ledger()
    ledger.register_relay("relay1")
    ledger.register_relay("relay2")
    ledger.relay_reputations["relay1"].score = 0.8
    ledger.relay_reputations["relay2"].score = 0.6

    stats = ledger.get_sybil_resistance_stats()
    assert stats["relay_count"] == 2
    assert stats["max_single_relay_influence"] <= Ledger.TRUST_AMPLIFICATION_CAP
    print(f"[PASS] test_sybil_resistance_stats ({stats})")


def test_merge_propagates_relay_and_updates_reputation():
    ledger_a = Ledger()
    ledger_b = Ledger()
    alice = Wallet()
    alice.fund(500_000)
    bob = Wallet()

    ledger_a.set_known_balance(alice.pubkey_hex, 500_000)
    ledger_b.set_known_balance(alice.pubkey_hex, 500_000)

    txn = alice.create_transaction(bob.pubkey_hex, 10_000)
    ledger_a.submit(txn)

    conflicts = ledger_b.merge(ledger_a, relay_pub="relay_x")
    assert len(conflicts) == 0
    assert txn.txn_id in ledger_b.entries
    assert "relay_x" in ledger_b.relay_reputations
    assert ledger_b.relay_reputations["relay_x"].score > 1.0 - 1e-9 or ledger_b.relay_reputations["relay_x"].score == 1.0
    print("[PASS] test_merge_propagates_relay_and_updates_reputation")


if __name__ == "__main__":
    test_relay_reputation_basic()
    test_reputation_bounds()
    test_relay_diversity_threshold()
    test_diversity_warning_generated()
    test_reputation_penalized_on_conflict()
    test_trust_weight_capped()
    test_unknown_relay_zero_trust()
    test_sybil_resistance_stats()
    test_merge_propagates_relay_and_updates_reputation()
    print("\nAll Sybil-resistance tests passed.")
