"""
ROTM Core: Transaction and Wallet primitives.

Design principles:
- Every transaction is signed with Ed25519 (fast, small signatures, well-audited).
- Every transaction carries a strictly-increasing per-sender nonce to prevent replay.
- Transactions are immutable once created; signature covers the full payload.
- No transaction references a "current balance" from a live server -- offline
  wallets track their own believed balance and enforce a hard offline spending cap.
"""

from __future__ import annotations

import os
import json
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional

import nacl.signing
import nacl.encoding
from nacl.exceptions import BadSignatureError


class InsufficientOfflineBalance(Exception):
    """Raised when a transaction would exceed the wallet's known/offline balance."""


class OfflineCapExceeded(Exception):
    """Raised when a transaction would push the wallet's cumulative offline
    spend past its hard offline cap (see docs/PROTOCOL.md)."""


class InvalidTransaction(Exception):
    """Raised when a transaction fails signature or structural validation."""


@dataclass(frozen=True)
class Transaction:
    """An immutable, signed P2P transaction.

    sender_pub / recipient_pub are hex-encoded Ed25519 public keys.
    nonce is the sender's strictly-increasing transaction counter.
    amount is in the smallest currency unit (paise) to avoid float issues.
    """
    sender_pub: str
    recipient_pub: str
    amount: int  # paise
    nonce: int
    timestamp: float
    signature: Optional[str] = field(default=None, compare=False)
    txn_id: str = field(default="", compare=False)

    # Domain separator: binds every signature to this specific protocol and
    # version, so a valid ROTM transaction signature can never be replayed
    # as a valid message in a different protocol/context that happens to
    # share the same signing key (a real risk if the same Ed25519 keypair
    # is ever reused across apps -- discovered in code review, see
    # results/code_review.md).
    DOMAIN_SEPARATOR = b"ROTM-TXN-v1:"

    def signing_payload(self) -> bytes:
        """Canonical bytes that get signed -- excludes signature and txn_id."""
        payload = {
            "sender_pub": self.sender_pub,
            "recipient_pub": self.recipient_pub,
            "amount": self.amount,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
        }
        return self.DOMAIN_SEPARATOR + json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    def compute_id(self) -> str:
        """Deterministic transaction ID derived from the signed payload."""
        return hashlib.sha256(self.signing_payload() + (self.signature or "").encode()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Transaction":
        return Transaction(**d)


class Wallet:
    """A single offline-capable wallet identity + local ledger view."""

    def __init__(self, offline_cap_paise: int = 200_000, seed: Optional[bytes] = None):
        """
        offline_cap_paise: hard cap on cumulative spend allowed while offline
                            since the last successful sync (default Rs. 2000).
        seed: optional 32-byte seed for deterministic keys (testing only).
        """
        self.signing_key = nacl.signing.SigningKey(seed) if seed else nacl.signing.SigningKey.generate()
        self.verify_key = self.signing_key.verify_key
        self.pubkey_hex = self.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()

        self.balance_paise: int = 0          # last known-good balance (from last sync)
        self.nonce: int = 0                  # next nonce to use
        self.offline_cap_paise: int = offline_cap_paise
        self.offline_spent_paise: int = 0    # cumulative spend since last sync
        self.outbox: list[Transaction] = []  # signed txns not yet synced anywhere

    def fund(self, amount_paise: int) -> None:
        """Simulates a sync event that confirms new balance (e.g. after reconnecting)."""
        self.balance_paise += amount_paise
        self.offline_spent_paise = 0  # cap resets on confirmed sync

    def create_transaction(self, recipient_pub: str, amount_paise: int) -> Transaction:
        if amount_paise <= 0:
            raise InvalidTransaction("Amount must be positive")

        if amount_paise > self.balance_paise:
            raise InsufficientOfflineBalance(
                f"Amount {amount_paise} exceeds known balance {self.balance_paise}"
            )

        projected_spend = self.offline_spent_paise + amount_paise
        if projected_spend > self.offline_cap_paise:
            raise OfflineCapExceeded(
                f"Offline spend {projected_spend} would exceed cap {self.offline_cap_paise}. "
                f"Sync to a server or trusted node to reset the cap."
            )

        txn = Transaction(
            sender_pub=self.pubkey_hex,
            recipient_pub=recipient_pub,
            amount=amount_paise,
            nonce=self.nonce,
            timestamp=time.time(),
        )

        signature = self.signing_key.sign(txn.signing_payload()).signature.hex()
        txn = Transaction(
            sender_pub=txn.sender_pub,
            recipient_pub=txn.recipient_pub,
            amount=txn.amount,
            nonce=txn.nonce,
            timestamp=txn.timestamp,
            signature=signature,
        )
        txn_id = txn.compute_id()
        txn = Transaction(**{**txn.to_dict(), "txn_id": txn_id})

        # Optimistically apply locally -- this is what enables offline spend,
        # and is exactly the assumption that creates double-spend risk,
        # which the sync/detection layer exists to catch.
        self.balance_paise -= amount_paise
        self.offline_spent_paise += amount_paise
        self.nonce += 1
        self.outbox.append(txn)

        return txn

    @staticmethod
    def verify_transaction(txn: Transaction) -> bool:
        """Verifies signature integrity only -- does NOT check balance/double-spend.
        That's the ledger/detection layer's job (see sync/ledger.py)."""
        if not txn.signature:
            return False
        try:
            verify_key = nacl.signing.VerifyKey(txn.sender_pub, encoder=nacl.encoding.HexEncoder)
            verify_key.verify(txn.signing_payload(), bytes.fromhex(txn.signature))
            return True
        except (BadSignatureError, ValueError):
            return False

    def save_state(self, filepath: str) -> None:
        """Persist wallet state (nonce, balance, cap, spent, key seed, outbox) to a local JSON file."""
        seed_hex = bytes(self.signing_key).hex()
        data = {
            "pubkey_hex": self.pubkey_hex,
            "seed_hex": seed_hex,
            "balance_paise": self.balance_paise,
            "nonce": self.nonce,
            "offline_cap_paise": self.offline_cap_paise,
            "offline_spent_paise": self.offline_spent_paise,
            "outbox": [t.to_dict() for t in self.outbox],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_state(self, filepath: str) -> None:
        """Load wallet state from a local JSON file if present."""
        if not os.path.exists(filepath):
            return
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "seed_hex" in data:
            seed_bytes = bytes.fromhex(data["seed_hex"])
            self.signing_key = nacl.signing.SigningKey(seed_bytes)
            self.verify_key = self.signing_key.verify_key
            self.pubkey_hex = self.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()

        self.balance_paise = data.get("balance_paise", self.balance_paise)
        self.nonce = data.get("nonce", self.nonce)
        self.offline_cap_paise = data.get("offline_cap_paise", self.offline_cap_paise)
        self.offline_spent_paise = data.get("offline_spent_paise", self.offline_spent_paise)
        if "outbox" in data:
            self.outbox = [Transaction.from_dict(t) for t in data["outbox"]]

    @classmethod
    def from_state_file(cls, filepath: str) -> "Wallet":
        """Factory method to load a Wallet instance directly from a saved state file."""
        wallet = cls()
        wallet.load_state(filepath)
        return wallet
