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


class Ledger:
    """A single ledger view (could represent a phone's local view, or the
    eventual central server view once nodes come back online)."""

    def __init__(self):
        self.entries: dict[str, LedgerEntry] = {}          # txn_id -> entry
        self.sender_nonces_seen: dict[str, set[int]] = {}  # sender_pub -> set of nonces committed
        self.sender_committed_spend: dict[str, int] = {}   # sender_pub -> total committed spend
        self.known_balances: dict[str, int] = {}           # sender_pub -> last confirmed balance
        self.conflicts: list[ConflictRecord] = []
        self.throttle: dict[str, float] = {}                # sender_pub -> throttle multiplier (1.0 = normal)
        self.rejected_ids: set[str] = set()                  # txn_ids already rejected -- avoids re-counting
                                                               # the same conflict every time two devices re-meet

    def set_known_balance(self, pubkey: str, balance_paise: int) -> None:
        self.known_balances[pubkey] = balance_paise

    def submit(self, txn: Transaction, hop_count: int = 0) -> tuple[bool, Optional[ConflictRecord]]:
        """Attempt to commit a transaction to this ledger.

        Returns (accepted: bool, conflict: ConflictRecord | None).
        """
        if not Wallet.verify_transaction(txn):
            return False, None

        if txn.txn_id in self.entries:
            # Already seen this exact transaction (deduped during mesh relay) -- fine.
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
            return False, conflict

        # Accept.
        seen_nonces.add(txn.nonce)
        self.sender_committed_spend[sender] = committed + txn.amount
        self.entries[txn.txn_id] = LedgerEntry(txn=txn, accepted_at=time.time(), hop_count=hop_count)
        return True, None

    def _throttle_sender(self, sender: str) -> None:
        current = self.throttle.get(sender, 1.0)
        self.throttle[sender] = max(0.1, current * 0.5)  # halve offline privileges per detected conflict

    def merge(self, other: "Ledger") -> list[ConflictRecord]:
        """Merge another ledger's entries into this one (device-to-device sync).
        Returns any new conflicts discovered during merge."""
        new_conflicts = []
        for entry in sorted(other.entries.values(), key=lambda e: e.accepted_at):
            accepted, conflict = self.submit(entry.txn, hop_count=entry.hop_count + 1)
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
