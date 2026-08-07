"""
ROTM Mesh Simulator: models N phones exchanging transactions device-to-device
while offline, then periodically "meeting" (simulating Bluetooth/WiFi Direct
range) and merging ledgers. Produces the benchmark data your paper needs:

  - detection latency (hops / simulated time) vs. offline cap size
  - conflict rate vs. % of malicious/double-spending nodes
  - throughput (txns/sec) under varying mesh density
  - Sybil resistance effectiveness vs. relay withholding attacks

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
    sybil_resistance_stats: dict = field(default_factory=dict)


@dataclass
class SybilSimResult:
    n_nodes: int
    n_sybil_relays: int
    withholding_rate: float
    total_transactions: int
    total_conflict_detections: int
    unique_conflicts_estimate: int
    sybil_resistance_stats: dict = field(default_factory=dict)


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
            # Register both nodes as relays for each other
            ledgers[a].register_relay(wallets[b].pubkey_hex)
            ledgers[b].register_relay(wallets[a].pubkey_hex)
            
            conflicts = ledgers[a].merge(ledgers[b], relay_pub=wallets[b].pubkey_hex)
            total_conflicts += len(conflicts)
            # After meeting, b also gets a's view (bidirectional sync).
            ledgers[b].merge(ledgers[a], relay_pub=wallets[a].pubkey_hex)

    all_hops = [c.hops_to_detect for ledger in ledgers for c in ledger.conflicts]

    # Aggregate Sybil resistance stats from all ledgers
    sybil_stats = {}
    for ledger in ledgers:
        stats = ledger.get_sybil_resistance_stats()
        for key, value in stats.items():
            if key not in sybil_stats:
                sybil_stats[key] = []
            sybil_stats[key].append(value)
    
    # Average the stats
    avg_sybil_stats = {
        key: statistics.mean(values) if values else 0.0
        for key, values in sybil_stats.items()
    }

    return SimResult(
        n_nodes=n_nodes,
        n_malicious=n_malicious,
        offline_cap_paise=offline_cap_paise,
        total_transactions=total_txns,
        total_conflicts=total_conflicts,
        conflict_rate=(total_conflicts / total_txns) if total_txns else 0.0,
        avg_hops_to_detect=statistics.mean(all_hops) if all_hops else 0.0,
        max_hops_to_detect=max(all_hops) if all_hops else 0,
        sybil_resistance_stats=avg_sybil_stats,
    )


def run_sybil_resistance_simulation(
    n_nodes: int = 20,
    n_sybil_relays: int = 5,
    withholding_rate: float = 0.3,
    rounds: int = 40,
    meetings_per_round: int = 10,
    starting_balance_paise: int = 500_000,
    seed: int = 42,
) -> SybilSimResult:
    """
    Simulates Sybil relay attacks where malicious relays selectively withhold
    transactions to delay conflict detection.
    
    n_nodes: total phones in the mesh
    n_sybil_relays: how many nodes act as malicious relays (withholding transactions)
    withholding_rate: probability that a Sybil relay withholds a transaction
    rounds: simulated time steps
    meetings_per_round: how many pairwise device "encounters" happen per round
    """
    random.seed(seed)

    wallets = [Wallet(offline_cap_paise=200_000) for _ in range(n_nodes)]
    for w in wallets:
        w.fund(starting_balance_paise)

    ledgers = [Ledger() for _ in range(n_nodes)]
    for i, ledger in enumerate(ledgers):
        for w in wallets:
            ledger.set_known_balance(w.pubkey_hex, starting_balance_paise)

    # Select Sybil relay nodes
    sybil_relay_idx = set(random.sample(range(n_nodes), min(n_sybil_relays, n_nodes)))

    total_conflict_detections = 0
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

                    # Simulate double-spend attack
                    if random.random() < 0.3:  # 30% chance of double-spend attempt
                        wallet.balance_paise += amount
                        wallet.nonce -= 1
                        other_recipient_idx = random.choice(
                            [j for j in range(n_nodes) if j != i and wallets[j] != recipient]
                        )
                        other_recipient = wallets[other_recipient_idx]
                        dupe_txn = wallet.create_transaction(other_recipient.pubkey_hex, amount)
                        ledgers[other_recipient_idx].submit(dupe_txn)
                        total_txns += 1
                except Exception:
                    continue

        # Simulate pairwise mesh "meetings" with Sybil relay behavior
        for _ in range(meetings_per_round):
            a, b = random.sample(range(n_nodes), 2)
            
            # Register both nodes as relays for each other
            ledgers[a].register_relay(wallets[b].pubkey_hex)
            ledgers[b].register_relay(wallets[a].pubkey_hex)
            
            # Check if either node is a Sybil relay
            a_is_sybil = a in sybil_relay_idx
            b_is_sybil = b in sybil_relay_idx
            
            # Determine if relays will withhold transactions
            a_withholds = a_is_sybil and random.random() < withholding_rate
            b_withholds = b_is_sybil and random.random() < withholding_rate
            
            # Perform merge with potential withholding
            if not a_withholds:
                conflicts = ledgers[a].merge(ledgers[b], relay_pub=wallets[b].pubkey_hex)
                total_conflict_detections += len(conflicts)
            else:
                # Sybil relay withholds - don't merge
                pass
            
            if not b_withholds:
                ledgers[b].merge(ledgers[a], relay_pub=wallets[a].pubkey_hex)
            else:
                # Sybil relay withholds - don't merge
                pass

    # Deduplicate conflicts by counting distinct sender_pub+rejected_txn_id pairs
    # across all ledgers' conflict lists
    unique_conflict_keys = set()
    for ledger in ledgers:
        for conflict in ledger.conflicts:
            unique_conflict_keys.add((conflict.sender_pub, conflict.rejected_txn_id))
    unique_conflicts_estimate = len(unique_conflict_keys)

    # Aggregate Sybil resistance stats from all ledgers
    # Note: diversity_warnings is always 0 because get_diversity_warning() is never
    # called during the simulation. Warnings are generated on-demand when explicitly
    # queried, not automatically during transaction processing. This is expected
    # behavior - the warning system is designed to be queried by applications
    # when they need to display alerts to users, not to accumulate during normal
    # operation.
    sybil_stats = {}
    for ledger in ledgers:
        stats = ledger.get_sybil_resistance_stats()
        for key, value in stats.items():
            if key not in sybil_stats:
                sybil_stats[key] = []
            sybil_stats[key].append(value)
    
    # For relay_count, we need to count distinct relay identities across all ledgers,
    # not average per-ledger counts (which produces fractional values)
    all_relay_pubs = set()
    for ledger in ledgers:
        all_relay_pubs.update(ledger.relay_reputations.keys())
    
    # Average the other stats
    avg_sybil_stats = {
        key: statistics.mean(values) if values else 0.0
        for key, values in sybil_stats.items()
    }
    # Override relay_count with the correct whole-number count of distinct relays
    avg_sybil_stats["relay_count"] = len(all_relay_pubs)

    return SybilSimResult(
        n_nodes=n_nodes,
        n_sybil_relays=n_sybil_relays,
        withholding_rate=withholding_rate,
        total_transactions=total_txns,
        total_conflict_detections=total_conflict_detections,
        unique_conflicts_estimate=unique_conflicts_estimate,
        sybil_resistance_stats=avg_sybil_stats,
    )


def run_sybil_resistance_sweep():
    """Runs run_sybil_resistance_simulation() across withholding_rate values
    [0.1, 0.2, 0.3, 0.4, 0.5] with n_sybil_relays=5, and writes real captured
    output to results/week5_sybil_resistance.md."""
    withholding_rates = [0.1, 0.2, 0.3, 0.4, 0.5]
    results = []
    
    for rate in withholding_rates:
        result = run_sybil_resistance_simulation(
            n_nodes=20,
            n_sybil_relays=5,
            withholding_rate=rate,
            rounds=40,
            meetings_per_round=10,
            starting_balance_paise=500_000,
            seed=42,
        )
        results.append(result)
    
    # Write results to markdown file
    with open("results/week5_sybil_resistance.md", "w") as f:
        f.write("# Sybil Resistance Simulation Results\n\n")
        f.write("## Withholding Rate Sweep (n_sybil_relays=5, n_nodes=20, rounds=40)\n\n")
        f.write("| Withholding Rate | Total Transactions | Conflict Detections | Unique Conflicts | Relay Count | Avg Reputation | Network Trust Score | Max Single Relay Influence |\n")
        f.write("|------------------|--------------------|---------------------|------------------|-------------|----------------|---------------------|----------------------------|\n")
        for result in results:
            stats = result.sybil_resistance_stats
            f.write(f"| {result.withholding_rate} | {result.total_transactions} | {result.total_conflict_detections} | {result.unique_conflicts_estimate} | {stats['relay_count']} | {stats['avg_reputation']:.4f} | {stats['network_trust_score']:.4f} | {stats['max_single_relay_influence']:.4f} |\n")
    
    # Print summary to stdout
    print("Sybil resistance sweep complete. Results written to results/week5_sybil_resistance.md")
    print("\nSummary:")
    print(f"{'Rate':>6} | {'Txns':>6} | {'Detections':>10} | {'Unique':>7} | {'Relays':>7} | {'AvgRep':>7} | {'Trust':>7} | {'MaxInfl':>7}")
    print("-" * 75)
    for result in results:
        stats = result.sybil_resistance_stats
        print(f"{result.withholding_rate:>6.1f} | {result.total_transactions:>6} | {result.total_conflict_detections:>10} | {result.unique_conflicts_estimate:>7} | {stats['relay_count']:>7} | {stats['avg_reputation']:>7.4f} | {stats['network_trust_score']:>7.4f} | {stats['max_single_relay_influence']:>7.4f}")


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
