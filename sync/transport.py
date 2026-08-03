"""
ROTM Transport Layer: Device-to-Device P2P Transport Simulator.

Simulates Bluetooth / Wi-Fi Direct peer-to-peer sync between offline devices
using framed TCP sockets over localhost.
"""

from __future__ import annotations

import json
import socket
import struct
import threading
import time
from typing import Optional, Tuple, List, Dict, Any

from core.transaction import Transaction, Wallet
from sync.ledger import Ledger, ConflictRecord
from detection.risk_scorer import LocalLLMRiskScorer, RiskAssessment


MAX_FRAME_SIZE = 10 * 1024 * 1024  # 10 MB maximum allowed payload frame size


class TransportError(Exception):
    """Raised on socket framing, serialization, or network errors."""


def send_framed_message(sock: socket.socket, msg: dict[str, Any]) -> None:
    """Send a length-prefixed JSON message over a socket."""
    payload = json.dumps(msg).encode("utf-8")
    header = struct.pack(">I", len(payload))
    sock.sendall(header + payload)


def recv_framed_message(sock: socket.socket, timeout_s: float = 5.0) -> dict[str, Any]:
    """Receive a length-prefixed JSON message from a socket."""
    sock.settimeout(timeout_s)
    header_bytes = b""
    while len(header_bytes) < 4:
        chunk = sock.recv(4 - len(header_bytes))
        if not chunk:
            raise TransportError("Connection closed before complete header received")
        header_bytes += chunk
    
    payload_len = struct.unpack(">I", header_bytes)[0]
    if payload_len > MAX_FRAME_SIZE:
        raise TransportError(f"Incoming payload size ({payload_len} bytes) exceeds MAX_FRAME_SIZE ({MAX_FRAME_SIZE} bytes)")

    payload_bytes = b""
    while len(payload_bytes) < payload_len:
        chunk = sock.recv(min(4096, payload_len - len(payload_bytes)))
        if not chunk:
            raise TransportError("Connection closed before complete payload received")
        payload_bytes += chunk
        
    return json.loads(payload_bytes.decode("utf-8"))


class DeviceNode:
    """Represents an offline device running a ROTM wallet + local ledger.
    Can act as a server (listening for incoming P2P connections) and/or client
    (initiating P2P connections to peers).
    """

    def __init__(self, node_id: str, wallet: Optional[Wallet] = None,
                 risk_scorer: Optional[LocalLLMRiskScorer] = None):
        self.node_id = node_id
        self.wallet = wallet or Wallet()
        self.ledger = Ledger()
        self.risk_scorer = risk_scorer
        self._server_sock: Optional[socket.socket] = None
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        self.port: int = 0
        self.risk_assessments: list[RiskAssessment] = []

    def start_server(self, host: str = "127.0.0.1", port: int = 0) -> int:
        """Start local P2P server socket listener in a background thread."""
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((host, port))
        self._server_sock.listen(5)
        self.port = self._server_sock.getsockname()[1]
        self._running = True

        self._server_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._server_thread.start()
        return self.port

    def stop_server(self) -> None:
        """Stop local P2P server socket listener."""
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=1.0)

    def _accept_loop(self) -> None:
        while self._running and self._server_sock:
            try:
                self._server_sock.settimeout(0.5)
                client_sock, addr = self._server_sock.accept()
                threading.Thread(target=self._handle_client, args=(client_sock,), daemon=True).start()
            except (socket.timeout, OSError):
                continue

    def _handle_client(self, sock: socket.socket) -> None:
        try:
            with sock:
                # 1. Receive handshake
                msg = recv_framed_message(sock)
                if msg.get("type") != "HANDSHAKE":
                    send_framed_message(sock, {"type": "ERROR", "message": "Expected HANDSHAKE"})
                    return
                
                peer_node_id = msg.get("node_id", "unknown")
                send_framed_message(sock, {"type": "HANDSHAKE_ACK", "node_id": self.node_id, "status": "ok"})

                # 2. Receive peer's transactions
                sync_msg = recv_framed_message(sock)
                if sync_msg.get("type") != "SYNC_TXNS":
                    send_framed_message(sock, {"type": "ERROR", "message": "Expected SYNC_TXNS"})
                    return

                peer_txns = [Transaction.from_dict(d) for d in sync_msg.get("transactions", [])]
                
                # Submit peer transactions to local ledger & assess risk
                accepted_count = 0
                conflicts_count = 0
                for txn in peer_txns:
                    accepted, conflict = self.ledger.submit(txn)
                    if accepted:
                        accepted_count += 1
                        if self.risk_scorer:
                            ra = self.risk_scorer.assess(
                                txn,
                                offline_cap_paise=self.wallet.offline_cap_paise,
                                cumulative_offline_spend=self.wallet.offline_spent_paise
                            )
                            self.risk_assessments.append(ra)
                    if conflict:
                        conflicts_count += 1

                # 3. Respond with our local ledger entries to complete bidirectional sync
                our_txns = [entry.txn.to_dict() for entry in self.ledger.entries.values()]
                send_framed_message(sock, {
                    "type": "SYNC_ACK",
                    "accepted_count": accepted_count,
                    "conflicts_count": conflicts_count,
                    "returned_transactions": our_txns,
                })
        except Exception:
            pass

    def sync_with_peer(self, host: str, port: int, timeout_s: float = 5.0) -> dict[str, Any]:
        """Initiate P2P sync connection to a peer device node."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_s)
        try:
            sock.connect((host, port))
            # 1. Send Handshake
            send_framed_message(sock, {"type": "HANDSHAKE", "node_id": self.node_id, "pubkey": self.wallet.pubkey_hex})
            ack = recv_framed_message(sock)
            if ack.get("type") != "HANDSHAKE_ACK":
                raise TransportError(f"Handshake failed: {ack}")

            # 2. Send our ledger transactions
            our_txns = [entry.txn.to_dict() for entry in self.ledger.entries.values()]
            send_framed_message(sock, {"type": "SYNC_TXNS", "transactions": our_txns})

            # 3. Receive peer response with returned transactions
            resp = recv_framed_message(sock)
            if resp.get("type") != "SYNC_ACK":
                raise TransportError(f"Sync failed: {resp}")

            peer_txns = [Transaction.from_dict(d) for d in resp.get("returned_transactions", [])]
            for txn in peer_txns:
                accepted, conflict = self.ledger.submit(txn)
                if accepted and self.risk_scorer:
                    ra = self.risk_scorer.assess(
                        txn,
                        offline_cap_paise=self.wallet.offline_cap_paise,
                        cumulative_offline_spend=self.wallet.offline_spent_paise
                    )
                    self.risk_assessments.append(ra)

            return {
                "peer_node_id": ack.get("node_id"),
                "peer_accepted_count": resp.get("accepted_count"),
                "peer_conflicts_count": resp.get("conflicts_count"),
                "received_txns_count": len(peer_txns),
            }
        finally:
            sock.close()
