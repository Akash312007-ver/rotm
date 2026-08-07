"""
ROTM Sync Layer: Ledger + double-spend detection + reconciliation.

Core honesty of this module: it does NOT prevent double-spend offline (that's
provably impossible without a reachable authority). It DETECTS conflicts at
the moment two transaction histories are merged (device-to-device sync, or
device-to-server sync), and applies a deterministic reconciliation policy.

Reconciliation policy implemented: first-synced-transaction-wins.
The transaction that reaches the ledger (any ledger instance) first is
honored; later-arriving conflicting transactions from the same sender+nonce
range that would exceed the sender's known balance are flagged and rejected,
and the sender's offline privileges are throttled proportionally.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from core.transaction import Transaction, Wallet


@dataclass
class ConflictRecord:
    sender_pub: str
    accepted_txn_id: str
    rejected_txn_id: str
    detected_at: float
    hops_to_detect: int  # how many device-hops the rejected txn traveled before conflict surfaced


@dataclass
class LedgerEntry:
    txn: Transaction
    accepted_at: float
    hop_count: int = 0  # incremented each time this txn is relayed device-to-device


class RelayReputation:
    """Tracks a relay peer's reputation for Sybil-resistance (see
    docs/PROTOCOL.md Section 8). Score starts neutral, decays sharply on
    detected withholding, recovers gradually on good behavior."""
    def __init__(self, score: float = 1.0):
        self.score = score
        self.last_penalty_time: Optional[float] = None

    def penalize(self, penalty: float = 0.3) -> None:
        self.score = max(0.0, self.score - penalty)
        self.last_penalty_time = time.time()

    def reward(self, reward: float = 0.1) -> None:
        self.score = min(1.0, self.score + reward)


class Ledger:
    """A single ledger view (could represent a phone's local view, or the
    eventual central server view once nodes come back online)."""

    # Sybil-resistance constants (docs/PROTOCOL.md Section 8)
    RELAY_DIVERSITY_THRESHOLD = 3   # k=3 distinct relays required for confidence
    TRUST_AMPLIFICATION_CAP = 0.20  # no single relay >20% influence

    def __init__(self):
        self.entries: dict[str, LedgerEntry] = {}          # txn_id -> entry
        self.sender_nonces_seen: dict[str, set[int]] = {}  # sender_pub -> set of nonces committed
        self.sender_committed_spend: dict[str, int] = {}   # sender_pub -> total committed spend
        self.known_balances: dict[str, int] = {}           # sender_pub -> last confirmed balance
        self.conflicts: list[ConflictRecord] = []
        self.throttle: dict[str, float] = {}                # sender_pub -> throttle multiplier (1.0 = normal)
        self.rejected_ids: set[str] = set()                  # txn_ids already rejected -- avoids re-counting
                                                               # the same conflict every time two devices re-meet

        # Sybil-resistance tracking (docs/PROTOCOL.md Section 8)
        self.relay_reputations: dict[str, RelayReputation] = {}  # relay_pub -> reputation
        self.sync_history: dict[str, set[str]] = {}               # txn_id -> set of relay pubs that relayed it
        self.diversity_warnings: list[str] = []                   # human-readable warnings, deduped

    def set_known_balance(self, pubkey: str, balance_paise: int) -> None:
        self.known_balances[pubkey] = balance_paise

    def submit(self, txn: Transaction, hop_count: int = 0, relay_pub: Optional[str] = None) -> tuple[bool, Optional[ConflictRecord]]:
        """Attempt to commit a transaction to this ledger.

        relay_pub: the peer identity this transaction arrived through, used
        for Sybil-resistance tracking (docs/PROTOCOL.md Section 8). None
        for locally-created transactions (no relay involved).

        Returns (accepted: bool, conflict: ConflictRecord | None).
        """
        if not Wallet.verify_transaction(txn):
            return False, None

        if txn.txn_id in self.entries:
            # Already seen this exact transaction (deduped during mesh relay) -- fine.
            if relay_pub:
                self._track_relay_diversity(txn.txn_id, relay_pub)
            return True, None

        if txn.txn_id in self.rejected_ids:
            # Already known-rejected from a previous merge -- don't re-flag
            # it as a "new" conflict every time two devices happen to re-meet.
            return False, None

        sender = txn.sender_pub
        seen_nonces = self.sender_nonces_seen.setdefault(sender, set())

        if txn.nonce in seen_nonces:
            # Same nonce already committed by a different transaction from this
            # sender -- this IS the double-spend/replay signature. Reject and record.
            existing_id = next(
                (e.txn.txn_id for e in self.entries.values()
                 if e.txn.sender_pub == sender and e.txn.nonce == txn.nonce),
                "unknown",
            )
            conflict = ConflictRecord(
                sender_pub=sender,
                accepted_txn_id=existing_id,
                rejected_txn_id=txn.txn_id,
                detected_at=time.time(),
                hops_to_detect=hop_count,
            )
            self.conflicts.append(conflict)
            self.rejected_ids.add(txn.txn_id)
            self._throttle_sender(sender)
            if relay_pub:
                self.update_relay_reputation(relay_pub, success=False)
            return False, conflict

        committed = self.sender_committed_spend.get(sender, 0)
        known_balance = self.known_balances.get(sender, float("inf"))

        if committed + txn.amount > known_balance:
            # Sender is trying to spend more than their last-confirmed balance
            # allows, across possibly-multiple valid-looking transactions.
            conflict = ConflictRecord(
                sender_pub=sender,
                accepted_txn_id="(balance_exceeded)",
                rejected_txn_id=txn.txn_id,
                detected_at=time.time(),
                hops_to_detect=hop_count,
            )
            self.conflicts.append(conflict)
            self.rejected_ids.add(txn.txn_id)
            self._throttle_sender(sender)
            if relay_pub:
                self.update_relay_reputation(relay_pub, success=False)
            return False, conflict

        # Accept.
        seen_nonces.add(txn.nonce)
        self.sender_committed_spend[sender] = committed + txn.amount
        self.entries[txn.txn_id] = LedgerEntry(txn=txn, accepted_at=time.time(), hop_count=hop_count)
        if relay_pub:
            self._track_relay_diversity(txn.txn_id, relay_pub)
            self.update_relay_reputation(relay_pub, success=True)
        return True, None

    def register_relay(self, relay_pub: str) -> None:
        """Register a relay peer with neutral starting reputation."""
        if relay_pub not in self.relay_reputations:
            self.relay_reputations[relay_pub] = RelayReputation()

    def update_relay_reputation(self, relay_pub: str, success: bool) -> None:
        """Adjust a relay's reputation after a sync attempt.
        success=True: relay delivered a transaction that was accepted cleanly.
        success=False: relay delivered a transaction that turned out to be
        a conflict/rejection -- treated as a withholding/misbehavior signal."""
        self.register_relay(relay_pub)
        if success:
            self.relay_reputations[relay_pub].reward()
        else:
            self.relay_reputations[relay_pub].penalize()

    def _track_relay_diversity(self, txn_id: str, relay_pub: str) -> None:
        self.sync_history.setdefault(txn_id, set()).add(relay_pub)

    def check_relay_diversity(self, txn_id: str) -> bool:
        """True if this transaction has been seen via >= RELAY_DIVERSITY_THRESHOLD
        distinct relays -- meaning suppression by any single relay cluster
        smaller than that threshold cannot hide it."""
        return len(self.sync_history.get(txn_id, set())) >= self.RELAY_DIVERSITY_THRESHOLD

    def get_diversity_warning(self, txn_id: str) -> Optional[str]:
        """Returns a warning string if diversity threshold isn't met, else None."""
        if self.check_relay_diversity(txn_id):
            return None
        seen = len(self.sync_history.get(txn_id, set()))
        warning = (f"Limited sync diversity for transaction {txn_id}: only {seen} "
                   f"distinct relay(s) seen (threshold: {self.RELAY_DIVERSITY_THRESHOLD})")
        if warning not in self.diversity_warnings:
            self.diversity_warnings.append(warning)
        return warning

    def get_trust_weight(self, relay_pub: str) -> float:
        """Trust weight for a relay, capped at TRUST_AMPLIFICATION_CAP so no
        single relay (however reputable-seeming) can dominate trust decisions."""
        if relay_pub not in self.relay_reputations:
            return 0.0
        return min(self.relay_reputations[relay_pub].score, self.TRUST_AMPLIFICATION_CAP)

    def get_network_trust_score(self) -> float:
        """Aggregate trust across all known relays (each capped individually)."""
        if not self.relay_reputations:
            return 0.0
        total = sum(self.get_trust_weight(r) for r in self.relay_reputations)
        return min(total, 1.0)

    def get_sybil_resistance_stats(self) -> dict:
        reps = self.relay_reputations.values()
        return {
            "relay_count": len(self.relay_reputations),
            "avg_reputation": (sum(r.score for r in reps) / len(reps)) if reps else 0.0,
            "diversity_warnings": len(self.diversity_warnings),
            "network_trust_score": self.get_network_trust_score(),
            "max_single_relay_influence": max(
                (self.get_trust_weight(r) for r in self.relay_reputations), default=0.0
            ),
        }

    def _throttle_sender(self, sender: str) -> None:
        current = self.throttle.get(sender, 1.0)
        self.throttle[sender] = max(0.1, current * 0.5)  # halve offline privileges per detected conflict

    def merge(self, other: "Ledger", relay_pub: Optional[str] = None) -> list[ConflictRecord]:
        """Merge another ledger's entries into this one (device-to-device sync).
        relay_pub identifies the peer this merge came through, for Sybil-
        resistance tracking (docs/PROTOCOL.md Section 8).
        Returns any new conflicts discovered during merge."""
        new_conflicts = []
        for entry in sorted(other.entries.values(), key=lambda e: e.accepted_at):
            accepted, conflict = self.submit(entry.txn, hop_count=entry.hop_count + 1, relay_pub=relay_pub)
            if conflict:
                new_conflicts.append(conflict)
        return new_conflicts

    def total_committed(self, sender_pub: str) -> int:
        return self.sender_committed_spend.get(sender_pub, 0)

    def conflict_rate(self) -> float:
        total_attempts = len(self.entries) + len(self.conflicts)
        if total_attempts == 0:
            return 0.0
        return len(self.conflicts) / total_attempts

    def decay_stale_reputations(self, current_time: float, half_life_seconds: float = 3600) -> None:
        """Decay the reputation scores of relays that have been penalized, based on time elapsed since last penalty.
        The score recovers towards 1.0 exponentially with the given half-life.
        """
        for reputation in self.relay_reputations.values():
            if reputation.last_penalty_time is not None:
                elapsed = current_time - reputation.last_penalty_time
                decay_factor = 1 - 0.5 ** (elapsed / half_life_seconds)
                reputation.score = min(1.0, reputation.score + (1.0 - reputation.score) * decay_factor)
