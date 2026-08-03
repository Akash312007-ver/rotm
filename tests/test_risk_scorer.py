"""
Test script for LocalLLMRiskScorer with LM Studio + Gemma 3 4B.
"""

import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.transaction import Wallet
from detection.risk_scorer import LocalLLMRiskScorer

def main():
    print("=" * 60)
    print("Initializing LocalLLMRiskScorer (connecting to LM Studio)...")
    print("=" * 60)
    
    # Initialize scorer with Gemma 3 4B and 15s timeout for local inference
    scorer = LocalLLMRiskScorer(
        endpoint="http://localhost:1234/v1/chat/completions",
        model="google/gemma-3-4b",
        timeout_s=15.0
    )
    
    # Setup Wallets
    alice = Wallet(offline_cap_paise=200_000) # Rs 2,000 cap
    alice.fund(500_000)                        # Rs 5,000 balance
    
    bob = Wallet()
    carol = Wallet()
    dave = Wallet()
    
    # Establish a normal transaction history profile for Alice (3-4 small txns to Bob)
    print("\n--- Establishing Alice's baseline transaction history ---")
    baseline_amounts = [5_000, 5_500, 4_800, 5_200] # ~Rs 50 average
    for amt in baseline_amounts:
        txn = alice.create_transaction(bob.pubkey_hex, amt)
        # Assess baseline to build profile
        scorer.assess(txn, offline_cap_paise=alice.offline_cap_paise, cumulative_offline_spend=alice.offline_spent_paise)
        print(f"Observed baseline txn: Rs {amt/100:.2f} to Bob")
        
    print("\n" + "=" * 60)
    print("TESTING SAMPLE TRANSACTIONS WITH LOCAL LLM RISK SCORER")
    print("=" * 60 + "\n")
    
    # Sample Transaction 1: Normal transaction consistent with history
    txn1 = alice.create_transaction(bob.pubkey_hex, 5_100) # Rs 51
    res1 = scorer.assess(txn1, offline_cap_paise=alice.offline_cap_paise, cumulative_offline_spend=alice.offline_spent_paise)
    print(f"Sample 1 [Normal Txn to Known Recipient]:")
    print(f"  Txn ID:       {res1.txn_id[:12]}...")
    print(f"  Amount:       Rs {txn1.amount/100:.2f}")
    print(f"  Risk Score:   {res1.risk_score}")
    print(f"  Used LLM:     {res1.used_llm}")
    print(f"  Reasons:      {res1.reasons}")
    print("-" * 50)
    
    # Sample Transaction 2: First transaction to a new recipient (Carol)
    txn2 = alice.create_transaction(carol.pubkey_hex, 6_000) # Rs 60
    res2 = scorer.assess(txn2, offline_cap_paise=alice.offline_cap_paise, cumulative_offline_spend=alice.offline_spent_paise)
    print(f"Sample 2 [Transaction to New Recipient]:")
    print(f"  Txn ID:       {res2.txn_id[:12]}...")
    print(f"  Amount:       Rs {txn2.amount/100:.2f}")
    print(f"  Risk Score:   {res2.risk_score}")
    print(f"  Used LLM:     {res2.used_llm}")
    print(f"  Reasons:      {res2.reasons}")
    print("-" * 50)

    # Sample Transaction 3: Anomalously large amount (Rs 450 - many std dev above mean)
    txn3 = alice.create_transaction(dave.pubkey_hex, 45_000) # Rs 450
    res3 = scorer.assess(txn3, offline_cap_paise=alice.offline_cap_paise, cumulative_offline_spend=alice.offline_spent_paise)
    print(f"Sample 3 [Anomalously Large Amount to New Recipient]:")
    print(f"  Txn ID:       {res3.txn_id[:12]}...")
    print(f"  Amount:       Rs {txn3.amount/100:.2f}")
    print(f"  Risk Score:   {res3.risk_score}")
    print(f"  Used LLM:     {res3.used_llm}")
    print(f"  Reasons:      {res3.reasons}")
    print("-" * 50)

    # Sample Transaction 4: High Offline Cap Usage / Cap Draining Pattern
    # Alice's cap is 100_000 paise (Rs 1,000). Total spent so far = 5,100 + 6,000 + 45,000 = 56,100.
    # New transaction of 35,000 (Rs 350) brings total spent to 91,100 (> 80% of offline cap).
    txn4 = alice.create_transaction(bob.pubkey_hex, 35_000) # Rs 350
    res4 = scorer.assess(txn4, offline_cap_paise=alice.offline_cap_paise, cumulative_offline_spend=alice.offline_spent_paise)
    print(f"Sample 4 [High Offline Cap Spend (>80% Cap Used)]:")
    print(f"  Txn ID:       {res4.txn_id[:12]}...")
    print(f"  Amount:       Rs {txn4.amount/100:.2f}")
    print(f"  Cumulative:   Rs {alice.offline_spent_paise/100:.2f} / Rs {alice.offline_cap_paise/100:.2f}")
    print(f"  Risk Score:   {res4.risk_score}")
    print(f"  Used LLM:     {res4.used_llm}")
    print(f"  Reasons:      {res4.reasons}")
    print("=" * 60)

if __name__ == "__main__":
    main()
