"""
ROTM Detection Layer: Local LLM transaction anomaly scoring.

Design principle (see docs/PROTOCOL.md section 4): the local LLM is an
ADVISORY risk-scorer, not a gatekeeper. It never blocks a transaction by
itself -- offline nodes have no authority to "deny" a cryptographically
valid transaction (there's nothing to enforce that denial against). Instead
it attaches a risk_score in [0,1] that:
  - surfaces in the sender/recipient's UI ("this looks unusual")
  - is included as metadata when the transaction eventually reaches a
    ledger, so a human reviewer can prioritize investigation

This module is designed to work with a local inference server exposing an
OpenAI-compatible /v1/chat/completions endpoint -- i.e. LM Studio or Ollama
running Gemma/Phi-4 locally, no internet or API key required.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from typing import Optional

import urllib.request
import urllib.error

from core.transaction import Transaction


@dataclass
class RiskAssessment:
    txn_id: str
    risk_score: float          # 0.0 (normal) - 1.0 (highly anomalous)
    reasons: list[str]
    used_llm: bool              # False if fell back to heuristic-only scoring


class SenderProfile:
    """Rolling per-sender behavioral stats used both as heuristic features
    and as context fed to the LLM prompt."""

    def __init__(self, history_window: int = 20):
        self.amounts: list[int] = []
        self.recipients: set[str] = set()
        self.history_window = history_window

    def observe(self, txn: Transaction) -> None:
        self.amounts.append(txn.amount)
        self.recipients.add(txn.recipient_pub)
        if len(self.amounts) > self.history_window:
            self.amounts.pop(0)

    def mean_amount(self) -> float:
        return statistics.mean(self.amounts) if self.amounts else 0.0

    def stdev_amount(self) -> float:
        return statistics.pstdev(self.amounts) if len(self.amounts) > 1 else 0.0

    def is_new_recipient(self, recipient_pub: str) -> bool:
        return recipient_pub not in self.recipients


class LocalLLMRiskScorer:
    """Calls a local OpenAI-compatible endpoint (LM Studio default:
    http://localhost:1234/v1, Ollama: http://localhost:11434/v1).
    Falls back to pure heuristic scoring if the local server is unreachable
    -- this matters because the whole point is it must work fully offline,
    and a local inference server occasionally being down shouldn't crash
    the wallet."""

    def __init__(self, endpoint: str = "http://localhost:1234/v1/chat/completions",
                 model: str = "gemma-3-4b", timeout_s: float = 3.0):
        self.endpoint = endpoint
        self.model = model
        self.timeout_s = timeout_s
        self.profiles: dict[str, SenderProfile] = {}

    def _get_profile(self, sender_pub: str) -> SenderProfile:
        return self.profiles.setdefault(sender_pub, SenderProfile())

    def _heuristic_score(self, txn: Transaction, profile: SenderProfile,
                          offline_cap_paise: int, cumulative_offline_spend: int) -> tuple[float, list[str]]:
        reasons = []
        score = 0.0

        mean = profile.mean_amount()
        stdev = profile.stdev_amount()
        if mean > 0 and stdev > 0:
            z = (txn.amount - mean) / stdev
            if z > 2.5:
                score += 0.35
                reasons.append(f"amount is {z:.1f} std-dev above sender's typical transaction")

        if profile.is_new_recipient(txn.recipient_pub) and len(profile.recipients) >= 3:
            score += 0.15
            reasons.append("first transaction to this recipient")

        cap_fraction = cumulative_offline_spend / offline_cap_paise if offline_cap_paise else 0
        if cap_fraction > 0.8:
            score += 0.25
            reasons.append(f"transaction pushes sender to {cap_fraction*100:.0f}% of offline cap")

        if txn.amount == offline_cap_paise:
            score += 0.25
            reasons.append("amount exactly equals the offline cap (classic cap-draining pattern)")

        return min(score, 1.0), reasons

    def _call_local_llm(self, txn: Transaction, profile: SenderProfile, heuristic_reasons: list[str]) -> Optional[dict]:
        prompt = (
            "You are a transaction risk-scoring assistant running fully offline on a phone. "
            "You NEVER block transactions, you only output a JSON risk assessment. "
            "Given this transaction and sender history, output strict JSON: "
            '{"risk_score": <0.0-1.0>, "reasons": [<short strings>]}.\n\n'
            f"Transaction amount (paise): {txn.amount}\n"
            f"Sender's average transaction (paise): {profile.mean_amount():.0f}\n"
            f"Sender's transaction history count: {len(profile.amounts)}\n"
            f"Is this a new recipient for the sender: {profile.is_new_recipient(txn.recipient_pub)}\n"
            f"Heuristic flags already raised: {heuristic_reasons}\n"
        )
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 200,
        }).encode()

        req = urllib.request.Request(
            self.endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read().decode())
                content = data["choices"][0]["message"]["content"]
                # Model may wrap JSON in prose/markdown fences -- extract the object.
                start, end = content.find("{"), content.rfind("}")
                if start == -1 or end == -1:
                    return None
                return json.loads(content[start:end + 1])
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError):
            return None

    def assess(self, txn: Transaction, offline_cap_paise: int,
               cumulative_offline_spend: int) -> RiskAssessment:
        profile = self._get_profile(txn.sender_pub)

        heuristic_score, heuristic_reasons = self._heuristic_score(
            txn, profile, offline_cap_paise, cumulative_offline_spend
        )

        llm_result = self._call_local_llm(txn, profile, heuristic_reasons)
        profile.observe(txn)

        if llm_result and "risk_score" in llm_result:
            # Blend: LLM adds nuance/context reasoning, heuristic keeps it honest
            # (guards against the LLM under- or over-reacting on sparse local context).
            blended = 0.6 * float(llm_result["risk_score"]) + 0.4 * heuristic_score
            reasons = list(llm_result.get("reasons", [])) + heuristic_reasons
            return RiskAssessment(
                txn_id=txn.txn_id, risk_score=round(min(blended, 1.0), 3),
                reasons=reasons, used_llm=True,
            )

        return RiskAssessment(
            txn_id=txn.txn_id, risk_score=round(heuristic_score, 3),
            reasons=heuristic_reasons, used_llm=False,
        )
