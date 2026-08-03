"""
Unit & Integration Tests for ROTM Device-to-Device Socket Transport.

Run with: python tests/test_transport.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.transaction import Wallet, Transaction
from sync.transport import DeviceNode, TransportError
from sync.ledger import Ledger


def test_socket_transport_successful_sync():
    # 1. Setup two device nodes
    alice_node = DeviceNode(node_id="device_alice")
    bob_node = DeviceNode(node_id="device_bob")

    alice_node.wallet.fund(100_000) # Rs 1,000
    bob_node.wallet.fund(50_000)   # Rs 500

    # Start Bob's server listener
    bob_port = bob_node.start_server(host="127.0.0.1", port=0)

    try:
        # Alice creates an offline transaction to Bob
        txn = alice_node.wallet.create_transaction(bob_node.wallet.pubkey_hex, 15_000) # Rs 150
        alice_node.ledger.submit(txn)

        # Alice connects to Bob over socket and syncs
        result = alice_node.sync_with_peer("127.0.0.1", bob_port)

        # Assertions
        assert result["peer_node_id"] == "device_bob"
        assert result["peer_accepted_count"] == 1
        assert txn.txn_id in bob_node.ledger.entries
        assert Wallet.verify_transaction(bob_node.ledger.entries[txn.txn_id].txn)
        print("[PASS] test_socket_transport_successful_sync")
    finally:
        bob_node.stop_server()


def test_bidirectional_sync():
    alice_node = DeviceNode(node_id="device_alice")
    bob_node = DeviceNode(node_id="device_bob")

    alice_node.wallet.fund(100_000)
    bob_node.wallet.fund(100_000)

    bob_port = bob_node.start_server(host="127.0.0.1", port=0)

    try:
        # Alice spends Rs 200 to Bob
        t1 = alice_node.wallet.create_transaction(bob_node.wallet.pubkey_hex, 20_000)
        alice_node.ledger.submit(t1)

        # Bob spends Rs 100 to Alice
        t2 = bob_node.wallet.create_transaction(alice_node.wallet.pubkey_hex, 10_000)
        bob_node.ledger.submit(t2)

        # Alice syncs with Bob
        alice_node.sync_with_peer("127.0.0.1", bob_port)

        # Both nodes should have both transactions in their ledger
        assert t1.txn_id in alice_node.ledger.entries
        assert t2.txn_id in alice_node.ledger.entries
        assert t1.txn_id in bob_node.ledger.entries
        assert t2.txn_id in bob_node.ledger.entries

        print("[PASS] test_bidirectional_sync")
    finally:
        bob_node.stop_server()


def test_socket_transport_double_spend_conflict_detected():
    # Simulate Alice double-spending to Bob and Carol
    alice_wallet = Wallet(offline_cap_paise=1_000_000)
    alice_wallet.fund(50_000) # Rs 500

    bob_node = DeviceNode(node_id="device_bob")
    carol_node = DeviceNode(node_id="device_carol")

    bob_node.ledger.set_known_balance(alice_wallet.pubkey_hex, 50_000)
    carol_node.ledger.set_known_balance(alice_wallet.pubkey_hex, 50_000)

    # Alice creates T1 to Bob (nonce 0)
    txn_to_bob = alice_wallet.create_transaction(bob_node.wallet.pubkey_hex, 50_000)
    bob_node.ledger.submit(txn_to_bob)

    # Alice tampers state to double-spend T2 to Carol with same nonce 0
    alice_wallet.balance_paise = 50_000
    alice_wallet.nonce = 0
    txn_to_carol = alice_wallet.create_transaction(carol_node.wallet.pubkey_hex, 50_000)
    carol_node.ledger.submit(txn_to_carol)

    # Start Carol's P2P server
    carol_port = carol_node.start_server(host="127.0.0.1", port=0)

    try:
        # Bob meets Carol (e.g. over Bluetooth) and syncs over socket
        result = bob_node.sync_with_peer("127.0.0.1", carol_port)

        # Assert conflict is detected
        assert len(bob_node.ledger.conflicts) == 1
        assert len(carol_node.ledger.conflicts) == 1
        assert bob_node.ledger.conflicts[0].sender_pub == alice_wallet.pubkey_hex
        assert carol_node.ledger.conflicts[0].sender_pub == alice_wallet.pubkey_hex

        print(f"[PASS] test_socket_transport_double_spend_conflict_detected "
              f"(conflicts_detected={len(bob_node.ledger.conflicts)})")
    finally:
        carol_node.stop_server()


def test_max_frame_size_enforced():
    import socket
    import struct
    import threading
    from sync.transport import recv_framed_message, TransportError

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    def client():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", port))
        # Send 15 MB length header (> 10MB cap)
        s.sendall(struct.pack(">I", 15 * 1024 * 1024))
        s.close()

    t = threading.Thread(target=client)
    t.start()

    conn, _ = server_sock.accept()
    try:
        try:
            recv_framed_message(conn)
            assert False, "Should have raised TransportError for frame size > MAX_FRAME_SIZE"
        except TransportError as e:
            assert "exceeds MAX_FRAME_SIZE" in str(e)
            print("[PASS] test_max_frame_size_enforced")
    finally:
        conn.close()
        server_sock.close()
        t.join()


if __name__ == "__main__":
    test_socket_transport_successful_sync()
    test_bidirectional_sync()
    test_socket_transport_double_spend_conflict_detected()
    test_max_frame_size_enforced()
    print("\nAll transport tests passed.")
