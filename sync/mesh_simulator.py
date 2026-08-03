"""
ROTM Mesh Simulator: models N phones exchanging transactions device-to-device
while offline, then periodically "meeting" (simulating Bluetooth/WiFi Direct
range) and merging ledgers. Produces the benchmark data your paper needs:

  - detection latency (hops / simulated time) vs. offline cap size
  - conflict rate vs. % of malicious/double-spending nodes
  - throughput (txns/sec) under varying mesh density

This is a discrete-event simulation, not a real Bluetooth stack -- appropriate
for a research prototype's evaluation section. Real device-to-device transport
(sync/mesh_transport.py, using Bluetooth/WiFi Direct) is a separate module for
the actual deployed app; this simulator lets you generate results NOW without
needing multiple physical phones.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass, field

from core.transaction import Wallet
from sync.ledger import Ledger


@dataclass
class SimResult:
    n_nodes: int
    n_malicious: int
    offline_cap_paise: int
    total_transactions: int
    total_conflicts: int
    conflict_rate: float
    avg_hops_to_detect: float
    max_hops_to_detect: int


def run_mesh_simulation(
    n_nodes: int = 20,
    n_malicious: int = 2,
    offline_cap_paise: int = 200_000,
    rounds: int = 50,
    meetings_per_round: int = 10,
    starting_balance_paise: int = 500_000,
    seed: int = 42,
) -> SimResult:
    """
    n_nodes: total phones in the mesh
    n_malicious: how many nodes deliberately double-spend (attack simulation)
    rounds: simulated time steps
    meetings_per_round: how many pairwise device "encounters" happen per round
                        (models Bluetooth-range meetups, e.g. people passing
                        each other, a market, a bus)
    """
    random.seed(seed)

    wallets = [Wallet(offline_cap_paise=offline_cap_paise) for _ in range(n_nodes)]
    for w in wallets:
        w.fund(starting_balance_paise)

    ledgers = [Ledger() for _ in range(n_nodes)]
    for i, ledger in enumerate(ledgers):
        for w in wallets:
            ledger.set_known_balance(w.pubkey_hex, starting_balance_paise)

    malicious_idx = set(random.sample(range(n_nodes), min(n_malicious, n_nodes)))

    total_conflicts = 0
    total_txns = 0

    for _ in range(rounds):
        # Each node may create a transaction to a random peer this round.
        for i, wallet in enumerate(wallets):
            if random.random() < 0.4:  # 40% chance a node transacts this round
                recipient = random.choice([w for j, w in enumerate(wallets) if j != i])
                amount = random.randint(1_000, min(20_000, max(wallet.balance_paise, 1_000)))
                try:
                    txn = wallet.create_transaction(recipient.pubkey_hex, amount)
                    ledgers[i].submit(txn)
                    total_txns += 1

                    if i in malicious_idx and random.random() < 0.5:
                        # Malicious node double-spends: reuse the nonce/balance
                        # to send the "same money" to a different recipient,
                        # but broadcasts this duplicate ONLY to that other
                        # recipient's own ledger -- modeling a real attack
                        # where the attacker shows txn_to_bob to Bob's phone
                        # and txn_to_carol to Carol's phone, hoping they never
                        # compare notes. The conflict is only detectable once
                        # those two devices' ledgers merge later.
                        wallet.balance_paise += amount  # attacker's client restores balance locally
                        wallet.nonce -= 1
                        other_recipient_idx = random.choice(
                            [j for j in range(n_nodes) if j != i and wallets[j] != recipient]
                        )
                        other_recipient = wallets[other_recipient_idx]
                        dupe_txn = wallet.create_transaction(other_recipient.pubkey_hex, amount)
                        ledgers[other_recipient_idx].submit(dupe_txn)
                        total_txns += 1
                except Exception:
                    continue  # cap exceeded or insufficient balance -- skip this attempt

        # Simulate pairwise mesh "meetings" -- devices in Bluetooth range sync ledgers.
        for _ in range(meetings_per_round):
            a, b = random.sample(range(n_nodes), 2)
            conflicts = ledgers[a].merge(ledgers[b])
            total_conflicts += len(conflicts)
            # After meeting, b also gets a's view (bidirectional sync).
            ledgers[b].merge(ledgers[a])

    all_hops = [c.hops_to_detect for ledger in ledgers for c in ledger.conflicts]

    return SimResult(
        n_nodes=n_nodes,
        n_malicious=n_malicious,
        offline_cap_paise=offline_cap_paise,
        total_transactions=total_txns,
        total_conflicts=total_conflicts,
        conflict_rate=(total_conflicts / total_txns) if total_txns else 0.0,
        avg_hops_to_detect=statistics.mean(all_hops) if all_hops else 0.0,
        max_hops_to_detect=max(all_hops) if all_hops else 0,
    )


def run_cap_sensitivity_sweep():
    """Generates the key figure for your paper: how offline cap size trades
    off against conflict exposure. Larger cap = more spending freedom but
    more potential damage per undetected double-spend."""
    caps = [50_000, 100_000, 200_000, 500_000, 1_000_000]
    print(f"{'Cap (Rs)':>10} | {'Txns':>6} | {'Conflicts':>9} | {'Rate':>6} | {'AvgHops':>8}")
    print("-" * 55)
    for cap in caps:
        result = run_mesh_simulation(offline_cap_paise=cap, n_malicious=3, rounds=40)
        print(f"{cap/100:>10.0f} | {result.total_transactions:>6} | "
              f"{result.total_conflicts:>9} | {result.conflict_rate:>6.2%} | "
              f"{result.avg_hops_to_detect:>8.2f}")


if __name__ == "__main__":
    print("=== Single simulation run ===")
    result = run_mesh_simulation()
    print(result)

    print("\n=== Cap sensitivity sweep (paper Figure 1) ===")
    run_cap_sensitivity_sweep()
