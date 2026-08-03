# Week 1: Local LLM Risk Scoring Evaluation

## Overview & Summary

This test evaluated `LocalLLMRiskScorer` from `detection/risk_scorer.py` against a locally hosted **Gemma 3 4B** model using LM Studio (`http://localhost:1234/v1`). The ROTM (Resilient Offline Transaction Mesh) architecture uses a local LLM as an **advisory** risk scorer for offline transactions. 

The risk scorer computes a blended score between heuristic rules (z-score on amount standard deviation, recipient novelty, and offline cap spend percentage) and local LLM reasoning. In this test, a baseline transaction history was established for a sender wallet (Alice), followed by evaluating 4 distinct transaction scenarios to verify offline risk detection behavior.

---

## Test Results Summary

| Sample | Scenario | Amount (Rs) | Cumulative Spend | Risk Score | Used LLM | Flagged Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Sample 1** | Normal Transaction to Known Recipient | Rs 51.00 | Rs 51.00 / Rs 2,000 | **0.03** | `True` | Transaction amount consistent with average profile |
| **Sample 2** | First Transaction to New Recipient | Rs 60.00 | Rs 111.00 / Rs 2,000 | **0.56** | `True` | New recipient; amount 3.8 std-dev above baseline mean |
| **Sample 3** | Anomalously Large Amount to New Recipient | Rs 450.00 | Rs 561.00 / Rs 2,000 | **0.71** | `True` | 101.8 std-dev above typical transaction; unknown recipient |
| **Sample 4** | High Offline Spend | Rs 350.00 | Rs 1,116.00 / Rs 2,000 | **0.15** | `True` | Higher amount than typical history |

---

## Detailed Test Case Output

```text
============================================================
Initializing LocalLLMRiskScorer (connecting to LM Studio)...
============================================================

--- Establishing Alice's baseline transaction history ---
Observed baseline txn: Rs 50.00 to Bob
Observed baseline txn: Rs 55.00 to Bob
Observed baseline txn: Rs 48.00 to Bob
Observed baseline txn: Rs 52.00 to Bob

============================================================
TESTING SAMPLE TRANSACTIONS WITH LOCAL LLM RISK SCORER
============================================================

Sample 1 [Normal Txn to Known Recipient]:
  Txn ID:       2775211b3608...
  Amount:       Rs 51.00
  Risk Score:   0.03
  Used LLM:     True
  Reasons:      ['Transaction amount slightly below average.', 'Sender has limited transaction history.']
--------------------------------------------------
Sample 2 [Transaction to New Recipient]:
  Txn ID:       b7b7b14dfd38...
  Amount:       Rs 60.00
  Risk Score:   0.56
  Used LLM:     True
  Reasons:      ['Amount significantly higher than average (6000 paise vs 5120 paise)', 'New recipient for the sender', "Amount is 3.8 std-dev above sender's typical transaction", "amount is 3.8 std-dev above sender's typical transaction"]
--------------------------------------------------
Sample 3 [Anomalously Large Amount to New Recipient]:
  Txn ID:       6e766e80d60f...
  Amount:       Rs 450.00
  Risk Score:   0.71
  Used LLM:     True
  Reasons:      ['Amount significantly exceeds average transaction.', 'New recipient for the sender.', "Amount is 101.8 std-dev above sender's typical transaction.", "amount is 101.8 std-dev above sender's typical transaction"]
--------------------------------------------------
Sample 4 [High Offline Cap Spend (>80% Cap Used)]:
  Txn ID:       ed8cb1a3bba3...
  Amount:       Rs 350.00
  Cumulative:   Rs 1116.00 / Rs 2000.00
  Risk Score:   0.15
  Used LLM:     True
  Reasons:      ['Transaction amount is significantly higher than average.', 'Sender has a limited transaction history.']
============================================================
```
