"""
ROTM Device-to-Device Transport Simulation Script.

Simulates two offline mobile devices (Node A and Node B) running in separate
socket threads/processes on localhost exchanging transactions and merging ledgers
via framed TCP socket transport.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.transaction import Wallet
from sync.transport import DeviceNode


def main():
    print("=" * 65)
    print("ROTM DEVICE-TO-DEVICE TRANSPORT SIMULATOR (LOCALHOST SOCKETS)")
    print("=" * 65)

    # Initialize two offline device nodes
    node_a = DeviceNode(node_id="Phone_Alice")
    node_b = DeviceNode(node_id="Phone_Bob")

    node_a.wallet.fund(200_000) # Rs 2,000 balance
    node_b.wallet.fund(100_000) # Rs 1,000 balance

    # Node B starts server listening for P2P connections (simulating BLE advertiser / Wi-Fi Direct socket)
    port_b = node_b.start_server(host="127.0.0.1", port=0)
    print(f"\n[NODE B] Listening for incoming P2P connections on 127.0.0.1:{port_b}...")

    # Node A creates 2 offline P2P payments to Node B while offline
    print("\n--- Node A creates offline transactions ---")
    txn1 = node_a.wallet.create_transaction(node_b.wallet.pubkey_hex, 25_000) # Rs 250
    node_a.ledger.submit(txn1)
    print(f"[NODE A] Created Txn 1: Rs {txn1.amount/100:.2f} (Txn ID: {txn1.txn_id[:12]}...)")

    txn2 = node_a.wallet.create_transaction(node_b.wallet.pubkey_hex, 15_000) # Rs 150
    node_a.ledger.submit(txn2)
    print(f"[NODE A] Created Txn 2: Rs {txn2.amount/100:.2f} (Txn ID: {txn2.txn_id[:12]}...)")

    # Node B creates an offline payment to Node A
    print("\n--- Node B creates offline transaction ---")
    txn3 = node_b.wallet.create_transaction(node_a.wallet.pubkey_hex, 10_000) # Rs 100
    node_b.ledger.submit(txn3)
    print(f"[NODE B] Created Txn 3: Rs {txn3.amount/100:.2f} (Txn ID: {txn3.txn_id[:12]}...)")

    # Simulate devices coming into physical range and initiating socket exchange
    print("\n--- Devices meet in physical proximity; Node A connects to Node B ---")
    sync_res = node_a.sync_with_peer("127.0.0.1", port_b)

    print(f"\n[SYNC RESULTS]")
    print(f"  Connected Peer ID:      {sync_res['peer_node_id']}")
    print(f"  Peer Accepted Txns:     {sync_res['peer_accepted_count']}")
    print(f"  Peer Conflicts:         {sync_res['peer_conflicts_count']}")
    print(f"  Received Txns Count:    {sync_res['received_txns_count']}")

    print(f"\n[FINAL LEDGER STATES]")
    print(f"  Node A Total Ledger Entries: {len(node_a.ledger.entries)}")
    print(f"  Node B Total Ledger Entries: {len(node_b.ledger.entries)}")
    print(f"  Node A Conflicts Count:      {len(node_a.ledger.conflicts)}")
    print(f"  Node B Conflicts Count:      {len(node_b.ledger.conflicts)}")

    node_b.stop_server()
    print("\n" + "=" * 65)
    print("DEVICE-TO-DEVICE TRANSPORT SIMULATION COMPLETED SUCCESSFULLY")
    print("=" * 65)


if __name__ == "__main__":
    main()
